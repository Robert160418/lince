"""El panel y la API exigen token; sin token configurado, Lince no queda abierto."""
import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(main, "LINCE_API_TOKEN", "token-de-prueba")
    monkeypatch.setattr(main, "TASK_SECRET", "secreto-cron")

    async def sin_db(*a, **k):
        return []
    monkeypatch.setattr(main, "supabase_select", sin_db)
    return TestClient(main.app)


def test_salud_y_paginas_publicas(cliente):
    assert cliente.get("/health").status_code == 200
    assert cliente.get("/").status_code == 200
    assert cliente.get("/prospectos").status_code == 200


@pytest.mark.parametrize("ruta", ["/leads", "/lotes", "/api/prospectos?lote_id=x"])
def test_api_sin_token_rechaza(cliente, ruta):
    assert cliente.get(ruta).status_code == 401
    assert cliente.get(ruta, headers={"X-Lince-Token": "malo"}).status_code == 401


def test_api_con_token(cliente):
    r = cliente.get("/lotes", headers={"X-Lince-Token": "token-de-prueba"})
    assert r.status_code == 200 and r.json() == []


def test_envio_de_correos_protegido(cliente):
    r = cliente.post("/pipeline/p6", json={"place_id": "x", "to_email": "a@b.com"})
    assert r.status_code == 401


def test_rutas_de_depuracion_eliminadas(cliente):
    h = {"X-Lince-Token": "token-de-prueba"}
    assert cliente.get("/debug", headers=h).status_code == 404
    assert cliente.get("/test-db", headers=h).status_code == 404


def test_tarea_diaria_exige_secreto(cliente):
    assert cliente.post("/tasks/daily-sequence").status_code == 403
    assert cliente.post("/tasks/daily-sequence", headers={"X-Task-Secret": "lince-cron-2026"}).status_code == 403


def test_sin_token_configurado_todo_cerrado(monkeypatch):
    monkeypatch.setattr(main, "LINCE_API_TOKEN", "")
    c = TestClient(main.app)
    assert c.get("/leads", headers={"X-Lince-Token": ""}).status_code == 503


def test_tarea_sin_secreto_configurado(monkeypatch):
    monkeypatch.setattr(main, "TASK_SECRET", "")
    c = TestClient(main.app)
    assert c.post("/tasks/daily-sequence", headers={"X-Task-Secret": ""}).status_code == 503
