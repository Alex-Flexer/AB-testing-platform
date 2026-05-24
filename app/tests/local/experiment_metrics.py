import os
import uuid
import requests
from typing import Any, Dict, Optional, Tuple

BASE_URL = "http://127.0.0.1:80"

AUTH_LOGIN_PATH = "/auth/login"
USERS_PATH = "/users"
FLAGS_PATH = "/flags"
EXPERIMENTS_PATH = "/experiments"
METRICS_PATH = "/metrics"

EXPERIMENT_METRICS_PATH_TEMPLATE = "/experiments/{experiment_id}/metrics"
EXPERIMENT_METRIC_DETACH_PATH_TEMPLATE = "/experiments/{experiment_id}/metrics/{metric_id}"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mail.ru")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

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
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.post(f"{BASE_URL}{path}", json=json, headers=headers, timeout=TIMEOUT)


def get(path: str, *, token: Optional[str] = None, params: Optional[dict] = None) -> requests.Response:
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.get(f"{BASE_URL}{path}", params=params, headers=headers, timeout=TIMEOUT)


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
    try:
        t = login(email, password)
        return email, t
    except AssertionError:
        pass

    payload = {"email": email, "role": role, "is_active": True, "password": password}
    r = post(f"{USERS_PATH}/", token=admin_token, json=payload)
    assert_ok(
        r.status_code in (200, 201, 409),
        f"Cannot create user {email} for tests. Status={r.status_code} body={r.text}",
    )

    t = login(email, password)
    return email, t


def unique_key(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex[:12]}"


# -------------------------
# Fixtures: create flag/experiment/metric
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


def create_experiment(exp_token: str, admin_token: str) -> Dict[str, Any]:
    flag = create_flag(admin_token, flag_type="bool")
    payload = experiment_payload(flag["id"], traffic=100.0)
    r = post(f"{EXPERIMENTS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create experiment failed: {r.status_code} {r.text}")
    return r.json()


