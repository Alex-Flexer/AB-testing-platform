import os
import uuid
import requests

BASE_URL = "http://127.0.0.1:80"
TIMEOUT = 10.0

AUTH_LOGIN_PATH = "/auth/login"

DECIDE_PATH = "/decide"

FLAGS_PATH = "/flags"

EXPERIMENTS_PATH = os.getenv("EXPERIMENTS_PATH", "/experiments")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mail.ru")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

APPROVER_EMAIL = os.getenv("APPROVER_EMAIL", ADMIN_EMAIL)
APPROVER_PASSWORD = os.getenv("APPROVER_PASSWORD", ADMIN_PASSWORD)


def assert_ok(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def http(method: str, path: str, token: str | None = None, **kwargs) -> requests.Response:
    url = f"{BASE_URL}{path}"
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)


def login(email: str, password: str) -> str:
    r = http("POST", AUTH_LOGIN_PATH, json={"email": email, "password": password})
    assert_ok(r.status_code == 200, f"Login failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("access_token" in data, f"Missing access_token: {data}")
    return data["access_token"]


def create_flag(token: str, *, key: str, flag_type: str = "string", default_value="off"):
    payload = {
        "key": key,
        "type": flag_type,
        "default_value": default_value,
        "description": "test flag",
    }

    # попробуем / и без /
    r = http("POST", f"{FLAGS_PATH}/", token, json=payload)
    if r.status_code == 404:
        r = http("POST", f"{FLAGS_PATH}", token, json=payload)

    assert_ok(r.status_code in (200, 201), f"Create flag failed: {r.status_code} {r.text}")
    return r.json()


def create_experiment(token: str, *, flag_id: str, name: str, traffic: float, variants: list[dict]):
    payload = {
        "name": name,
        "description": "test experiment",
        "feature_flag_id": flag_id,
        "traffic_percentage": traffic,
        "targeting_rule": None,
        "variants": variants,
    }
    r = http("POST", f"{EXPERIMENTS_PATH}/", token, json=payload)
    assert_ok(r.status_code in (200, 201), f"Create experiment failed: {r.status_code} {r.text}")
    return r.json()


def submit_experiment(token: str, experiment_id: str, comment: str = "submit"):
    r = http("POST", f"{EXPERIMENTS_PATH}/{experiment_id}/submit", token, json={"comment": comment})
    assert_ok(r.status_code == 200, f"Submit failed: {r.status_code} {r.text}")
    return r.json()


def review_experiment(token: str, experiment_id: str, decision: str = "approve", comment: str = "ok"):
    # decision значения: approve/reject/request_changes (ReviewDecision)
    r = http(
        "POST",
        f"{EXPERIMENTS_PATH}/{experiment_id}/review",
        token,
        json={"decision": decision, "comment": comment},
    )
    assert_ok(r.status_code == 200, f"Review failed: {r.status_code} {r.text}")
    return r.json()


def start_experiment(token: str, experiment_id: str):
    r = http("POST", f"{EXPERIMENTS_PATH}/{experiment_id}/start", token)
    assert_ok(r.status_code == 200, f"Start failed: {r.status_code} {r.text}")
    return r.json()


def decide(subject_id: str, flags: list[str], *, attributes: dict | None = None, token: str | None = None):
    payload = {"subject_id": subject_id, "flags": flags, "attributes": attributes}
    return http("POST", DECIDE_PATH, token, json=payload)


def setup_running_experiment_for_flag(
    *,
    admin_token: str,
    approver_token: str,
    flag_key: str,
    default_value: str,
    traffic: float,
):
    flag = create_flag(admin_token, key=flag_key, flag_type="string", default_value=default_value)

    exp = create_experiment(
        admin_token,
        flag_id=flag["id"],
        name=f"exp_{uuid.uuid4().hex[:8]}",
        traffic=traffic,
        variants=[
            {"name": "control", "value": default_value, "weight": traffic / 2, "is_control": True},
            {"name": "treat", "value": "on", "weight": traffic / 2, "is_control": False},
        ],
    )

    submit_experiment(admin_token, exp["id"], comment="submit exp")
    review_experiment(approver_token, exp["id"], decision="approve", comment="ok")
    exp_running = start_experiment(admin_token, exp["id"])

    return flag, exp_running


# -------------------------
# tests
# -------------------------

def test_decide_requires_correct_body_422():
    # missing flags
    r = http("POST", DECIDE_PATH, json={"subject_id": "x"})
    assert_ok(r.status_code == 422, f"Expected 422, got {r.status_code} {r.text}")


def test_decide_unknown_flag_404():
    r = decide("user-1", ["does_not_exist"])
    assert_ok(r.status_code == 404, f"Expected 404, got {r.status_code} {r.text}")


def test_decide_default_when_experiment_not_running():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    flag_key = f"flag_{uuid.uuid4().hex[:8]}"
    create_flag(admin_token, key=flag_key, flag_type="string", default_value="off")

    r = decide("user-1", [flag_key])
    assert_ok(r.status_code == 200, f"Decide failed: {r.status_code} {r.text}")

    data = r.json()
    d = data["decisions"][0]
    assert_ok(d["flag_key"] == flag_key, "flag_key mismatch")
    assert_ok(d["value"] == "off", "should return flag default value")
    assert_ok(d["meta"]["is_default"] is True, "should be default (no running experiment)")
    # experiment_id/variant_id может быть None в default
    assert_ok(d["meta"]["experiment_id"] is None, "default should have experiment_id=None")


def test_decide_applies_experiment_and_is_sticky():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    approver_token = login(APPROVER_EMAIL, APPROVER_PASSWORD)

    flag_key = f"flag_{uuid.uuid4().hex[:8]}"
    flag, exp = setup_running_experiment_for_flag(
        admin_token=admin_token,
        approver_token=approver_token,
        flag_key=flag_key,
        default_value="off",
        traffic=100.0,
    )

    subject = f"user-{uuid.uuid4().hex[:6]}"

    r1 = decide(subject, [flag_key])
    assert_ok(r1.status_code == 200, f"Decide1 failed: {r1.status_code} {r1.text}")
    d1 = r1.json()["decisions"][0]

    assert_ok(d1["meta"]["is_default"] is False, "expected non-default due to running experiment")
    assert_ok(d1["meta"]["experiment_id"] == exp["id"], "experiment_id mismatch")
    assert_ok(d1["meta"]["variant_id"] is not None, "variant_id must be present")
    assert_ok(d1["meta"]["decision_id"] is not None, "decision_id must be present")
    assert_ok(d1["value"] in ("off", "on"), "unexpected value")

    # sticky
    r2 = decide(subject, [flag_key])
    assert_ok(r2.status_code == 200, f"Decide2 failed: {r2.status_code} {r2.text}")
    d2 = r2.json()["decisions"][0]

    assert_ok(d2["meta"]["decision_id"] == d1["meta"]["decision_id"], "decision_id must be sticky")
    assert_ok(d2["meta"]["variant_id"] == d1["meta"]["variant_id"], "variant_id must be sticky")
    assert_ok(d2["value"] == d1["value"], "value must be sticky")


def test_decide_traffic_less_than_100_has_some_default_and_some_applied():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    approver_token = login(APPROVER_EMAIL, APPROVER_PASSWORD)

    flag_key = f"flag_{uuid.uuid4().hex[:8]}"
    flag, exp = setup_running_experiment_for_flag(
        admin_token=admin_token,
        approver_token=approver_token,
        flag_key=flag_key,
        default_value="off",
        traffic=10.0,
    )

    N = 80
    defaults = 0
    applied = 0

    for _ in range(N):
        subject = f"user-{uuid.uuid4().hex[:10]}"
        r = decide(subject, [flag_key])
        assert_ok(r.status_code == 200, f"Decide failed: {r.status_code} {r.text}")
        dec = r.json()["decisions"][0]
        if dec["meta"]["is_default"]:
            defaults += 1
            assert_ok(dec["value"] == "off", "default should return flag default_value")
        else:
            applied += 1
            assert_ok(dec["meta"]["experiment_id"] == exp["id"], "experiment_id mismatch")
            assert_ok(dec["value"] in ("off", "on"), "unexpected applied value")

    assert_ok(defaults > 0, f"expected some defaults with traffic=10%, got {defaults}/{N}")
    assert_ok(applied > 0, f"expected some applied with traffic=10%, got {applied}/{N}")


def test_decide_multiple_flags_mixed_default_and_applied():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    approver_token = login(APPROVER_EMAIL, APPROVER_PASSWORD)

    flag_a_key = f"flag_{uuid.uuid4().hex[:8]}"
    create_flag(admin_token, key=flag_a_key, flag_type="string", default_value="A0")

    flag_b_key = f"flag_{uuid.uuid4().hex[:8]}"
    flag_b, exp_b = setup_running_experiment_for_flag(
        admin_token=admin_token,
        approver_token=approver_token,
        flag_key=flag_b_key,
        default_value="B0",
        traffic=100.0,
    )

    subject = f"user-{uuid.uuid4().hex[:6]}"

    r = decide(subject, [flag_a_key, flag_b_key])
    assert_ok(r.status_code == 200, f"Decide failed: {r.status_code} {r.text}")

    data = r.json()
    assert_ok(len(data["decisions"]) == 2, "expected 2 decisions")

    by_key = {d["flag_key"]: d for d in data["decisions"]}

    dA = by_key[flag_a_key]
    assert_ok(dA["meta"]["is_default"] is True, "flag A should be default")
    assert_ok(dA["value"] == "A0", "flag A value mismatch")

    dB = by_key[flag_b_key]
    assert_ok(dB["meta"]["is_default"] is False, "flag B should be applied")
    assert_ok(dB["meta"]["experiment_id"] == exp_b["id"], "flag B experiment mismatch")
    assert_ok(dB["value"] in ("B0", "on"), "flag B value unexpected")


def test_decide_auth_behavior_optional():
    """
    Если decide endpoint публичный — 200 без токена.
    Если защищён — будет 401/403.
    """
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    flag_key = f"flag_{uuid.uuid4().hex[:8]}"
    create_flag(admin_token, key=flag_key, flag_type="string", default_value="off")

    r = decide("user-1", [flag_key], token=None)
    assert_ok(r.status_code in (200, 401, 403), f"Unexpected status: {r.status_code} {r.text}")


# -------------------------
# runner
# -------------------------

def main():
    tests = [
        test_decide_requires_correct_body_422,
        test_decide_unknown_flag_404,
        test_decide_default_when_experiment_not_running,
        test_decide_applies_experiment_and_is_sticky,
        test_decide_traffic_less_than_100_has_some_default_and_some_applied,
        test_decide_multiple_flags_mixed_default_and_applied,
        test_decide_auth_behavior_optional,
    ]

    for t in tests:
        print(f"\n>>> RUN {t.__name__}")
        t()
        print(f"OK: {t.__name__}")

    print("\nALL DECISION TESTS PASSED")


main()
