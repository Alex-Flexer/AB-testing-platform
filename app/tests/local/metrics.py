import os
import uuid
import requests
from typing import Any, Dict, Optional, Tuple


BASE_URL = "http://127.0.0.1:80"

AUTH_LOGIN_PATH = "/auth/login"
USERS_PATH = "/users"
METRICS_PATH = "/metrics"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mail.ru")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

EXP_EMAIL = os.getenv("EXPERIMENTER_EMAIL", "experimenter@mail.ru")
EXP_PASSWORD = os.getenv("EXPERIMENTER_PASSWORD", "experimenter123")

VIEWER_EMAIL = os.getenv("VIEWER_EMAIL", "viewer@example.com")
VIEWER_PASSWORD = os.getenv("VIEWER_PASSWORD", "viewer123")


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
    # 1) try login
    try:
        t = login(email, password)
        return email, t
    except AssertionError:
        pass

    # 2) create user (admin)
    payload = {"email": email, "role": role, "is_active": True, "password": password}
    r = post(f"{USERS_PATH}/", token=admin_token, json=payload)

    assert_ok(
        r.status_code in (200, 201, 409),
        f"Cannot create user {email} for tests. Status={r.status_code} body={r.text}"
    )

    # 3) login again
    t = login(email, password)
    return email, t


def unique_key(prefix: str) -> str:
    return f"{prefix}.{uuid.uuid4().hex[:12]}"


# -------------------------
# Fixtures
# -------------------------

def metric_payload_count() -> Dict[str, Any]:
    # aggregation_type=count требует numerator_event
    return {
        "key": unique_key("test.metric"),
        "name": "Test metric COUNT",
        "aggregation_type": "count",
        "numerator_event": "purchase",
    }


def metric_payload_unique_count() -> Dict[str, Any]:
    return {
        "key": unique_key("test.metric"),
        "name": "Test metric UNIQUE_COUNT",
        "aggregation_type": "unique_count",
        "numerator_event": "click",
    }


def metric_payload_rate() -> Dict[str, Any]:
    return {
        "key": unique_key("test.metric"),
        "name": "Test metric RATE",
        "aggregation_type": "rate",
        "numerator_event": "purchase",
        "denominator_event": "exposure",
    }


def metric_payload_avg() -> Dict[str, Any]:
    return {
        "key": unique_key("test.metric"),
        "name": "Test metric AVG",
        "aggregation_type": "avg",
        "field_path": "perf.latency_ms",
    }


def metric_payload_p95() -> Dict[str, Any]:
    return {
        "key": unique_key("test.metric"),
        "name": "Test metric P95",
        "aggregation_type": "p95",
        "field_path": "perf.latency_ms",
    }


# -------------------------
# Tests
# -------------------------

def test_create_metric_ok(exp_token: str):
    payload = metric_payload_count()
    r = post(f"{METRICS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create metric failed: {r.status_code} {r.text}")
    data = r.json()

    assert_ok("id" in data, f"No id in response: {data}")
    assert_ok(data["key"] == payload["key"], f"key mismatch: {data}")
    assert_ok(data["aggregation_type"] == "count", f"aggregation_type mismatch: {data}")
    assert_ok(data.get("numerator_event") ==
              payload["numerator_event"], f"numerator_event mismatch: {data}")
    assert_ok(data.get("denominator_event") is None, f"denominator_event must be null: {data}")
    assert_ok(data.get("field_path") is None, f"field_path must be null: {data}")

    print("✅ test_create_metric_ok")
    return data


def test_create_metric_validation_errors(exp_token: str):
    # 1) empty body -> 422
    r = post(f"{METRICS_PATH}/", token=exp_token, json={})
    assert_ok(r.status_code == 422, f"Expected 422 on empty body, got {r.status_code} {r.text}")

    # 2) count without numerator_event -> 422 (по твоей схеме MetricCreate)
    p = metric_payload_count()
    p.pop("numerator_event", None)
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code == 422,
              f"Expected 422 on count without numerator_event, got {r.status_code} {r.text}")

    # 3) rate without denominator_event -> 422
    p = metric_payload_rate()
    p.pop("denominator_event", None)
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code == 422,
              f"Expected 422 on rate without denominator_event, got {r.status_code} {r.text}")

    # 4) avg without field_path -> 422
    p = metric_payload_avg()
    p.pop("field_path", None)
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code == 422,
              f"Expected 422 on avg without field_path, got {r.status_code} {r.text}")

    # 5) avg with numerator_event -> 422
    p = metric_payload_avg()
    p["numerator_event"] = "purchase"
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code == 422,
              f"Expected 422 on avg with numerator_event, got {r.status_code} {r.text}")

    # 6) rate with field_path -> 422
    p = metric_payload_rate()
    p["field_path"] = "perf.latency_ms"
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code == 422,
              f"Expected 422 on rate with field_path, got {r.status_code} {r.text}")

    print("✅ test_create_metric_validation_errors")


def test_metric_key_unique(exp_token: str):
    payload = metric_payload_unique_count()
    r = post(f"{METRICS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create metric failed: {r.status_code} {r.text}")
    m1 = r.json()

    # same key again -> 409
    payload2 = dict(payload)
    payload2["name"] = "Different name"
    r = post(f"{METRICS_PATH}/", token=exp_token, json=payload2)
    assert_ok(r.status_code == 409, f"Expected 409 on duplicate key, got {r.status_code} {r.text}")

    print("✅ test_metric_key_unique")
    return m1


