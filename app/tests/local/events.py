import os
import uuid
import requests
from typing import Any, Dict, Optional, Tuple

BASE_URL = "http://127.0.0.1:80"

AUTH_LOGIN_PATH = "/auth/login"
USERS_PATH = "/users"
FLAGS_PATH = "/flags"
EXPERIMENTS_PATH = "/experiments"
DECIDE_PATH = "/decide"
EVENTS_PATH = "/events"

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


def post(path: str, *, token: Optional[str] = None, json: Optional[dict] = None, params: Optional[dict] = None) -> requests.Response:
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.post(f"{BASE_URL}{path}", json=json, headers=headers, params=params, timeout=TIMEOUT)


def get(path: str, *, token: Optional[str] = None, params: Optional[dict] = None) -> requests.Response:
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.get(f"{BASE_URL}{path}", params=params, headers=headers, timeout=TIMEOUT)


def patch(path: str, *, token: Optional[str] = None, json: Optional[dict] = None, params: Optional[dict] = None) -> requests.Response:
    headers = {}
    if token:
        headers.update(auth_header(token))
    return requests.patch(f"{BASE_URL}{path}", json=json, headers=headers, params=params, timeout=TIMEOUT)


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
# Fixtures: flag, experiment, decide
# -------------------------

def create_flag(admin_token: str, *, flag_type: str = "bool") -> Dict[str, Any]:
    key = unique_key("test.flag")
    payload = {
        "key": key,
        "type": flag_type,
        "default_value": False if flag_type == "bool" else ("0" if flag_type == "number" else "off"),
        "description": "test flag for events",
    }
    r = post(f"{FLAGS_PATH}/", token=admin_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create flag failed: {r.status_code} {r.text}")
    return r.json()


def experiment_payload(feature_flag_id: str, *, traffic: float = 100.0) -> Dict[str, Any]:
    return {
        "name": f"Experiment {uuid.uuid4().hex[:8]}",
        "description": "test experiment for events",
        "feature_flag_id": feature_flag_id,
        "traffic_percentage": traffic,
        "targeting_rule": None,
        "variants": [
            {"name": "control", "value": "false", "weight": traffic * 0.5, "is_control": True},
            {"name": "treatment", "value": "true", "weight": traffic * 0.5, "is_control": False},
        ],
    }


def create_running_experiment(exp_token: str, admin_token: str) -> Dict[str, Any]:
    """
    Создаём flag -> experiment -> submit -> review approve -> start.
    """
    flag = create_flag(admin_token, flag_type="bool")

    # create DRAFT
    payload = experiment_payload(flag["id"], traffic=100.0)
    r = post(f"{EXPERIMENTS_PATH}/", token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create experiment failed: {r.status_code} {r.text}")
    exp = r.json()

    # submit -> IN_REVIEW
    r = post(f"{EXPERIMENTS_PATH}/{exp['id']}/submit",
             token=exp_token, json={"comment": "pls approve"})
    assert_ok(r.status_code == 200, f"Submit failed: {r.status_code} {r.text}")

    # review approve (админ)
    r = post(
        f"{EXPERIMENTS_PATH}/{exp['id']}/review",
        token=admin_token,
        json={"decision": "approve", "comment": "ok"},
    )
    assert_ok(r.status_code == 200, f"Review approve failed: {r.status_code} {r.text}")

    # start -> RUNNING
    r = post(f"{EXPERIMENTS_PATH}/{exp['id']}/start", token=exp_token, json=None)
    assert_ok(r.status_code == 200, f"Start failed: {r.status_code} {r.text}")
    exp = r.json()

    assert_ok(exp["status"] == "running", f"Expected RUNNING, got: {exp.get('status')}")
    return {"experiment": exp, "flag": flag}


def decide_one(flag_key: str, subject_id: str) -> Dict[str, Any]:
    payload = {
        "subject_id": subject_id,
        "flags": [flag_key],
        "attributes": {"country": "nl", "age": 25},
    }
    r = post(f"{DECIDE_PATH}", json=payload)
    assert_ok(r.status_code == 200, f"Decide failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok(data.get("decisions") and isinstance(
        data["decisions"], list), f"Bad decide response: {data}")
    return data["decisions"][0]


# -------------------------
# Fixtures: event types
# -------------------------

def ensure_event_type(admin_token: str, key: str, *, requires_exposure: bool) -> Dict[str, Any]:
    """
    Создаёт type если нет. Если уже есть — игнорируем.
    """
    payload = {"key": key, "description": f"test type {key}",
               "requires_exposure": requires_exposure}
    r = post(f"{EVENTS_PATH}/types", token=admin_token, json=payload)

    if r.status_code in (200, 201):
        return r.json()

    # если уже существует, твой сервис сейчас возвращает 422 "already exists"
    # (вместо 409). Поддержим оба.
    assert_ok(
        r.status_code in (409, 422),
        f"Create event type {key} failed unexpectedly: {r.status_code} {r.text}"
    )
    # get
    g = get(f"{EVENTS_PATH}/types/{key}", token=admin_token)
    assert_ok(g.status_code == 200, f"Get event type failed: {g.status_code} {g.text}")
    return g.json()


# -------------------------
# Events tests
# -------------------------

def test_event_types_crud(admin_token: str):
    # create
    key = unique_key("test.event_type")
    r = post(
        f"{EVENTS_PATH}/types",
        token=admin_token,
        json={"key": key, "description": "type desc", "requires_exposure": True},
    )
    assert_ok(r.status_code in (200, 201), f"Create event type failed: {r.status_code} {r.text}")
    et = r.json()
    assert_ok(et["key"] == key, f"key mismatch: {et}")
    assert_ok(et["requires_exposure"] is True, f"requires_exposure mismatch: {et}")

    # list
    r = get(f"{EVENTS_PATH}/types", token=admin_token, params={"offset": 0, "limit": 50})
    assert_ok(r.status_code == 200, f"List event types failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("items" in data and "total" in data, f"List shape invalid: {data}")
    keys = [it.get("key") for it in data["items"]]
    assert_ok(key in keys, f"Created event type not found in list. keys={keys}")

    # get
    r = get(f"{EVENTS_PATH}/types/{key}", token=admin_token)
    assert_ok(r.status_code == 200, f"Get event type failed: {r.status_code} {r.text}")
    got = r.json()
    assert_ok(got["key"] == key, f"Get key mismatch: {got}")

    # update (через query params, как у тебя сейчас)
    r = patch(
        f"{EVENTS_PATH}/types/{key}",
        token=admin_token,
        params={"description": "updated", "requires_exposure": "false"},
    )
    assert_ok(r.status_code == 200, f"Patch event type failed: {r.status_code} {r.text}")
    upd = r.json()
    assert_ok(upd["description"] == "updated", f"description not updated: {upd}")
    assert_ok(upd["requires_exposure"] is False, f"requires_exposure not updated: {upd}")

    # archive
    r = post(f"{EVENTS_PATH}/types/{key}/archive", token=admin_token, json=None)
    assert_ok(r.status_code == 200, f"Archive event type failed: {r.status_code} {r.text}")
    archived = r.json()
    assert_ok(archived.get("is_active") is False,
              f"Expected is_active=false after archive: {archived}")

    # list without inactive should NOT include
    r = get(f"{EVENTS_PATH}/types", token=admin_token, params={"offset": 0, "limit": 50})
    assert_ok(r.status_code == 200, f"List event types failed: {r.status_code} {r.text}")
    data = r.json()
    keys = [it.get("key") for it in data["items"]]
    assert_ok(key not in keys, "Archived type should be hidden when include_inactive=false")

    # list include_inactive should include
    r = get(f"{EVENTS_PATH}/types", token=admin_token,
            params={"offset": 0, "limit": 50, "include_inactive": True})
    assert_ok(r.status_code == 200, f"List include_inactive failed: {r.status_code} {r.text}")
    data = r.json()
    keys = [it.get("key") for it in data["items"]]
    assert_ok(key in keys, "Archived type should appear when include_inactive=true")

    print("✅ test_event_types_crud")


def test_ingest_events_happy_path(admin_token: str, exp_token: str):
    # ensure base types exist
    ensure_event_type(admin_token, "exposure", requires_exposure=False)
    ensure_event_type(admin_token, "click", requires_exposure=True)

    # create running experiment and get decision_id via /decide
    pack = create_running_experiment(exp_token, admin_token)
    flag = pack["flag"]
    subject_id = f"user_{uuid.uuid4().hex[:8]}"

    d0 = decide_one(flag["key"], subject_id)
    decision_id = d0["meta"]["decision_id"]

    # ingest batch: exposure + click
    payload = {
        "events": [
            {
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
                "decision_id": decision_id,
                "event_name": "exposure",
                "ts": "2026-02-24T10:00:00Z",
                "props": {"sdk": "py", "v": 1},
            },
            {
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
                "decision_id": decision_id,
                "event_name": "click",
                "ts": "2026-02-24T10:01:00Z",
                "props": {"button": "buy"},
            },
        ]
    }

    r = post(f"{EVENTS_PATH}", json=payload)
    assert_ok(r.status_code == 200, f"Ingest failed: {r.status_code} {r.text}")
    res = r.json()

    assert_ok(res["accepted"] == 2, f"Expected accepted=2, got: {res}")
    assert_ok(res["duplicates"] == 0, f"Expected duplicates=0, got: {res}")
    assert_ok(res["rejected"] == 0, f"Expected rejected=0, got: {res}")
    assert_ok(isinstance(res.get("errors", []), list), f"errors must be list: {res}")

    print("✅ test_ingest_events_happy_path")
    return decision_id


def test_ingest_events_duplicates(admin_token: str, exp_token: str):
    ensure_event_type(admin_token, "exposure", requires_exposure=False)

    pack = create_running_experiment(exp_token, admin_token)
    flag = pack["flag"]
    subject_id = f"user_{uuid.uuid4().hex[:8]}"
    d0 = decide_one(flag["key"], subject_id)
    decision_id = d0["meta"]["decision_id"]

    idem = f"idem_{uuid.uuid4().hex}"

    payload = {
        "events": [
            {
                "idempotency_key": idem,
                "decision_id": decision_id,
                "event_name": "exposure",
                "ts": "2026-02-24T10:00:00Z",
                "props": {"a": 1},
            }
        ]
    }

    # first insert
    r = post(f"{EVENTS_PATH}", json=payload)
    assert_ok(r.status_code == 200, f"Ingest1 failed: {r.status_code} {r.text}")
    res1 = r.json()
    assert_ok(res1["accepted"] == 1, f"Expected accepted=1, got: {res1}")

    # second insert same idempotency_key -> duplicate
    r = post(f"{EVENTS_PATH}", json=payload)
    assert_ok(r.status_code == 200, f"Ingest2 failed: {r.status_code} {r.text}")
    res2 = r.json()
    assert_ok(res2["accepted"] == 0, f"Expected accepted=0, got: {res2}")
    assert_ok(res2["duplicates"] == 1, f"Expected duplicates=1, got: {res2}")
    assert_ok(res2["rejected"] == 0, f"Expected rejected=0, got: {res2}")

    dup_key = f"dup_{uuid.uuid4().hex}"
    # duplicates inside same batch
    payload2 = {
        "events": [
            {
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
                "decision_id": decision_id,
                "event_name": "exposure",
                "ts": "2026-02-24T10:05:00Z",
            },
            {
                "idempotency_key": dup_key,
                "decision_id": decision_id,
                "event_name": "exposure",
                "ts": "2026-02-24T10:06:00Z",
            },
            {
                "idempotency_key": dup_key,
                "decision_id": decision_id,
                "event_name": "exposure",
                "ts": "2026-02-24T10:07:00Z",
            },
        ]
    }

    r = post(f"{EVENTS_PATH}", json=payload2)
    assert_ok(r.status_code == 200, f"Ingest batch dup failed: {r.status_code} {r.text}")
    res3 = r.json()
    assert_ok(res3["accepted"] == 2, f"Expected accepted=2 (2 unique), got: {res3}")
    assert_ok(res3["duplicates"] == 1, f"Expected duplicates=1 (in-batch), got: {res3}")

    print("✅ test_ingest_events_duplicates")


def test_ingest_events_validation_errors(admin_token: str, exp_token: str):
    ensure_event_type(admin_token, "exposure", requires_exposure=False)

    pack = create_running_experiment(exp_token, admin_token)
    flag = pack["flag"]
    subject_id = f"user_{uuid.uuid4().hex[:8]}"
    d0 = decide_one(flag["key"], subject_id)
    decision_id = d0["meta"]["decision_id"]

    # 1) missing required fields in body -> 422 from schema
    r = post(f"{EVENTS_PATH}", json={})
    assert_ok(r.status_code == 422, f"Expected 422 on empty body, got {r.status_code} {r.text}")

    # 2) unknown event type -> should be rejected in ingest result (200)
    payload = {
        "events": [
            {
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
                "decision_id": decision_id,
                "event_name": "unknown_event_type_xxx",
                "ts": "2026-02-24T10:00:00Z",
            }
        ]
    }
    r = post(f"{EVENTS_PATH}", json=payload)
    assert_ok(r.status_code == 200,
              f"Expected 200 with rejected item, got {r.status_code} {r.text}")
    res = r.json()
    assert_ok(res["accepted"] == 0, f"accepted should be 0: {res}")
    assert_ok(res["rejected"] == 1, f"rejected should be 1: {res}")
    assert_ok(len(res.get("errors", [])) == 1, f"Expected one error: {res}")
    assert_ok("unknown" in (res["errors"][0]["error"] or "").lower(),
              f"Expected unknown type error: {res}")

    # 3) decision not found -> rejected
    payload = {
        "events": [
            {
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
                "decision_id": str(uuid.uuid4()),
                "event_name": "exposure",
                "ts": "2026-02-24T10:00:00Z",
            }
        ]
    }
    r = post(f"{EVENTS_PATH}", json=payload)
    assert_ok(r.status_code == 200,
              f"Expected 200 with rejected item, got {r.status_code} {r.text}")
    res = r.json()
    assert_ok(res["accepted"] == 0, f"accepted should be 0: {res}")
    assert_ok(res["rejected"] == 1, f"rejected should be 1: {res}")
    assert_ok("decision" in (res["errors"][0]["error"] or "").lower(),
              f"Expected decision not found: {res}")

    print("✅ test_ingest_events_validation_errors")


def test_ingest_requires_exposure_out_of_order(admin_token: str, exp_token: str):
    """
    Проверяем поведение requires_exposure:
    - click (requires_exposure=True) может прийти до exposure
    - мы всё равно принимаем (по твоей реализации), чтобы поддерживать out-of-order
    """
    ensure_event_type(admin_token, "exposure", requires_exposure=False)
    ensure_event_type(admin_token, "click", requires_exposure=True)

    pack = create_running_experiment(exp_token, admin_token)
    flag = pack["flag"]
    subject_id = f"user_{uuid.uuid4().hex[:8]}"
    d0 = decide_one(flag["key"], subject_id)
    decision_id = d0["meta"]["decision_id"]

    payload = {
        "events": [
            {
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
                "decision_id": decision_id,
                "event_name": "click",
                "ts": "2026-02-24T10:01:00Z",
            },
            {
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
                "decision_id": decision_id,
                "event_name": "exposure",
                "ts": "2026-02-24T10:00:00Z",
            },
        ]
    }

    r = post(f"{EVENTS_PATH}", json=payload)
    assert_ok(r.status_code == 200, f"Ingest failed: {r.status_code} {r.text}")
    res = r.json()
    assert_ok(res["accepted"] == 2, f"Expected accepted=2 for out-of-order, got: {res}")
    assert_ok(res["rejected"] == 0, f"Expected rejected=0, got: {res}")

    print("✅ test_ingest_requires_exposure_out_of_order")


def test_event_types_forbidden_for_non_admin(exp_token: str):
    key = unique_key("test.event_type.forbidden")
    r = post(
        f"{EVENTS_PATH}/types",
        token=exp_token,
        json={"key": key, "description": "x", "requires_exposure": False},
    )
    assert_ok(r.status_code == 403, f"Expected 403 for non-admin, got {r.status_code} {r.text}")
    print("✅ test_event_types_forbidden_for_non_admin")


# -------------------------
# Main
# -------------------------

def main():
    print(f"BASE_URL={BASE_URL}")
    print(f"AUTH_LOGIN_PATH={AUTH_LOGIN_PATH}")
    print(f"EVENTS_PATH={EVENTS_PATH}")
    print(f"DECIDE_PATH={DECIDE_PATH}")

    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    _, exp_token = ensure_user_exists(admin_token, EXP_EMAIL, EXP_PASSWORD, role="experimenter")
    _, viewer_token = ensure_user_exists(admin_token, VIEWER_EMAIL, VIEWER_PASSWORD, role="viewer")

    # # -------------------------
    # # Run tests
    # # -------------------------
    test_event_types_crud(admin_token)
    test_event_types_forbidden_for_non_admin(exp_token)

    test_ingest_events_validation_errors(admin_token, exp_token)
    test_ingest_events_happy_path(admin_token, exp_token)
    test_ingest_events_duplicates(admin_token, exp_token)
    test_ingest_requires_exposure_out_of_order(admin_token, exp_token)

    print("\n✅✅✅ ALL EVENTS TESTS PASSED")


# if __name__ == "__main__":
main()
