from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.user.models import User

from .config import get_header, init_config  # noqa
from .data import users

client = TestClient(app)

NEW_USERNAME = "username-exists"
NEW_PASS = "new-pass"
NEW_FULL_NAME = "Full Name"


def test_registration_and_auth():
    _ = User.delete_many({"username": NEW_USERNAME})

    response = client.post(
        "/api/v1/registration",
        json={
            "username": NEW_USERNAME,
            "password": NEW_PASS,
            "full_name": NEW_FULL_NAME,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    response = client.post(
        "/token", data={"username": NEW_USERNAME, "password": NEW_PASS}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["access_token"]

    _ = User.delete_many({"username": NEW_USERNAME})


def test_duplicate_registration():
    _ = User.delete_many({"username": NEW_USERNAME})

    response = client.post(
        "/api/v1/registration",
        json={
            "username": NEW_USERNAME,
            "password": NEW_PASS,
            "full_name": NEW_FULL_NAME,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    response = client.post(
        "/api/v1/registration",
        json={
            "username": NEW_USERNAME,
            "password": NEW_PASS,
            "full_name": NEW_FULL_NAME,
        },
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    _ = User.delete_many({"username": NEW_USERNAME})


def test_update_access_token():
    response = client.post(
        "/token",
        data={"username": users[0]["username"], "password": users[0]["password"]},
    )

    response = client.post(
        "/api/v1/update-access-token",
        json={"refresh_token": response.json()["refresh_token"]},
    )
    assert response.status_code == status.HTTP_200_OK


def test_get_me():
    response = client.get("/api/v1/me", headers=get_header())

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == users[0]["username"]


def test_update_user():
    new_full_name = "New Name"
    response = client.patch(
        "/api/v1/update-user", json={"full_name": new_full_name}, headers=get_header()
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["full_name"] == new_full_name
    assert response.json()["username"] == users[0]["username"]


def test_logout_from_all_device():
    response = client.post(
        "/token",
        data={"username": users[0]["username"], "password": users[0]["password"]},
    )
    access_token = response.json()["access_token"]
    refresh_token = response.json()["refresh_token"]
    print(access_token, refresh_token)
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    response = client.put("/api/v1/logout-from-all-device", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post(
        "/api/v1/update-access-token", json={"refresh_token": refresh_token}
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
