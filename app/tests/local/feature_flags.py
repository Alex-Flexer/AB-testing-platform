import os
import time
import uuid
import requests


BASE_URL = "http://127.0.0.1:80"

AUTH_LOGIN_PATH = "/auth/login"
FLAGS_PATH = "/flags/"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mail.ru")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

USER_EMAIL = os.getenv("USER_EMAIL", "viewer@mail.ru")
USER_PASSWORD = os.getenv("USER_PASSWORD", "viewer123")


# -------------------------
# helpers
# -------------------------

def assert_ok(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def http_json(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text}


def assert_status(resp: requests.Response, expected: int):
    assert_ok(
        resp.status_code == expected,
        f"Expected status {expected}, got {resp.status_code}. Body: {resp.text}",
    )


def assert_detail_contains(resp: requests.Response, needle: str):
    data = http_json(resp)
    detail = data.get("detail")
    assert_ok(detail is not None, f"No 'detail' in response: {data}")
    assert_ok(
        needle.lower() in str(detail).lower(),
        f"Expected detail to contain '{needle}', got '{detail}'",
    )


def login(email: str, password: str) -> str:
    resp = requests.post(
        f"{BASE_URL}{AUTH_LOGIN_PATH}",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert_status(resp, 200)
    data = http_json(resp)
    assert_ok("access_token" in data, f"No access_token in response: {data}")
    return data["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def unique_key(prefix: str = "flag") -> str:
    # ключ должен начинаться с буквы по твоей валидации
    # пример: f_ab12cd...
    return f"f_{prefix}_{uuid.uuid4().hex[:10]}"


# -------------------------
# API wrappers
# -------------------------

def create_flag(token: str, payload: dict) -> requests.Response:
    return requests.post(
        f"{BASE_URL}{FLAGS_PATH}",
        json=payload,
        headers=auth_headers(token),
        timeout=10,
    )


def get_flag(token: str, flag_id: str) -> requests.Response:
    return requests.get(
        f"{BASE_URL}{FLAGS_PATH}{flag_id}",
        headers=auth_headers(token),
        timeout=10,
    )


def list_flags(token: str, offset: int = 0, limit: int = 50) -> requests.Response:
    return requests.get(
        f"{BASE_URL}{FLAGS_PATH}?offset={offset}&limit={limit}",
        headers=auth_headers(token),
        timeout=10,
    )


def patch_flag(token: str, flag_id: str, payload: dict) -> requests.Response:
    return requests.patch(
        f"{BASE_URL}{FLAGS_PATH}{flag_id}",
        json=payload,
        headers=auth_headers(token),
        timeout=10,
    )


def delete_flag(token: str, flag_id: str) -> requests.Response:
    return requests.delete(
        f"{BASE_URL}{FLAGS_PATH}{flag_id}",
        headers=auth_headers(token),
        timeout=10,
    )


# -------------------------
# tests
# -------------------------

def test_auth_smoke():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    assert_ok(isinstance(admin_token, str) and len(admin_token) > 10, "admin token looks invalid")
    print("[OK] auth admin")

    user_token = login(USER_EMAIL, USER_PASSWORD)
    assert_ok(isinstance(user_token, str) and len(user_token) > 10, "user token looks invalid")
    print("[OK] auth non-admin")


def test_admin_can_create_get_list_patch_delete():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    key = unique_key("bool")
    payload = {
        "key": key,
        "type": "bool",
        "default_value": False,
        "description": "test flag",
    }

    # CREATE
    r = create_flag(admin_token, payload)
    assert_status(r, 200)
    data = http_json(r)

    flag_id = data.get("id")
    assert_ok(flag_id, f"Missing id in create response: {data}")
    assert_ok(data["key"] == key, f"key mismatch: {data}")
    assert_ok(data["type"] == "bool" or data["type"] == "FlagType.BOOL", f"type mismatch: {data}")
    assert_ok(data["default_value"] in ("false", "true"),
              f"default_value should be stringified bool: {data}")
    assert_ok(data["default_value"] == "false", f"default_value should be 'false': {data}")

    print("[OK] create flag")

    # GET
    r = get_flag(admin_token, flag_id)
    assert_status(r, 200)
    got = http_json(r)
    assert_ok(got["id"] == flag_id, "get returned different flag id")
    assert_ok(got["key"] == key, "get returned different key")
    print("[OK] get flag")

    # LIST
    r = list_flags(admin_token, offset=0, limit=10)
    assert_status(r, 200)
    lst = http_json(r)
    assert_ok("items" in lst and "total" in lst, f"list response shape invalid: {lst}")
    assert_ok(isinstance(lst["items"], list), f"items must be list: {lst}")
    assert_ok(isinstance(lst["total"], int), f"total must be int: {lst}")
    assert_ok(any(item["id"] == flag_id for item in lst["items"]), "created flag not found in list")
    print("[OK] list flags")

    # PATCH (default_value only)
    r = patch_flag(admin_token, flag_id, {"default_value": True})
    assert_status(r, 200)
    patched = http_json(r)
    assert_ok(patched["default_value"] == "true",
              f"patch should set default_value to 'true': {patched}")
    print("[OK] patch flag")

    # DELETE
    r = delete_flag(admin_token, flag_id)
    assert_status(r, 200)
    body = http_json(r)
    assert_ok(body.get("ok") is True, f"delete response invalid: {body}")
    print("[OK] delete flag")

    # GET after delete -> 404
    r = get_flag(admin_token, flag_id)
    assert_status(r, 404)
    print("[OK] get deleted -> 404")


def test_non_admin_forbidden_everywhere():
    user_token = login(USER_EMAIL, USER_PASSWORD)

    key = unique_key("forbidden")
    payload = {"key": key, "type": "string", "default_value": "x"}

    # CREATE -> 403
    r = create_flag(user_token, payload)
    assert_status(r, 403)
    print("[OK] non-admin create -> 403")

    # LIST -> 403
    r = list_flags(user_token, 0, 10)
    assert_status(r, 403)
    print("[OK] non-admin list -> 403")


def test_create_duplicate_key_conflict():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    key = unique_key("dup")

    payload = {"key": key, "type": "string", "default_value": "v1"}
    r1 = create_flag(admin_token, payload)
    assert_status(r1, 200)
    flag_id = http_json(r1)["id"]

    # duplicate
    r2 = create_flag(admin_token, payload)
    assert_status(r2, 409)
    assert_detail_contains(r2, "already exists")
    print("[OK] duplicate key -> 409")

    # cleanup
    delete_flag(admin_token, flag_id)


def test_create_validation_errors_422():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    # bad key (starts with digit)
    r = create_flag(admin_token, {"key": "1_bad", "type": "bool", "default_value": True})
    assert_status(r, 422)
    print("[OK] invalid key -> 422")

    # bad type
    r = create_flag(admin_token, {"key": unique_key("badtype"),
                    "type": "unknown", "default_value": "x"})
    assert_status(r, 422)
    print("[OK] invalid type -> 422")

    # bool type but default_value not bool-ish after normalization
    # (у тебя DefaultValue приводит число/строку, но валидатор create требует true/false)
    r = create_flag(admin_token, {"key": unique_key("boolbad"),
                    "type": "bool", "default_value": "yes"})
    assert_status(r, 422)
    print("[OK] bool default_value invalid -> 422")

    # number type invalid format
    r = create_flag(admin_token, {"key": unique_key("numbad"),
                    "type": "number", "default_value": "12..3"})
    assert_status(r, 422)
    print("[OK] number default_value invalid -> 422")


def test_patch_validation_by_type_422():
    """
    Важно: PATCH не знает type из тела, значит валидация должна быть в сервисе
    (мы это и сделали: _validate_default_value_for_type).
    """
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    # create number flag
    key = unique_key("num")
    r = create_flag(admin_token, {"key": key, "type": "number", "default_value": 1})
    assert_status(r, 200)
    flag_id = http_json(r)["id"]

    # patch invalid number
    r = patch_flag(admin_token, flag_id, {"default_value": "abc"})
    assert_status(r, 422)
    print("[OK] patch invalid default_value for number -> 422")

    # patch valid number
    r = patch_flag(admin_token, flag_id, {"default_value": "-12.5"})
    assert_status(r, 200)
    patched = http_json(r)
    assert_ok(patched["default_value"] == "-12.5", f"unexpected patched value: {patched}")
    print("[OK] patch valid number -> 200")

    delete_flag(admin_token, flag_id)


def test_patch_only_default_value():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    key = unique_key("only")
    r = create_flag(admin_token, {"key": key, "type": "string", "default_value": "v"})
    assert_status(r, 200)
    flag_id = http_json(r)["id"]

    # try to patch forbidden fields (type/key/description)
    r = patch_flag(admin_token, flag_id, {"type": "bool"})
    # BodyModel у тебя может ругнуться на unknown fields, если он strict.
    # Либо FastAPI/Pydantic вернёт 422. В любом случае — должно быть не 200.
    assert_ok(r.status_code in (422, 400),
              f"expected 4xx for patching forbidden field, got {r.status_code}: {r.text}")
    print("[OK] patch forbidden field -> 4xx")

    # patch empty body
    r = patch_flag(admin_token, flag_id, {})
    assert_ok(r.status_code in (422, 400),
              f"expected 4xx for empty patch, got {r.status_code}: {r.text}")
    print("[OK] patch empty body -> 4xx")

    delete_flag(admin_token, flag_id)


def test_list_pagination_validation():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    r = list_flags(admin_token, offset=-1, limit=10)
    assert_status(r, 422)  # если ты валидируешь offset/limit в сервисе через UnprocessableEntity
    print("[OK] list offset < 0 -> 422")

    r = list_flags(admin_token, offset=0, limit=0)
    assert_status(r, 422)
    print("[OK] list limit 0 -> 422")

    r = list_flags(admin_token, offset=0, limit=9999)
    assert_status(r, 422)
    print("[OK] list limit too big -> 422")


def test_not_found_404():
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)

    missing_id = str(uuid.uuid4())

    r = get_flag(admin_token, missing_id)
    assert_status(r, 404)
    print("[OK] get missing -> 404")

    r = patch_flag(admin_token, missing_id, {"default_value": "x"})
    assert_status(r, 404)
    print("[OK] patch missing -> 404")

    r = delete_flag(admin_token, missing_id)
    assert_status(r, 404)
    print("[OK] delete missing -> 404")


def run_all():
    print("BASE_URL:", BASE_URL)

    # чтобы сервер успел подняться, если запускаешь всё подряд
    time.sleep(0.2)

    test_auth_smoke()
    test_non_admin_forbidden_everywhere()
    test_admin_can_create_get_list_patch_delete()
    test_create_duplicate_key_conflict()
    test_create_validation_errors_422()
    test_patch_validation_by_type_422()
    test_patch_only_default_value()
    test_list_pagination_validation()
    test_not_found_404()

    print("\nALL FLAGS TESTS PASSED ✅")


run_all()
