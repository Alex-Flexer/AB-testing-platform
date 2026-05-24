import os
import uuid
import requests
from typing import Dict, Any


BASE_URL = "http://127.0.0.1:80"

AUTH = "/auth/login"
USERS = "/users"
FLAGS = "/flags"
METRICS = "/metrics"
EXPERIMENTS = "/experiments"
REPORTS = "/reports"
DECIDE = "/decide"
EVENTS = "/events"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mail.ru")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


TIMEOUT = 10


# -------------------------
# utils
# -------------------------

def assert_ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def post(path, token=None, json=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(BASE_URL + path, json=json, headers=headers, timeout=TIMEOUT)


def get(path, token=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(BASE_URL + path, headers=headers, timeout=TIMEOUT)


def login(email, password):
    r = post(AUTH, json={"email": email, "password": password})
    assert_ok(r.status_code == 200, f"Login failed {r.text}")
    return r.json()["access_token"]


# -------------------------
# helpers
# -------------------------

def create_flag(admin_token) -> Dict[str, Any]:
    key = f"flag_{uuid.uuid4().hex[:8]}"
    r = post(FLAGS, token=admin_token, json={
        "key": key,
        "type": "bool",
        "default_value": False,
        "description": "test flag"
    })
    assert_ok(r.status_code in (200, 201), r.text)
    return r.json()


def get_flag_key(admin_token, flag_id):
    r = get(f"{FLAGS}/{flag_id}", token=admin_token)
    assert_ok(r.status_code == 200, r.text)
    return r.json()["key"]


def create_metric(admin_token, key, aggregation_type,
                  numerator=None, denominator=None):
    r = post(METRICS, token=admin_token, json={
        "key": key,
        "name": key,
        "aggregation_type": aggregation_type,
        "numerator_event": numerator,
        "denominator_event": denominator
    })
    assert_ok(r.status_code in (200, 201), r.text)
    return r.json()


def experiment_payload(feature_flag_id: str, *, traffic: float = 100.0) -> dict:
    return {
        "name": f"Experiment {uuid.uuid4().hex[:8]}",
        "description": "test experiment",
        "feature_flag_id": feature_flag_id,
        "traffic_percentage": traffic,
        "targeting_rule": None,
        "variants": [
            {
                "name": "control",
                "value": "false",
                "weight": traffic * 0.5,
                "is_control": True,
            },
            {
                "name": "treatment",
                "value": "true",
                "weight": traffic * 0.5,
                "is_control": False,
            },
        ],
    }


def create_experiment(exp_token, admin_token):
    flag = create_flag(admin_token)

    payload = {
        "name": "exp_" + uuid.uuid4().hex[:6],
        "description": "report test",
        "feature_flag_id": flag["id"],
        "traffic_percentage": 100.0,
        "targeting_rule": None,
        "variants": [
            {"name": "control", "value": "false", "weight": 50.0, "is_control": True},
            {"name": "treatment", "value": "true", "weight": 50.0, "is_control": False},
        ],
    }

    r = post(EXPERIMENTS, token=exp_token, json=payload)
    assert_ok(r.status_code in (200, 201), r.text)
    exp = r.json()

    # submit
    r = post(f"{EXPERIMENTS}/{exp['id']}/submit", token=exp_token, json={})
    assert_ok(r.status_code == 200, r.text)

    # review (admin assumed APPROVER or allowed)
    r = post(f"{EXPERIMENTS}/{exp['id']}/review",
             token=admin_token,
             json={"decision": "approve", "comment": "ok"})
    assert_ok(r.status_code == 200, r.text)

    # start
    r = post(f"{EXPERIMENTS}/{exp['id']}/start", token=exp_token)
    assert_ok(r.status_code == 200, r.text)

    return exp, flag


def decide(flag_key, subject):
    r = post(DECIDE, json={
        "subject_id": subject,
        "flags": [flag_key],
        "attributes": {}
    })
    assert_ok(r.status_code == 200, r.text)
    d = r.json()["decisions"][0]
    assert_ok(d["meta"]["is_default"] is False, "Experiment not applied")
    return d["meta"]["decision_id"]


def ingest(decision_id, name, ts):
    return post(EVENTS, json={
        "events": [{
            "idempotency_key": uuid.uuid4().hex,
            "decision_id": decision_id,
            "event_name": name,
            "ts": ts
        }]
    })


def report(exp_id, payload, token):
    r = post(f"{REPORTS}/experiments/{exp_id}", json=payload, token=token)
    assert_ok(r.status_code == 200, r.text)
    return r.json()


# -------------------------
# TESTS
# -------------------------

def test_basic_count_and_rate(admin_token, exp_token):
    exp, flag = create_experiment(exp_token, admin_token)

    try:
        m_click = create_metric(admin_token, "m_click", "count", numerator="click")
        m_ctr = create_metric(
            admin_token, "m_ctr", "rate",
            numerator="click",
            denominator="exposure"
        )
    except Exception:
        # при повторном создании может вылезти ошибка
        pass

    flag_key = get_flag_key(admin_token, flag["id"])

    subject = "user_" + uuid.uuid4().hex[:6]
    decision_id = decide(flag_key, subject)

    ingest(decision_id, "exposure", "2026-02-24T10:00:00Z")
    ingest(decision_id, "exposure", "2026-02-24T10:01:00Z")
    ingest(decision_id, "click", "2026-02-24T10:02:00Z")

    rep = report(exp["id"], {
        "from_ts": "2026-02-24T09:00:00Z",
        "to_ts": "2026-02-24T11:00:00Z",
        "metric_keys": ["m_click", "m_ctr"],
        "include_timeseries": False
    }, token=admin_token)

    variants = rep["variants"]

    print(rep)

    # найдём вариант с кликом
    v = next(v for v in variants if v["metrics"]["m_click"]["raw"] == 1.0)

    assert_ok(v["metrics"]["m_click"]["raw"] == 1.0, "Click count mismatch")
    assert_ok(abs(v["metrics"]["m_ctr"]["raw"] - 0.5) < 1e-9, "CTR mismatch")

    print("✅ test_basic_count_and_rate")


def test_timeseries(admin_token, exp_token):
    exp, flag = create_experiment(exp_token, admin_token)

    try:
        create_metric(admin_token, "m_click_ts", "count", numerator="click")
    except Exception:
        pass

    flag_key = get_flag_key(admin_token, flag["id"])
    subject = "user_" + uuid.uuid4().hex[:6]
    decision_id = decide(flag_key, subject)

    ingest(decision_id, "click", "2026-02-24T10:10:00Z")
    ingest(decision_id, "click", "2026-02-24T11:10:00Z")

    rep = report(exp["id"], {
        "from_ts": "2026-02-24T10:00:00Z",
        "to_ts": "2026-02-24T12:00:00Z",
        "metric_keys": ["m_click_ts"],
        "include_timeseries": True,
        "granularity": "hour"
    }, token=admin_token)

    ts = rep["timeseries"]
    assert_ok(ts is not None, "Timeseries missing")

    found = False
    for v in ts:
        for s in v["series"]:
            vals = [p["value"] for p in s["points"]]
            if sum(vals) == 2.0:
                found = True

    assert_ok(found, "Timeseries aggregation incorrect")

    print("✅ test_timeseries")


def main():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    exp_token = admin_token

    test_basic_count_and_rate(admin_token, exp_token)
    test_timeseries(admin_token, exp_token)

    print("\n✅ ALL REPORT TESTS PASSED")


main()