def create_metric(admin_token: str, *, key_prefix: str = "m") -> Dict[str, Any]:
    payload = {
        "key": unique_key(f"test.{key_prefix}"),
        "name": "test metric",
        "aggregation_type": "count",
        "numerator_event": "click",
    }
    r = post(f"{METRICS_PATH}/", token=admin_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create metric failed: {r.status_code} {r.text}")
    return r.json()


def exp_metrics_path(exp_id: str) -> str:
    return EXPERIMENT_METRICS_PATH_TEMPLATE.format(experiment_id=exp_id)


def exp_metric_detach_path(exp_id: str, metric_id: str) -> str:
    return EXPERIMENT_METRIC_DETACH_PATH_TEMPLATE.format(experiment_id=exp_id, metric_id=metric_id)


# -------------------------
# Tests
# -------------------------

def test_attach_list_detach_ok(admin_token: str, exp_token: str):
    exp = create_experiment(exp_token, admin_token)
    metric = create_metric(admin_token, key_prefix="click")

    # attach
    r = post(exp_metrics_path(exp["id"]), token=exp_token, json={
             "metric_id": metric["id"], "role": "guardrail"})
    assert_ok(r.status_code in (200, 201), f"Attach metric failed: {r.status_code} {r.text}")
    link = r.json()
    assert_ok(link.get("experiment_id") == exp["id"],
              f"experiment_id mismatch: {pretty_json(link)}")
    assert_ok(link.get("metric_id") == metric["id"], f"metric_id mismatch: {pretty_json(link)}")
    assert_ok(link.get("role") == "guardrail", f"role mismatch: {pretty_json(link)}")

    # list
    r = get(exp_metrics_path(exp["id"]), token=exp_token, params={"offset": 0, "limit": 200})
    assert_ok(r.status_code == 200, f"List exp metrics failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("items" in data and "total" in data, f"List shape invalid: {pretty_json(data)}")
    assert_ok(isinstance(data["items"], list), "items must be list")
    assert_ok(any(it.get("metric_id") == metric["id"] for it in data["items"]),
              f"Attached metric not found in list: {pretty_json(data)}")

    # detach
    r = delete(exp_metric_detach_path(exp["id"], metric["id"]), token=exp_token)
    assert_ok(r.status_code in (200, 204), f"Detach metric failed: {r.status_code} {r.text}")

    # list again -> metric gone
    r = get(exp_metrics_path(exp["id"]), token=exp_token, params={"offset": 0, "limit": 200})
    assert_ok(r.status_code == 200, f"List exp metrics failed: {r.status_code} {r.text}")
    data2 = r.json()
    assert_ok(not any(it.get("metric_id") == metric["id"] for it in data2["items"]),
              f"Detached metric still present: {pretty_json(data2)}")

    print("✅ test_attach_list_detach_ok")


def test_attach_updates_role(admin_token: str, exp_token: str):
    exp = create_experiment(exp_token, admin_token)
    metric = create_metric(admin_token, key_prefix="click2")

    # attach as secondary
    r = post(exp_metrics_path(exp["id"]), token=exp_token, json={
             "metric_id": metric["id"], "role": "secondary"})
    assert_ok(r.status_code in (200, 201), f"Attach metric failed: {r.status_code} {r.text}")
    link1 = r.json()
    assert_ok(link1.get("role") == "secondary", f"role mismatch: {pretty_json(link1)}")

    # attach again with role=guardrail -> should upsert/update role
    r = post(exp_metrics_path(exp["id"]), token=exp_token, json={
             "metric_id": metric["id"], "role": "guardrail"})
    assert_ok(r.status_code in (200, 201), f"Attach (update role) failed: {r.status_code} {r.text}")
    link2 = r.json()
    assert_ok(link2.get("role") == "guardrail", f"role not updated: {pretty_json(link2)}")

    # list -> only one link for same metric_id
    r = get(exp_metrics_path(exp["id"]), token=exp_token, params={"offset": 0, "limit": 200})
    assert_ok(r.status_code == 200, f"List exp metrics failed: {r.status_code} {r.text}")
    items = r.json().get("items", [])
    same = [it for it in items if it.get("metric_id") == metric["id"]]
    assert_ok(len(same) == 1,
              f"Expected single link for metric, got {len(same)}: {pretty_json(items)}")
    assert_ok(same[0].get("role") == "guardrail", f"role mismatch in list: {pretty_json(same[0])}")

    print("✅ test_attach_updates_role")


def test_other_experimenter_forbidden(admin_token: str, exp1_token: str, exp2_token: str):
    exp = create_experiment(exp1_token, admin_token)
    metric = create_metric(admin_token, key_prefix="own")

    # exp2 tries attach -> 403
    r = post(exp_metrics_path(exp["id"]), token=exp2_token, json={
             "metric_id": metric["id"], "role": "secondary"})
    assert_ok(r.status_code == 403,
              f"Expected 403 for чужой эксперимент, got {r.status_code} {r.text}")

    # exp2 tries list -> 403 (в нашей реализации list тоже owner/admin)
    r = get(exp_metrics_path(exp["id"]), token=exp2_token, params={"offset": 0, "limit": 200})
    assert_ok(r.status_code == 403, f"Expected 403 for чужой list, got {r.status_code} {r.text}")

    # admin can attach -> 200/201
    r = post(exp_metrics_path(exp["id"]), token=admin_token, json={
             "metric_id": metric["id"], "role": "secondary"})
    assert_ok(r.status_code in (200, 201), f"Admin attach failed: {r.status_code} {r.text}")

    print("✅ test_other_experimenter_forbidden")


# -------------------------
# Main
# -------------------------

def main():
    print(f"BASE_URL={BASE_URL}")
    print(f"AUTH_LOGIN_PATH={AUTH_LOGIN_PATH}")
    print(f"EXPERIMENT_METRICS_PATH_TEMPLATE={EXPERIMENT_METRICS_PATH_TEMPLATE}")

    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    _, exp1_token = ensure_user_exists(admin_token, EXP_EMAIL, EXP_PASSWORD, role="experimenter")

    exp2_email = f"exp2_{uuid.uuid4().hex[:6]}@example.com"
    exp2_password = "exp2pass123"
    _, exp2_token = ensure_user_exists(admin_token, exp2_email, exp2_password, role="experimenter")

    test_attach_list_detach_ok(admin_token, exp1_token)
    test_attach_updates_role(admin_token, exp1_token)
    test_other_experimenter_forbidden(admin_token, exp1_token, exp2_token)

    print("\n✅✅✅ ALL EXPERIMENT_METRICS TESTS PASSED")


# if __name__ == "__main__":
main()
