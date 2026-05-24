import os
import requests
from random import randint


BASE_URL = "http://127.0.0.1:80"
AUTH_LOGIN_PATH = "/auth/login"
USERS_PATH = "/users"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@mail.ru")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def assert_ok(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def login_admin() -> str:
    r = requests.post(
        f"{BASE_URL}{AUTH_LOGIN_PATH}",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10
    )

    assert_ok(r.ok, f"Login failed: {r.status_code} {r.text}")

    data = r.json()

    assert_ok("access_token" in data, f"No access_token in response: {data}")

    return data["access_token"]


def main():
    token = login_admin()

    headers = {"Authorization": f"Bearer {token}"}

    uniq = "haha" + str(randint(1, 100))
    email = f"use{uniq}r@example.com"

    print("1) CREATE user")

    r = requests.post(
        f"{BASE_URL}{USERS_PATH}",
        json={"email": email, "role": "viewer", "password": "some password", "is_active": True},
        headers=headers,
        timeout=10,
    )
    assert_ok(r.ok, f"Create failed: {r.status_code} {r.text}")
    user = r.json()
    user_id = user["id"]
    print("   created:", user_id)

    print("2) GET user")
    r = requests.get(f"{BASE_URL}{USERS_PATH}/{user_id}", headers=headers, timeout=10)
    assert_ok(r.status_code == 200, f"Get failed: {r.status_code} {r.text}")
    got = r.json()
    assert_ok(got["email"] == email, "Email mismatch")

    print("3) LIST users")
    r = requests.get(f"{BASE_URL}{USERS_PATH}", params={
                     "offset": 0, "limit": 50}, headers=headers, timeout=10)
    assert_ok(r.status_code == 200, f"List failed: {r.status_code} {r.text}")
    data = r.json()
    assert_ok("items" in data and "total" in data, f"Unexpected list response: {data}")

    print("4) PATCH user")
    r = requests.patch(
        f"{BASE_URL}{USERS_PATH}/{user_id}",
        json={"role": "approver", "is_active": False},
        headers=headers,
        timeout=10,
    )
    assert_ok(r.status_code == 200, f"Patch failed: {r.status_code} {r.text}")
    updated = r.json()
    assert_ok(updated["role"] == "approver", "Role not updated")
    assert_ok(updated["is_active"] is False, "is_active not updated")

    print("5) Duplicate email must fail with 409")
    r = requests.post(
        f"{BASE_URL}{USERS_PATH}",
        json={"email": email, "role": "viewer", "is_active": True,
              "password": "some another password"},
        headers=headers,
        timeout=10,
    )
    assert_ok(r.status_code == 409, f"Expected 409, got: {r.status_code} {r.text}")

    print("6) DELETE user")
    r = requests.delete(f"{BASE_URL}{USERS_PATH}/{user_id}", headers=headers, timeout=10)
    assert_ok(r.status_code in (200, 204), f"Delete failed: {r.status_code} {r.text}")

    print("7) GET after delete must be 404")
    r = requests.get(f"{BASE_URL}{USERS_PATH}/{user_id}", headers=headers, timeout=10)
    assert_ok(r.status_code == 404, f"Expected 404, got: {r.status_code} {r.text}")

    print("✅ OK: admin endpoints work")


main()
