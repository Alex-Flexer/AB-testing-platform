import os
import uuid
import requests
from typing import Any, Dict, Optional, Tuple

BASE_URL = "http://127.0.0.1:80"

AUTH_LOGIN_PATH = "/auth/login"
USERS_PATH = "/users"
FLAGS_PATH = "/flags"
EXPERIMENTS_PATH = "/experiments"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mail.ru")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

EXPERIMENT_METRICS_PATH_TEMPLATE = "/experiments/{experiment_id}/metrics"
EXPERIMENT_METRIC_DETACH_PATH_TEMPLATE = "/experiments/{experiment_id}/metrics/{metric_id}"

VIEWER_EMAIL = os.getenv("VIEWER_EMAIL", "viewer@maril.ru")
VIEWER_PASSWORD = os.getenv("VIEWER_PASSWORD", "viewer123")

EXP_EMAIL = os.getenv("EXPERIMENTER_EMAIL", "experimenter@mail.ru")
EXP_PASSWORD = os.getenv("EXPERIMENTER_PASSWORD", "experimenter123")


TIMEOUT = 10.0


# -------------------------
# Small test utils
# -------------------------

def assert_ok(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def pretty_json(obj: Any) -> str:
    try:
        import json
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def auth_header(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def post(path: str, *, token: Optional[str] = None, json: Optional[dict] = None) -> requests.Response:
    print(f"{BASE_URL}{path}")
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.post(f"{BASE_URL}{path}", json=json, headers=headers, timeout=TIMEOUT)


def get(path: str, *, token: Optional[str] = None, params: Optional[dict] = None) -> requests.Response:
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.get(f"{BASE_URL}{path}", params=params, headers=headers, timeout=TIMEOUT)


def patch(path: str, *, token: Optional[str] = None, json: Optional[dict] = None) -> requests.Response:
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.patch(f"{BASE_URL}{path}", json=json, headers=headers, timeout=TIMEOUT)


def delete(path: str, *, token: Optional[str] = None) -> requests.Response:
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.delete(f"{BASE_URL}{path}", headers=headers, timeout=TIMEOUT)


def login(email: str, password: str) -> str:
    r = post(AUTH_LOGIN_PATH, json={"email": email, "password": password})
    assert_ok(r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("access_token" in data, f"No access_token in login response: {data}")
    return data["access_token"]


def ensure_user_exists(admin_token: str, email: str, password: str, role: str) -> Tuple[str, str]:
    # 1) try login
    try:
        t = login(email, password)
        return email, t
    except AssertionError:
        pass

    # 2) create user (админом)
    payload = {"email": email, "role": role, "is_active": True, "password": password}
    r = post(f"{USERS_PATH}/", token=admin_token, json=payload)

    # если ты password не добавлял в UserCreate — будет 422; тогда просто сообщим
    assert_ok(
        r.status_code in (200, 201, 409),
        f"Cannot create user {email} for tests. "
        f"Maybe your UserCreate does not include password yet? "
        f"Status={r.status_code} body={r.text}"
    )

    # 3) login again
    t = login(email, password)
    return email, t


def unique_key(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex[:12]}"


# -------------------------
# Test fixtures (create flag, experiment payloads)
# -------------------------

def create_flag(admin_token: str, *, flag_type: str = "bool") -> Dict[str, Any]:
    key = unique_key("test.flag")
    payload = {
        "key": key,
        "type": flag_type,
        "default_value": False if flag_type == "bool" else ("0" if flag_type == "number" else "off"),
        "description": "test flag",
    }
    r = post(f"{FLAGS_PATH}/", token=admin_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create flag failed: {r.status_code} {r.text}")
    return r.json()


def experiment_payload(feature_flag_id: str, *, traffic: float = 100.0) -> Dict[str, Any]:
    return {
        "name": f"Experiment {uuid.uuid4().hex[:8]}",
        "description": "test experiment",
        "feature_flag_id": feature_flag_id,
        "traffic_percentage": traffic,
        "targeting_rule": None,
        "variants": [
            {"name": "control", "value": "false", "weight": traffic * 0.5, "is_control": True},
            {"name": "treatment", "value": "true", "weight": traffic * 0.5, "is_control": False},
        ],
    }


# -------------------------
# Experiments tests
# -------------------------

def test_create_experiment_ok(exp_token: str, admin_token: str):
    flag = create_flag(admin_token, flag_type="bool")
    payload = experiment_payload(flag["id"], traffic=100.0)

    r = post(f"{EXPERIMENTS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create experiment failed: {r.status_code} {r.text}")
    data = r.json()

    assert_ok("id" in data, f"No id in response: {data}")
    assert_ok(data["feature_flag_id"] == flag["id"], f"feature_flag_id mismatch: {data}")
    assert_ok(data["traffic_percentage"] == 100.0, f"traffic_percentage mismatch: {data}")
    assert_ok(isinstance(data.get("variants", []), list), f"variants missing: {data}")

    # schema constraints
    control_cnt = sum(1 for v in data["variants"] if v.get("is_control") is True)
    assert_ok(control_cnt == 1,
              f"Expected exactly 1 control variant, got {control_cnt}: {data['variants']}")

    total_weight = round(sum(float(v["weight"]) for v in data["variants"]), 6)
    assert_ok(total_weight == 100.0, f"Sum weights must equal traffic_percentage: {total_weight}")

    print("✅ test_create_experiment_ok")
    return data, flag


def test_create_experiment_validation_errors(exp_token: str, admin_token: str):
    flag = create_flag(admin_token, flag_type="bool")

    # 1) missing required fields -> 422
    r = post(f"{EXPERIMENTS_PATH}", token=exp_token, json={})
    assert_ok(r.status_code == 422, f"Expected 422 on empty body, got {r.status_code} {r.text}")

    # 2) weights sum != traffic_percentage -> 422
    payload = experiment_payload(flag["id"], traffic=50.0)
    payload["variants"][0]["weight"] = 10
    payload["variants"][1]["weight"] = 10
    r = post(f"{EXPERIMENTS_PATH}/", token=exp_token, json=payload)

    assert_ok(r.status_code == 422,
              f"Expected 422 on wrong weights sum, got {r.status_code} {r.text}")

    # 3) not exactly one control -> 422
    payload = experiment_payload(flag["id"], traffic=100.0)
    payload["variants"][1]["is_control"] = True
    r = post(f"{EXPERIMENTS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code == 422,
              f"Expected 422 on multiple controls, got {r.status_code} {r.text}")

    # 4) duplicate variant names -> 422
    payload = experiment_payload(flag["id"], traffic=100.0)
    payload["variants"][1]["name"] = payload["variants"][0]["name"]
    r = post(f"{EXPERIMENTS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code == 422,
              f"Expected 422 on duplicate variant names, got {r.status_code} {r.text}")

    print("✅ test_create_experiment_validation_errors")


def test_list_and_get_experiment(exp_token: str, exp: Dict[str, Any]):
    exp_id = exp["id"]

    # GET by id
    r = get(f"{EXPERIMENTS_PATH}/{exp_id}", token=exp_token)
    assert_ok(r.status_code == 200, f"Get experiment failed: {r.status_code} {r.text}")
    got = r.json()
    assert_ok(got["id"] == exp_id, "Get experiment id mismatch")

    # LIST (pagination)
    r = get(f"{EXPERIMENTS_PATH}/", token=exp_token, params={"offset": 0, "limit": 50})
    assert_ok(r.status_code == 200, f"List experiments failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("items" in data and "total" in data, f"List shape invalid: {data}")
    assert_ok(isinstance(data["items"], list), "items must be list")
    assert_ok(isinstance(data["total"], int), "total must be int")

    # should include our exp (not guaranteed if your list has filters, but usually yes)
    ids = [it.get("id") for it in data["items"]]
    assert_ok(exp_id in ids, f"Created exp not found in list. ids={ids}")

    # pagination errors
    r = get(f"{EXPERIMENTS_PATH}/", token=exp_token, params={"offset": -1, "limit": 50})
    assert_ok(r.status_code in (400, 422), f"Expected error on offset=-1, got {r.status_code}")

    r = get(f"{EXPERIMENTS_PATH}/", token=exp_token, params={"offset": 0, "limit": 0})
    assert_ok(r.status_code in (400, 422), f"Expected error on limit=0, got {r.status_code}")

    print("✅ test_list_and_get_experiment")


def test_update_experiment_ok(exp_token: str, exp: Dict[str, Any]):
    exp_id = exp["id"]

    payload = {"name": f"{exp['name']} UPDATED", "description": "updated desc"}
    r = patch(f"{EXPERIMENTS_PATH}/{exp_id}", token=exp_token, json=payload)
    assert_ok(r.status_code == 200, f"Patch experiment failed: {r.status_code} {r.text}")
    upd = r.json()
    assert_ok(upd["id"] == exp_id, "id mismatch after update")
    assert_ok(upd["name"].endswith("UPDATED"), f"name not updated: {upd['name']}")
    assert_ok(upd["description"] == "updated desc",
              f"description not updated: {upd.get('description')}")

    # empty patch -> 422 (по твоей схеме)
    r = patch(f"{EXPERIMENTS_PATH}/{exp_id}", token=exp_token, json={})
    assert_ok(r.status_code == 422, f"Expected 422 on empty patch, got {r.status_code} {r.text}")

    print("✅ test_update_experiment_ok")
    return upd


def test_update_experiment_forbidden_for_other_experimenter(
    admin_token: str,
    exp1_token: str,
    exp2_token: str,
):
    # создаём флаг
    flag = create_flag(admin_token, flag_type="bool")

    # exp1 создаёт эксперимент
    payload = experiment_payload(flag["id"], traffic=100.0)
    r = post(f"{EXPERIMENTS_PATH}/", token=exp1_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create exp by exp1 failed: {r.status_code} {r.text}")
    exp = r.json()

    # exp2 пытается обновить -> 403
    r = patch(
        f"{EXPERIMENTS_PATH}/{exp['id']}",
        token=exp2_token,
        json={"description": "hacked"},
    )
    assert_ok(r.status_code == 403,
              f"Expected 403 for чужой эксперимент, got {r.status_code} {r.text}")

    # admin может обновить -> 200
    r = patch(
        f"{EXPERIMENTS_PATH}/{exp['id']}",
        token=admin_token,
        json={"description": "admin edit"},
    )
    assert_ok(r.status_code == 200, f"Admin patch failed: {r.status_code} {r.text}")

    print("✅ test_update_experiment_forbidden_for_other_experimenter")


def test_viewer_cannot_create_experiment(viewer_token: str, admin_token: str):
    flag = create_flag(admin_token, flag_type="bool")
    payload = experiment_payload(flag["id"], traffic=100.0)
    r = post(f"{EXPERIMENTS_PATH}/", token=viewer_token, json=payload)
    assert_ok(r.status_code == 403, f"Expected 403 for viewer create, got {r.status_code} {r.text}")
    print("✅ test_viewer_cannot_create_experiment")


def test_delete_experiment(exp_token: str, admin_token: str):
    # создаём эксперимент и удаляем
    flag = create_flag(admin_token, flag_type="bool")
    payload = experiment_payload(flag["id"], traffic=100.0)
    r = post(f"{EXPERIMENTS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create experiment failed: {r.status_code} {r.text}")
    exp = r.json()

    r = delete(f"{EXPERIMENTS_PATH}/{exp['id']}", token=exp_token)
    # у тебя может быть hard delete (204/200) или soft delete (200) — проверим мягко
    assert_ok(r.status_code in (200, 204), f"Delete experiment failed: {r.status_code} {r.text}")

    # повторный GET -> 404
    r = get(f"{EXPERIMENTS_PATH}/{exp['id']}", token=exp_token)
    assert_ok(r.status_code == 404, f"Expected 404 after delete, got {r.status_code} {r.text}")

    print("✅ test_delete_experiment")


# -------------------------
# Main
# -------------------------

def main():
    print(f"BASE_URL={BASE_URL}")
    print(f"AUTH_LOGIN_PATH={AUTH_LOGIN_PATH}")
    print(f"FLAGS_PATH={FLAGS_PATH}")
    print(f"EXPERIMENTS_PATH={EXPERIMENTS_PATH}")

    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    # Убедимся что есть пользователь-экспериментер и viewer (если у тебя уже есть сиды — просто логин)
    _, exp_token = ensure_user_exists(admin_token, EXP_EMAIL, EXP_PASSWORD, role="experimenter")
    _, viewer_token = ensure_user_exists(admin_token, VIEWER_EMAIL, VIEWER_PASSWORD, role="viewer")

    # # Второй экспериментер для теста ownership
    exp2_email = f"exp2_{uuid.uuid4().hex[:6]}@example.com"
    exp2_password = "exp2pass123"
    _, exp2_token = ensure_user_exists(admin_token, exp2_email, exp2_password, role="experimenter")

    # # -------------------------
    # # Run tests
    # # -------------------------
    test_create_experiment_validation_errors(exp_token, admin_token)

    exp, _flag = test_create_experiment_ok(exp_token, admin_token)
    test_list_and_get_experiment(exp_token, exp)
    exp = test_update_experiment_ok(exp_token, exp)

    test_viewer_cannot_create_experiment(viewer_token, admin_token)
    test_update_experiment_forbidden_for_other_experimenter(admin_token, exp_token, exp2_token)
    test_delete_experiment(exp_token, admin_token)

    print("\n✅✅✅ ALL EXPERIMENT TESTS PASSED")


# if __name__ == "__main__":
main()
