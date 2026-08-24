import pytest
from fastapi.testclient import TestClient
import time
import hmac
import hashlib

from app.main import app, verify_admin_or_task_secret
import app.main as main_module
from fastapi import Depends

@app.get("/test-protected-auth")
async def test_protected(auth: bool = Depends(verify_admin_or_task_secret)):
    return {"status": "ok"}

@pytest.fixture
def client():
    with TestClient(app, base_url="https://testserver") as c:
        yield c

@pytest.fixture
def mock_config(monkeypatch):
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", "super_secret")
    monkeypatch.setattr(main_module, "ADMIN_SESSION_SECRET", "super_session_secret")
    monkeypatch.setattr(main_module, "TASK_SECRET", "old_task_secret")

def test_login_fails_if_not_configured(monkeypatch, client):
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(main_module, "ADMIN_SESSION_SECRET", "")

    response = client.post("/admin/login", json={"password": "any"})
    assert response.status_code == 503

@pytest.mark.parametrize("admin_pwd, admin_sec", [
    ("super_secret", ""),
    ("", "super_session_secret"),
])
def test_login_fails_if_partially_configured(monkeypatch, client, admin_pwd, admin_sec):
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", admin_pwd)
    monkeypatch.setattr(main_module, "ADMIN_SESSION_SECRET", admin_sec)

    response = client.post("/admin/login", json={"password": "super_secret" if admin_pwd else "any"})
    assert response.status_code == 503

def test_login_incorrect_password(mock_config, client):
    response = client.post("/admin/login", json={"password": "wrong"})
    assert response.status_code == 403

def test_login_correct_and_cookie_attributes(mock_config, client):
    response = client.post("/admin/login", json={"password": "super_secret"})
    assert response.status_code == 200
    assert response.json().get("status") == "ok"

    cookie_str = response.headers.get("set-cookie", "").lower()

    assert "lince_admin_session=" in cookie_str
    assert "httponly" in cookie_str
    assert "samesite=strict" in cookie_str
    assert "secure" in cookie_str
    assert "max-age=43200" in cookie_str

def test_helper_accepts_valid_session(mock_config, client):
    response = client.post("/admin/login", json={"password": "super_secret"})
    cookie_val = response.cookies.get("lince_admin_session")

    res = client.get("/test-protected-auth", cookies={"lince_admin_session": cookie_val})
    assert res.status_code == 200

def test_helper_rejects_manipulated_session(mock_config, client):
    response = client.post("/admin/login", json={"password": "super_secret"})
    cookie_val = response.cookies.get("lince_admin_session")

    parts = cookie_val.split(".")
    manipulated = f"{parts[0]}.badsignature"

    res = client.get("/test-protected-auth", cookies={"lince_admin_session": manipulated})
    assert res.status_code == 403

def test_helper_rejects_expired_session(mock_config, client):
    past_time = time.time() - (13 * 3600)

    timestamp_str = str(int(past_time))
    signature = hmac.new(
        "super_session_secret".encode(),
        timestamp_str.encode(),
        hashlib.sha256
    ).hexdigest()

    expired_cookie = f"{timestamp_str}.{signature}"

    res = client.get("/test-protected-auth", cookies={"lince_admin_session": expired_cookie})
    assert res.status_code == 403

def test_helper_accepts_x_task_secret(mock_config, client):
    res = client.get("/test-protected-auth", headers={"X-Task-Secret": "old_task_secret"})
    assert res.status_code == 200

def test_helper_accepts_x_task_secret_without_admin_config(monkeypatch, client):
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(main_module, "ADMIN_SESSION_SECRET", "")
    monkeypatch.setattr(main_module, "TASK_SECRET", "old_task_secret")

    res = client.get("/test-protected-auth", headers={"X-Task-Secret": "old_task_secret"})
    assert res.status_code == 200

def test_helper_rejects_future_session(mock_config, client):
    future_time = time.time() + 3600

    timestamp_str = str(int(future_time))
    signature = hmac.new(
        "super_session_secret".encode(),
        timestamp_str.encode(),
        hashlib.sha256
    ).hexdigest()

    future_cookie = f"{timestamp_str}.{signature}"

    res = client.get("/test-protected-auth", cookies={"lince_admin_session": future_cookie})
    assert res.status_code == 403

def test_helper_fail_closed_if_missing_config(monkeypatch, client):
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(main_module, "ADMIN_SESSION_SECRET", "")
    monkeypatch.setattr(main_module, "TASK_SECRET", "")

    res = client.get("/test-protected-auth")
    assert res.status_code == 503

def test_p5_dual_auth(mock_config, client, monkeypatch):
    calls = []

    async def mock_generar(place_id):
        calls.append(place_id)
        return {
            "emails": [],
            "requiere_aprobacion": True
        }
    monkeypatch.setattr(main_module, "generar_secuencia_emails", mock_generar)

    body = {"place_id": "test_p5"}

    res = client.post("/pipeline/p5", json=body)
    assert res.status_code == 403
    assert len(calls) == 0

    res = client.post("/pipeline/p5", json=body, headers={"X-Task-Secret": "old_task_secret"})
    assert res.status_code == 200
    assert len(calls) == 1
    assert calls[0] == "test_p5"

    login_res = client.post("/admin/login", json={"password": "super_secret"})
    assert login_res.status_code == 200

    res = client.post("/pipeline/p5", json=body)
    assert res.status_code == 200
    assert len(calls) == 2
    assert calls[1] == "test_p5"

def test_p6_dual_auth(mock_config, client, monkeypatch):
    received_approved = None

    async def mock_ejecutar(place_id, approved_by_human):
        nonlocal received_approved
        received_approved = approved_by_human
        return {"status": "ok"}

    async def mock_actualizar(place_id, to_email):
        return {"status": "ok"}

    monkeypatch.setattr(main_module, "ejecutar_secuencia", mock_ejecutar)
    monkeypatch.setattr(main_module, "actualizar_recipient_email", mock_actualizar)

    body = {"place_id": "test_p6", "approved_by_human": True, "to_email": "test@test.com"}

    res = client.post("/pipeline/p6", json=body)
    assert res.status_code == 403

    res = client.post("/pipeline/p6", json=body, headers={"X-Task-Secret": "old_task_secret"})
    assert res.status_code == 200
    assert received_approved is True

    received_approved = None
    body["approved_by_human"] = False

    client.post("/admin/login", json={"password": "super_secret"})
    res = client.post("/pipeline/p6", json=body)
    assert res.status_code == 200
    assert received_approved is False

def test_setup_recipient_email_dual_auth(mock_config, client, monkeypatch):
    async def mock_actualizar(place_id, email):
        return {"status": "ok"}

    monkeypatch.setattr(main_module, "actualizar_recipient_email", mock_actualizar)

    body = {"place_id": "test_p6", "email": "test@test.com"}

    res = client.post("/setup/recipient-email", json=body)
    assert res.status_code == 403

    res = client.post("/setup/recipient-email", json=body, headers={"X-Task-Secret": "old_task_secret"})
    assert res.status_code == 200

    client.post("/admin/login", json={"password": "super_secret"})
    res = client.post("/setup/recipient-email", json=body)
    assert res.status_code == 200
