"""Secuencia de correo: 3 toques espaciados, con opción de baja, sin casos inventados."""
import inspect

from app.config import SECUENCIA_MAX_EMAILS
from app.tasks.daily_sequence import horas_de_espera
from app.pipelines import p5_email_generator, p6_email_sender


def test_tres_correos_espaciados():
    assert SECUENCIA_MAX_EMAILS == 3
    assert horas_de_espera(2) == 72
    assert horas_de_espera(3) == 144


def test_prompt_prohibe_inventar_casos():
    src = inspect.getsource(p5_email_generator)
    assert "NO inventes casos de éxito" in src
    assert "Caso de éxito de negocio similar" not in src


def test_correo_lleva_baja(monkeypatch):
    enviado = {}

    class R:
        status_code = 201
        text = ""

    def fake_post(url, headers=None, json=None, timeout=None):
        enviado.update(json)
        return R()

    monkeypatch.setattr(p6_email_sender.requests, "post", fake_post)
    assert p6_email_sender._enviar_brevo("a@b.com", "A", "Hola", "Texto")["ok"]
    assert "BAJA" in enviado["textContent"]
    assert "List-Unsubscribe" in enviado["headers"]
