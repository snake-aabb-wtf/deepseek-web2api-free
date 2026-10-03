"""Tests for persistent API-key storage, management routes, and client auth."""
from __future__ import annotations

import sqlite3
import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import admin
import server
from api_key_store import ApiKeyStore, _legacy_keys_from_env


@pytest.fixture
def api_key_store(tmp_path):
    return ApiKeyStore(tmp_path / "api_keys.sqlite3")


@pytest.fixture
def admin_client(monkeypatch, tmp_path):
    store = ApiKeyStore(tmp_path / "admin_api_keys.sqlite3")
    monkeypatch.setattr(admin, "get_api_key_store", lambda: store)

    token = secrets.token_urlsafe(24)
    admin._tokens.add(token)
    app = FastAPI()
    app.include_router(admin.router)
    try:
        with TestClient(app) as client:
            yield client, store, token
    finally:
        admin._tokens.discard(token)


@pytest.fixture
def server_client(monkeypatch, tmp_path):
    store = ApiKeyStore(tmp_path / "server_api_keys.sqlite3")
    monkeypatch.setattr(server, "API_KEY_STORE", store)
    with TestClient(server.app) as client:
        yield client, store


def test_legacy_environment_keys_are_deduplicated(monkeypatch):
    monkeypatch.setenv("API_KEYS", "first-key, second-key, first-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "second-key")

    assert _legacy_keys_from_env() == ["first-key", "second-key"]


def test_legacy_keys_import_only_once_and_store_hashes(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    legacy_keys = ["old-client-key-one", "old-client-key-two"]

    store = ApiKeyStore(db_path, legacy_keys)
    assert all(store.verify(key) for key in legacy_keys)
    assert len(store.list_keys()) == 2

    # Restarting with different environment values must not silently add or
    # replace credentials after the one-time migration marker is set.
    reopened = ApiKeyStore(db_path, ["late-environment-key"])
    assert not reopened.verify("late-environment-key")
    assert all(reopened.verify(key) for key in legacy_keys)

    rows = sqlite3.connect(db_path).execute(
        "SELECT name FROM pragma_table_info('api_keys') ORDER BY cid"
    ).fetchall()
    assert [row[0] for row in rows] == [
        "id", "name", "key_hash", "key_prefix", "created_at"
    ]
    db_bytes = b"".join(
        path.read_bytes()
        for path in tmp_path.glob("legacy.sqlite3*")
        if path.is_file()
    )
    assert all(key.encode() not in db_bytes for key in legacy_keys)


def test_generated_key_is_verifiable_and_only_returned_at_creation(api_key_store):
    result = api_key_store.create_key("  local client  ")
    key = result["key"]
    record = result["api_key"]

    assert key.startswith("sk-")
    assert len(key) > 40
    assert record["name"] == "local client"
    assert set(record) == {"id", "name", "prefix", "created_at"}
    assert record["prefix"] == key[:8]
    assert api_key_store.verify(key)
    assert not api_key_store.verify("sk-invalid")
    assert key not in repr(api_key_store.list_keys())


@pytest.mark.parametrize("name", ["", "   ", "x" * 65])
def test_create_rejects_empty_or_overlong_names(api_key_store, name):
    with pytest.raises(ValueError):
        api_key_store.create_key(name)


def test_multiple_keys_can_be_revoked_independently(api_key_store):
    first = api_key_store.create_key("first")
    second = api_key_store.create_key("second")

    assert api_key_store.has_keys()
    assert api_key_store.verify(first["key"])
    assert api_key_store.verify(second["key"])
    assert api_key_store.revoke_key(first["api_key"]["id"])
    assert not api_key_store.verify(first["key"])
    assert api_key_store.verify(second["key"])
    assert not api_key_store.revoke_key("missing-id")


def test_admin_api_key_routes_require_admin_auth(admin_client):
    client, _, _ = admin_client

    assert client.get("/admin/api/api-keys").status_code == 401
    assert client.post(
        "/admin/api/api-keys", json={"name": "unauthorized"}
    ).status_code == 401
    assert client.delete("/admin/api/api-keys/missing").status_code == 401


def test_admin_api_key_routes_create_list_and_revoke(admin_client):
    client, store, token = admin_client
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/admin/api/api-keys", json={"name": "desktop app"}, headers=headers
    )
    assert created.status_code == 200
    assert created.headers["cache-control"] == "no-store"
    body = created.json()
    key = body["key"]
    record = body["api_key"]
    assert store.verify(key)

    listed = client.get("/admin/api/api-keys", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == {"keys": [record]}
    assert key not in listed.text

    invalid_name = client.post(
        "/admin/api/api-keys", json={"name": " "}, headers=headers
    )
    assert invalid_name.status_code == 400

    revoked = client.delete(
        f"/admin/api/api-keys/{record['id']}", headers=headers
    )
    assert revoked.status_code == 200
    assert not store.verify(key)
    assert client.get("/admin/api/api-keys", headers=headers).json() == {"keys": []}
    assert client.delete(
        f"/admin/api/api-keys/{record['id']}", headers=headers
    ).status_code == 404


def test_generated_keys_authenticate_v1_and_revocation_takes_effect(server_client):
    client, store = server_client

    assert client.get("/v1/models").status_code == 503
    key_record = store.create_key("auth integration")
    key = key_record["key"]

    bearer = client.get(
        "/v1/models", headers={"Authorization": f"Bearer {key}"}
    )
    assert bearer.status_code == 200

    x_api_key = client.get("/v1/models", headers={"x-api-key": key})
    assert x_api_key.status_code == 200
    assert client.get(
        "/v1/models", headers={"Authorization": "Bearer wrong-key"}
    ).status_code == 401

    assert store.revoke_key(key_record["api_key"]["id"])
    assert client.get(
        "/v1/models", headers={"Authorization": f"Bearer {key}"}
    ).status_code == 503
