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
DECIDE_PATH = "/decide"
EVENTS_PATH = "/events"

EXPERIMENT_METRICS_PATH_TEMPLATE = "/experiments/{experiment_id}/metrics"
GUARDRAILS_PATH_TEMPLATE = "/experiments/{experiment_id}/guardrails"
GUARDRAIL_TRIGGERS_PATH_TEMPLATE = "/experiments/{experiment_id}/guardrails/triggers"

GUARDRAILS_CHECK_PATH_TEMPLATE = ''

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
    try:
        t = login(email, password)
        return email, t
    except AssertionError:
        pass

    payload = {"email": email, "role": role, "is_active": True, "password": password}
    r = post(f"{USERS_PATH}/", token=admin_token, json=payload)
    assert_ok(r.status_code in (200, 201, 409),
              f"Cannot create user {email}: {r.status_code} {r.text}")

    t = login(email, password)
    return email, t


def unique_key(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex[:12]}"


# -------------------------
# Fixtures: flag/experiment/metrics/attach
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


def create_metric_rate_error(admin_token: str) -> Dict[str, Any]:
    """
    Создаём rate-метрику ошибок:
      m_error_rate = errors / exposure
    """
    payload = {
        "key": unique_key("test.m_error_rate"),
        "name": "Error rate",
        "aggregation_type": "rate",
        "numerator_event": "error",
        "denominator_event": "exposure",
        "requires_exposure": False,
    }
    r = post(f"{METRICS_PATH}/", token=admin_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create metric failed: {r.status_code} {r.text}")
    return r.json()


def exp_metrics_path(exp_id: str) -> str:
    return EXPERIMENT_METRICS_PATH_TEMPLATE.format(experiment_id=exp_id)


def guardrails_path(exp_id: str) -> str:
    return GUARDRAILS_PATH_TEMPLATE.format(experiment_id=exp_id)


def guardrail_triggers_path(exp_id: str) -> str:
    return GUARDRAIL_TRIGGERS_PATH_TEMPLATE.format(experiment_id=exp_id)


def guardrails_check_path(exp_id: str) -> str:
    if not GUARDRAILS_CHECK_PATH_TEMPLATE:
        return ""
    return GUARDRAILS_CHECK_PATH_TEMPLATE.format(experiment_id=exp_id)


def attach_metric(exp_token: str, exp_id: str, metric_id: str, *, role: str = "guardrail"):
    r = post(exp_metrics_path(exp_id), token=exp_token, json={"metric_id": metric_id, "role": role})
    assert_ok(r.status_code in (200, 201), f"Attach metric failed: {r.status_code} {r.text}")
    return r.json()


# -------------------------
# Helpers: run experiment, generate events
# -------------------------

def start_experiment(exp_token: str, exp_id: str):
    r = post(f"{EXPERIMENTS_PATH}/{exp_id}/start", token=exp_token, json=None)
    assert_ok(r.status_code == 200, f"Start experiment failed: {r.status_code} {r.text}")
    return r.json()


def decide_for_subject(flag_key: str, subject_id: str) -> Dict[str, Any]:
    r = post(DECIDE_PATH, json={"subject_id": subject_id, "flags": [flag_key], "attributes": {}})
    assert_ok(r.status_code == 200, f"Decide failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok(data.get("decisions") and len(data["decisions"])
              == 1, f"Bad decide response: {pretty_json(data)}")
    return data["decisions"][0]


def ingest_events(events: list[dict]) -> Dict[str, Any]:
    r = post(EVENTS_PATH, json={"events": events})
    assert_ok(r.status_code == 200, f"Ingest events failed: {r.status_code} {r.text}")
    return r.json()


# -------------------------
# Tests
# -------------------------

def test_guardrail_create_requires_attached_metric(admin_token: str, exp_token: str):
    exp = create_experiment(exp_token, admin_token)
    metric = create_metric_rate_error(admin_token)

    # НЕ прикрепляли метрику -> создание guardrail должно упасть (обычно 422/409/404)
    payload = {
        "metric_key": metric["key"],
        "comparison_operator": ">=",
        "threshold": 0.5,
        "window_minutes": 10,
        "action": "pause",
        "enabled": True,
    }
    r = post(guardrails_path(exp["id"]), token=exp_token, json=payload)
    assert_ok(r.status_code in (400, 404, 409, 422),
              f"Expected error when metric not attached, got {r.status_code} {r.text}")

    print("✅ test_guardrail_create_requires_attached_metric")


def test_guardrail_create_list_update_delete(admin_token: str, exp_token: str):
    exp = create_experiment(exp_token, admin_token)
    metric = create_metric_rate_error(admin_token)
    attach_metric(exp_token, exp["id"], metric["id"], role="guardrail")

    # create guardrail
    payload = {
        "metric_key": metric["key"],
        "comparison_operator": ">=",
        "threshold": 0.5,
        "window_minutes": 10,
        "action": "pause",
        "enabled": True,
    }
    r = post(guardrails_path(exp["id"]), token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create guardrail failed: {r.status_code} {r.text}")
    gr = r.json()
    assert_ok("id" in gr, f"No id in guardrail: {pretty_json(gr)}")
    assert_ok(gr.get("metric_key") == metric["key"], f"metric_key mismatch: {pretty_json(gr)}")
    assert_ok(gr.get("action") == "pause", f"action mismatch: {pretty_json(gr)}")

    # list guardrails
    r = get(guardrails_path(exp["id"]), token=exp_token, params={"offset": 0, "limit": 200})
    assert_ok(r.status_code == 200, f"List guardrails failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("items" in data and "total" in data, f"List shape invalid: {pretty_json(data)}")
    assert_ok(any(it.get("id") == gr["id"] for it in data["items"]),
              f"Created guardrail not in list: {pretty_json(data)}")

    # update (disable or change threshold)
    r = patch(f"{guardrails_path(exp['id'])}/{gr['id']}", token=exp_token, json={"enabled": False})
    assert_ok(r.status_code == 200, f"Update guardrail failed: {r.status_code} {r.text}")
    upd = r.json()
    assert_ok(upd.get("enabled") is False, f"enabled not updated: {pretty_json(upd)}")

    # delete
    r = delete(f"{guardrails_path(exp['id'])}/{gr['id']}", token=exp_token)
    assert_ok(r.status_code in (200, 204), f"Delete guardrail failed: {r.status_code} {r.text}")

    # list -> removed
    r = get(guardrails_path(exp["id"]), token=exp_token, params={"offset": 0, "limit": 200})
    assert_ok(r.status_code == 200, f"List guardrails failed: {r.status_code} {r.text}")
    data2 = r.json()
    assert_ok(not any(it.get("id") == gr["id"] for it in data2["items"]),
              f"Deleted guardrail still present: {pretty_json(data2)}")

    print("✅ test_guardrail_create_list_update_delete")


def main():
    print(f"BASE_URL={BASE_URL}")
    print(f"GUARDRAILS_PATH_TEMPLATE={GUARDRAILS_PATH_TEMPLATE}")
    print(f"GUARDRAILS_CHECK_PATH_TEMPLATE={GUARDRAILS_CHECK_PATH_TEMPLATE or '(not set)'}")

    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    _, exp_token = ensure_user_exists(admin_token, EXP_EMAIL, EXP_PASSWORD, role="experimenter")

    test_guardrail_create_requires_attached_metric(admin_token, exp_token)
    test_guardrail_create_list_update_delete(admin_token, exp_token)

    print("\n✅✅✅ ALL GUARDRAILS TESTS PASSED")


# if __name__ == "__main__":
main()