def test_list_and_get_metric(viewer_token: str, metric: Dict[str, Any]):
    metric_id = metric["id"]

    # GET by id
    r = get(f"{METRICS_PATH}/{metric_id}", token=viewer_token)
    assert_ok(r.status_code == 200, f"Get metric failed: {r.status_code} {r.text}")
    got = r.json()
    assert_ok(got["id"] == metric_id, "Get metric id mismatch")

    # LIST
    r = get(f"{METRICS_PATH}/", token=viewer_token, params={"offset": 0, "limit": 50})
    assert_ok(r.status_code == 200, f"List metrics failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("items" in data and "total" in data, f"List shape invalid: {data}")
    assert_ok(isinstance(data["items"], list), "items must be list")
    assert_ok(isinstance(data["total"], int), "total must be int")

    ids = [it.get("id") for it in data["items"]]
    assert_ok(metric_id in ids, f"Created metric not found in list. ids={ids}")

    # pagination errors
    r = get(f"{METRICS_PATH}/", token=viewer_token, params={"offset": -1, "limit": 50})
    assert_ok(r.status_code in (400, 422), f"Expected error on offset=-1, got {r.status_code}")

    r = get(f"{METRICS_PATH}/", token=viewer_token, params={"offset": 0, "limit": 0})
    assert_ok(r.status_code in (400, 422), f"Expected error on limit=0, got {r.status_code}")

    print("✅ test_list_and_get_metric")


def test_viewer_cannot_create_update_delete(viewer_token: str):
    # create -> 403
    p = metric_payload_count()
    r = post(f"{METRICS_PATH}/", token=viewer_token, json=p)
    assert_ok(r.status_code == 403, f"Expected 403 for viewer create, got {r.status_code} {r.text}")

    print("✅ test_viewer_cannot_create_update_delete (create checked)")


def test_update_metric_ok(exp_token: str):
    # create rate metric
    p = metric_payload_rate()
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code in (200, 201), f"Create metric failed: {r.status_code} {r.text}")
    m = r.json()

    # patch name only
    r = patch(f"{METRICS_PATH}/{m['id']}", token=exp_token, json={"name": "RATE UPDATED"})
    assert_ok(r.status_code == 200, f"Patch metric failed: {r.status_code} {r.text}")
    upd = r.json()
    assert_ok(upd["name"] == "RATE UPDATED", f"name not updated: {upd}")

    # empty patch -> 422
    r = patch(f"{METRICS_PATH}/{m['id']}", token=exp_token, json={})
    assert_ok(r.status_code == 422, f"Expected 422 on empty patch, got {r.status_code} {r.text}")

    print("✅ test_update_metric_ok")
    return upd


def test_update_metric_change_aggregation_with_validation(exp_token: str):
    # create count metric
    p = metric_payload_count()
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code in (200, 201), f"Create metric failed: {r.status_code} {r.text}")
    m = r.json()

    # try switch to avg without field_path -> should fail (service should validate)
    r = patch(
        f"{METRICS_PATH}/{m['id']}",
        token=exp_token,
        json={"aggregation_type": "avg"},
    )
    assert_ok(r.status_code == 422,
              f"Expected 422 on agg change without field_path, got {r.status_code} {r.text}")

    # proper switch to avg with field_path (and numerator should be cleared by service)
    r = patch(
        f"{METRICS_PATH}/{m['id']}",
        token=exp_token,
        json={"aggregation_type": "avg", "field_path": "perf.latency_ms"},
    )
    assert_ok(r.status_code == 200,
              f"Expected 200 on agg change to avg, got {r.status_code} {r.text}")
    upd = r.json()
    assert_ok(upd["aggregation_type"] == "avg", f"agg not updated: {upd}")
    assert_ok(upd.get("field_path") == "perf.latency_ms", f"field_path not set: {upd}")
    # your response schema returns numerator_event/denominator_event optional:
    assert_ok(upd.get("numerator_event") is None, f"numerator_event must be null for avg: {upd}")
    assert_ok(upd.get("denominator_event") is None,
              f"denominator_event must be null for avg: {upd}")

    print("✅ test_update_metric_change_aggregation_with_validation")


def test_delete_metric(exp_token: str):
    p = metric_payload_p95()
    r = post(f"{METRICS_PATH}/", token=exp_token, json=p)
    assert_ok(r.status_code in (200, 201), f"Create metric failed: {r.status_code} {r.text}")
    m = r.json()

    r = delete(f"{METRICS_PATH}/{m['id']}", token=exp_token)
    assert_ok(r.status_code in (200, 204), f"Delete metric failed: {r.status_code} {r.text}")

    # GET after delete -> 404
    r = get(f"{METRICS_PATH}/{m['id']}", token=exp_token)
    assert_ok(r.status_code == 404, f"Expected 404 after delete, got {r.status_code} {r.text}")

    print("✅ test_delete_metric")


# -------------------------
# Main
# -------------------------

def main():
    print(f"BASE_URL={BASE_URL}")
    print(f"AUTH_LOGIN_PATH={AUTH_LOGIN_PATH}")
    print(f"USERS_PATH={USERS_PATH}")
    print(f"METRICS_PATH={METRICS_PATH}")

    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    # Ensure users exist
    _, exp_token = ensure_user_exists(admin_token, EXP_EMAIL, EXP_PASSWORD, role="experimenter")
    _, viewer_token = ensure_user_exists(admin_token, VIEWER_EMAIL, VIEWER_PASSWORD, role="viewer")

    # Run tests
    test_create_metric_validation_errors(exp_token)

    metric = test_create_metric_ok(exp_token)
    test_list_and_get_metric(viewer_token, metric)

    test_metric_key_unique(exp_token)
    test_viewer_cannot_create_update_delete(viewer_token)

    test_update_metric_ok(exp_token)
    test_update_metric_change_aggregation_with_validation(exp_token)

    test_delete_metric(exp_token)

    print("\n✅✅✅ ALL METRICS TESTS PASSED")


# if __name__ == "__main__":
main()
