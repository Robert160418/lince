"""
Tests seguros de Lince 2.0
──────────────────────────

Esta suite NO debe:

- enviar emails reales
- llamar a Brevo
- llamar a OpenAI
- llamar a Apify
- escribir en Supabase real
- sincronizar leads al portal real

Todos los servicios externos son simulados mediante monkeypatch.

Ejecutar únicamente esta suite:

    pytest tests/test_lince_v2_safe.py -v
"""

import os
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


# ===================================================================
# ENTORNO DE PRUEBA
# ===================================================================

# Se establecen ANTES de importar los módulos de Lince.
# load_dotenv() no los reemplaza porque override=False por defecto.

os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_KEY"] = "test-supabase-key"
os.environ["OPENAI_API_KEY"] = "sk-test-lince-v2"
os.environ["APIFY_API_KEY"] = "apify-test-key"
os.environ["BREVO_API_KEY"] = "brevo-test-key"

os.environ["PORTAL_WEBHOOK_URL"] = ""
os.environ["LINCE_WEBHOOK_SECRET"] = ""

os.environ["GOOGLE_SHEET_ID"] = ""
os.environ["GOOGLE_SHEETS_CREDENTIALS"] = ""
os.environ["GOOGLE_SHEETS_CREDENTIALS_PATH"] = ""


# Importar DESPUÉS de preparar el entorno seguro.

from app.pipelines import p2_reviews
from app.pipelines import p4_keypoints
from app.pipelines import p5_email_generator
from app.pipelines import p6_email_sender

from app.utils import batch_processor
from app.tasks import daily_sequence


pytestmark = pytest.mark.unit


# ===================================================================
# HELPERS
# ===================================================================


async def _noop_async(*args, **kwargs):
    return None


class FakeOpenAICompletions:
    """
    Respuesta falsa de OpenAI.
    """

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def create(self, *args, **kwargs):
        self.calls += 1

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            self.payload,
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        )


class FakeOpenAIClient:
    def __init__(self, payload):
        self.fake_completions = FakeOpenAICompletions(
            payload
        )

        self.chat = SimpleNamespace(
            completions=self.fake_completions
        )


def _lead_base(
    score_fields=True,
):
    """
    Lead de prueba reutilizable.
    """

    lead = {
        "place_id": "TEST_PLACE_001",
        "lote_id": "TEST_LOTE_001",
        "name": "Negocio Seguro Test",
        "category": "Clínica dental",
        "rating": 4.2,
        "full_address": "Quito, Ecuador",
        "phone": "+593999999999",
        "contact_email": "contacto@example.com",
        "site": "https://example.com",
        "query": "dentistas quito",
    }

    if score_fields:
        lead.update({
            "website_title": "Clínica Dental",
            "website_description": "",
            "website_generator": "WordPress",
            "website_has_gtm": False,
            "website_has_fb_pixel": False,
            "company_instagram": "",
            "company_facebook": "",
            "company_tiktok": "",
            "company_linkedin": "",
        })

    return lead


# ===================================================================
# P2 — REVIEWS
# ===================================================================


@pytest.mark.asyncio
async def test_p2_sin_api_key_devuelve_lista_vacia(
    monkeypatch,
):
    """
    Si Apify no está configurado, P2 debe devolver [].

    Nunca debe utilizar reviews ficticias.
    """

    monkeypatch.setattr(
        p2_reviews,
        "APIFY_API_KEY",
        None,
    )

    reviews = await p2_reviews.obtener_reviews(
        "TEST_PLACE_001",
        max_reviews=10,
    )

    assert reviews == []


@pytest.mark.asyncio
async def test_p2_lista_vacia_no_guarda_reviews(
    monkeypatch,
):
    """
    Una lista vacía debe devolver 0 y no escribir en Supabase.
    """

    calls = []

    async def fake_insert(*args, **kwargs):
        calls.append(
            (args, kwargs)
        )

    monkeypatch.setattr(
        p2_reviews,
        "supabase_insert",
        fake_insert,
    )

    monkeypatch.setattr(
        p2_reviews,
        "_SHEETS_AVAILABLE",
        False,
    )

    guardadas = (
        await p2_reviews
        .procesar_y_guardar_reviews(
            "TEST_PLACE_001",
            [],
        )
    )

    assert guardadas == 0
    assert calls == []


# ===================================================================
# P4 — SCORING OBJETIVO
# ===================================================================


def test_p4_score_es_deterministico():
    """
    El mismo lead siempre debe producir el mismo score
    sin participación de OpenAI.
    """

    lead = {
        "site": None,
        "company_instagram": None,
        "company_facebook": None,
        "phone": "+593999999999",
        "contact_email": "test@example.com",
        "full_address": "Quito",
        "rating": 3.8,
    }

    score_1, breakdown_1 = (
        p4_keypoints.calcular_score_objetivo(
            lead
        )
    )

    score_2, breakdown_2 = (
        p4_keypoints.calcular_score_objetivo(
            lead
        )
    )

    assert score_1 == score_2
    assert breakdown_1 == breakdown_2

    assert 0 <= score_1 <= 100

    # Con las reglas actuales:
    #
    # sin web            +35
    # sin Instagram      +10
    # sin Facebook       +8
    # rating disponible  +2
    # rating < 4         +10
    # teléfono           +12
    # email              +8
    # dirección          +3
    #
    # Total = 88

    assert score_1 == 88


@pytest.mark.asyncio
async def test_p4_openai_no_puede_cambiar_score(
    monkeypatch,
):
    """
    Aunque OpenAI intente devolver lead_score=1,
    el resultado final debe utilizar el score Python.
    """

    lead = _lead_base()

    async def fake_select(
        table,
        filters,
    ):
        if table == "leads":
            return [lead]

        if table == "reviews":
            return []

        return []

    inserts = []
    updates = []

    async def fake_insert(
        table,
        data,
    ):
        inserts.append(
            (table, data)
        )

        return {"status": 201}

    async def fake_update(
        place_id,
        data,
    ):
        updates.append(
            (place_id, data)
        )

        return {"status": 200}

    fake_ai_payload = {
        "problema_principal":
            "Hay oportunidades verificables de mejora digital.",

        "oportunidad":
            "Noboweb puede revisar medición y presencia digital.",

        "argumento_venta":
            "Detectamos algunos puntos que vale la pena revisar.",

        "puntos_positivos": [
            "Tiene sitio web"
        ],

        "puntos_negativos": [
            "No se detectó GTM"
        ],

        "plan_de_accion": [
            "Revisar medición",
            "Revisar presencia social",
            "Priorizar oportunidades",
        ],

        "servicios_recomendados": [
            "Rediseño y modernización web",
            "Gestión de redes sociales (Instagram, Facebook)",
        ],

        "servicio_principal":
            "Rediseño y modernización web",

        "razon_score":
            "Explicación basada en señales objetivas.",

        # Intento deliberado de alterar el score.
        "lead_score": 1,
    }

    fake_client = FakeOpenAIClient(
        fake_ai_payload
    )

    monkeypatch.setattr(
        p4_keypoints,
        "supabase_select",
        fake_select,
    )

    monkeypatch.setattr(
        p4_keypoints,
        "supabase_insert",
        fake_insert,
    )

    monkeypatch.setattr(
        p4_keypoints,
        "supabase_update_lead",
        fake_update,
    )

    monkeypatch.setattr(
        p4_keypoints,
        "client",
        fake_client,
    )

    expected_score, _ = (
        p4_keypoints.calcular_score_objetivo(
            lead
        )
    )

    resultado = (
        await p4_keypoints.generar_keypoints(
            lead["place_id"]
        )
    )

    assert resultado["lead_score"] == expected_score
    assert resultado["lead_score"] != 1

    assert (
        resultado["score_version"]
        == "lince-v2-objective-1"
    )

    assert len(inserts) == 1
    assert len(updates) == 1


# ===================================================================
# BATCH — GATE COMERCIAL
# ===================================================================


@pytest.mark.asyncio
async def test_batch_score_69_no_pasa_a_crm_ni_p5(
    monkeypatch,
):
    """
    Score 69 debe permanecer en análisis/Sheets.

    No CRM.
    No P5.
    No P6.
    """

    lead = _lead_base()

    async def fake_supabase_select(
        table,
        filters,
    ):
        if table == "leads":
            return [lead]

        return []

    async def fake_reviews(*args, **kwargs):
        return []

    async def fake_guardar_reviews(
        *args,
        **kwargs,
    ):
        return 0

    async def fake_p4(*args, **kwargs):
        return {
            "lead_score": 69,
            "problema_principal":
                "Problema test",
            "oportunidad":
                "Oportunidad test",
            "servicios_recomendados": [
                "Página web profesional"
            ],
            "servicio_principal":
                "Página web profesional",
        }

    async def no_debe_llamarse(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "Esta función no debía ejecutarse "
            "para score 69."
        )

    async def fake_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(
        batch_processor,
        "_SHEETS_AVAILABLE",
        False,
    )

    monkeypatch.setattr(
        batch_processor,
        "supabase_select",
        fake_supabase_select,
    )

    monkeypatch.setattr(
        batch_processor,
        "obtener_reviews",
        fake_reviews,
    )

    monkeypatch.setattr(
        batch_processor,
        "procesar_y_guardar_reviews",
        fake_guardar_reviews,
    )

    monkeypatch.setattr(
        batch_processor,
        "generar_keypoints",
        fake_p4,
    )

    monkeypatch.setattr(
        batch_processor,
        "push_lead_to_portal",
        no_debe_llamarse,
    )

    monkeypatch.setattr(
        batch_processor,
        "generar_secuencia_emails",
        no_debe_llamarse,
    )

    monkeypatch.setattr(
        batch_processor.asyncio,
        "sleep",
        fake_sleep,
    )

    resultado = (
        await batch_processor.process_lote(
            lead["lote_id"]
        )
    )

    lead_result = resultado[
        "results"
    ][0]

    assert (
        lead_result["steps"]["crm"]["status"]
        == "skipped"
    )

    assert (
        lead_result["steps"]["p5"]["status"]
        == "skipped"
    )

    assert (
        lead_result["steps"]["p6"]["status"]
        == "skipped"
    )


@pytest.mark.asyncio
async def test_batch_score_70_pasa_crm_p5_pero_no_envia(
    monkeypatch,
):
    """
    Score 70 debe:

    - pasar al CRM
    - generar P5
    - quedar pendiente de aprobación
    - NO ejecutar ningún envío
    """

    lead = _lead_base()

    portal_calls = []
    p5_calls = []

    async def fake_supabase_select(
        table,
        filters,
    ):
        if table == "leads":
            return [lead]

        return []

    async def fake_reviews(*args, **kwargs):
        return []

    async def fake_guardar_reviews(
        *args,
        **kwargs,
    ):
        return 0

    async def fake_p4(*args, **kwargs):
        return {
            "lead_score": 70,
            "problema_principal":
                "Problema test",
            "oportunidad":
                "Oportunidad test",
            "servicios_recomendados": [
                "Página web profesional"
            ],
            "servicio_principal":
                "Página web profesional",
        }

    async def fake_portal(
        lead_arg,
        kp_arg,
    ):
        portal_calls.append(
            (
                lead_arg,
                kp_arg,
            )
        )

        return {
            "status": "ok"
        }

    async def fake_p5(
        place_id,
    ):
        p5_calls.append(
            place_id
        )

        return {
            "emails": [
                {
                    "asunto": f"Asunto {i}",
                    "cuerpo": f"Cuerpo {i}",
                }
                for i in range(
                    1,
                    6,
                )
            ],
            "guardado": True,
            "requiere_aprobacion": True,
        }

    async def fake_sleep(
        *args,
        **kwargs,
    ):
        return None

    monkeypatch.setattr(
        batch_processor,
        "_SHEETS_AVAILABLE",
        False,
    )

    monkeypatch.setattr(
        batch_processor,
        "supabase_select",
        fake_supabase_select,
    )

    monkeypatch.setattr(
        batch_processor,
        "obtener_reviews",
        fake_reviews,
    )

    monkeypatch.setattr(
        batch_processor,
        "procesar_y_guardar_reviews",
        fake_guardar_reviews,
    )

    monkeypatch.setattr(
        batch_processor,
        "generar_keypoints",
        fake_p4,
    )

    monkeypatch.setattr(
        batch_processor,
        "push_lead_to_portal",
        fake_portal,
    )

    monkeypatch.setattr(
        batch_processor,
        "generar_secuencia_emails",
        fake_p5,
    )

    monkeypatch.setattr(
        batch_processor.asyncio,
        "sleep",
        fake_sleep,
    )

    resultado = (
        await batch_processor.process_lote(
            lead["lote_id"]
        )
    )

    lead_result = resultado[
        "results"
    ][0]

    assert len(portal_calls) == 1
    assert len(p5_calls) == 1

    assert (
        lead_result["steps"]["crm"]["status"]
        == "ok"
    )

    assert (
        lead_result["steps"]["p5"]["status"]
        == "ok"
    )

    assert (
        lead_result["steps"]["p6"]["status"]
        == "pending_approval"
    )

    assert resultado["enviados"] == 0


# ===================================================================
# P5 — GENERACIÓN SEGURA
# ===================================================================


@pytest.mark.asyncio
async def test_p5_no_genera_duplicado(
    monkeypatch,
):
    """
    Si ya existe una secuencia, P5 debe detenerse antes de OpenAI.
    """

    lead = _lead_base()

    kp = {
        "place_id":
            lead["place_id"],

        "painpoints_and_opportunities": {
            "problema_principal":
                "Problema test",
            "oportunidad":
                "Oportunidad test",
        },

        "keypoints_for_personalization": {
            "argumento_venta":
                "Argumento test",
            "servicio_principal":
                "Página web profesional",
        },

        "servicios_recomendados": [
            "Página web profesional"
        ],

        "lead_score": 80,
    }

    async def fake_select(
        table,
        filters,
    ):
        if table == "leads":
            return [lead]

        if table == "keypoints":
            return [kp]

        if table == "emails":
            return [
                {
                    "place_id":
                        lead["place_id"]
                }
            ]

        return []

    class FailCompletions:
        async def create(
            self,
            *args,
            **kwargs,
        ):
            raise AssertionError(
                "OpenAI no debía ejecutarse "
                "si ya existe una secuencia."
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=FailCompletions()
        )
    )

    monkeypatch.setattr(
        p5_email_generator,
        "supabase_select",
        fake_select,
    )

    monkeypatch.setattr(
        p5_email_generator,
        "client",
        fake_client,
    )

    resultado = (
        await p5_email_generator
        .generar_secuencia_emails(
            lead["place_id"]
        )
    )

    assert "error" in resultado

    assert (
        "Ya existe una secuencia"
        in resultado["error"]
    )


def test_p5_detector_rechaza_claims_no_verificados():
    """
    Validación local: claims prohibidos deben ser detectados
    incluso si la IA ignora el prompt.
    """

    frase = (
        "Nuestros clientes aumentaron sus ventas "
        "gracias a este servicio."
    )

    riesgo = (
        p5_email_generator
        ._detectar_afirmacion_riesgosa(
            frase
        )
    )

    assert riesgo is not None


# ===================================================================
# P6 — SEGURIDAD / IDEMPOTENCIA
# ===================================================================


@pytest.mark.asyncio
async def test_p6_primer_email_requiere_aprobacion_y_no_envia(
    monkeypatch,
):
    """
    Sin approved_by_human=True, el primer email jamás llega a Brevo.
    """

    row = {
        "place_id":
            "TEST_PLACE_001",

        "company_name":
            "Negocio Seguro",

        "recipient_email":
            "contacto@example.com",

        "current_email_day":
            0,

        "sequence_stopped":
            False,

        "replied":
            False,

        "email_1_subject":
            "Asunto test",

        "email_1_body":
            "Cuerpo test",
    }

    async def fake_select(
        table,
        filters,
    ):
        return [row]

    def brevo_prohibido(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "Brevo NO debe ejecutarse "
            "sin aprobación humana."
        )

    monkeypatch.setattr(
        p6_email_sender,
        "supabase_select",
        fake_select,
    )

    monkeypatch.setattr(
        p6_email_sender,
        "_enviar_brevo",
        brevo_prohibido,
    )

    resultado = (
        await p6_email_sender
        .ejecutar_secuencia(
            "TEST_PLACE_001"
        )
    )

    assert (
        resultado["status"]
        == "pending_approval"
    )

    assert resultado["dia"] == 1


@pytest.mark.asyncio
async def test_p6_estado_incierto_bloquea_reintento(
    monkeypatch,
):
    """
    Si current_email_day avanzó pero no existe sent_at,
    P6 debe detenerse antes de Brevo.
    """

    row = {
        "place_id":
            "TEST_PLACE_001",

        "company_name":
            "Negocio Seguro",

        "recipient_email":
            "contacto@example.com",

        "current_email_day":
            1,

        "sent_at_day1":
            None,

        "sequence_stopped":
            False,

        "replied":
            False,
    }

    async def fake_select(
        table,
        filters,
    ):
        return [row]

    def brevo_prohibido(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "Brevo NO debe ejecutarse "
            "en estado incierto."
        )

    monkeypatch.setattr(
        p6_email_sender,
        "supabase_select",
        fake_select,
    )

    monkeypatch.setattr(
        p6_email_sender,
        "_enviar_brevo",
        brevo_prohibido,
    )

    resultado = (
        await p6_email_sender
        .ejecutar_secuencia(
            "TEST_PLACE_001"
        )
    )

    assert (
        resultado["status"]
        == "manual_review_required"
    )


# ===================================================================
# DAILY SEQUENCE
# ===================================================================


@pytest.mark.asyncio
async def test_daily_sequence_no_inicia_campanas(
    monkeypatch,
):
    """
    La consulta debe pedir únicamente current_email_day >= 1.
    """

    consultas = []

    async def fake_select(
        table,
        filters,
    ):
        consultas.append(
            (
                table,
                filters,
            )
        )

        return []

    monkeypatch.setattr(
        daily_sequence,
        "supabase_select",
        fake_select,
    )

    resultado = (
        await daily_sequence
        .run_daily_sequence()
    )

    assert resultado["enviados"] == 0

    assert consultas[0] == (
        "emails",
        {
            "current_email_day":
                "gte.1"
        },
    )


@pytest.mark.asyncio
async def test_daily_sequence_estado_incierto_va_revision_manual(
    monkeypatch,
):
    """
    current_email_day=1 sin sent_at_day1 nunca debe avanzar.
    """

    row = {
        "place_id":
            "TEST_PLACE_001",

        "company_name":
            "Negocio Seguro",

        "recipient_email":
            "contacto@example.com",

        "current_email_day":
            1,

        "sent_at_day1":
            None,

        "sequence_stopped":
            False,

        "replied":
            False,
    }

    async def fake_select(
        table,
        filters,
    ):
        if table == "emails":
            return [row]

        return []

    async def p6_prohibido(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "P6 NO debe ejecutarse "
            "con estado incierto."
        )

    async def fake_sheet(
        *args,
        **kwargs,
    ):
        return None

    monkeypatch.setattr(
        daily_sequence,
        "supabase_select",
        fake_select,
    )

    monkeypatch.setattr(
        daily_sequence,
        "ejecutar_secuencia",
        p6_prohibido,
    )

    monkeypatch.setattr(
        daily_sequence,
        "_actualizar_sheet",
        fake_sheet,
    )

    resultado = (
        await daily_sequence
        .run_daily_sequence()
    )

    assert resultado["enviados"] == 0

    assert (
        resultado["revision_manual"]
        == 1
    )

    assert (
        resultado["resultados"][0]["status"]
        == "manual_review_required"
    )


@pytest.mark.asyncio
async def test_daily_solo_status_enviado_cuenta_como_envio(
    monkeypatch,
):
    """
    Un estado de revisión manual de P6 jamás incrementa enviados.
    """

    hace_48_horas = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            hours=48
        )
    ).isoformat()

    row = {
        "place_id":
            "TEST_PLACE_001",

        "company_name":
            "Negocio Seguro",

        "recipient_email":
            "contacto@example.com",

        "current_email_day":
            1,

        "sent_at_day1":
            hace_48_horas,

        "sequence_stopped":
            False,

        "replied":
            False,
    }

    async def fake_select(
        table,
        filters,
    ):
        if table == "emails":
            return [row]

        return []

    async def fake_p6(
        *args,
        **kwargs,
    ):
        return {
            "status":
                "manual_review_required",

            "mensaje":
                "Estado incierto simulado",
        }

    async def fake_sheet(
        *args,
        **kwargs,
    ):
        return None

    monkeypatch.setattr(
        daily_sequence,
        "supabase_select",
        fake_select,
    )

    monkeypatch.setattr(
        daily_sequence,
        "ejecutar_secuencia",
        fake_p6,
    )

    monkeypatch.setattr(
        daily_sequence,
        "_actualizar_sheet",
        fake_sheet,
    )

    resultado = (
        await daily_sequence
        .run_daily_sequence()
    )

    assert resultado["enviados"] == 0

    assert (
        resultado["revision_manual"]
        == 1
    )


# ===================================================================
# TEST FINAL DE INVARIANTES
# ===================================================================


def test_invariantes_lince_v2():
    """
    Verifica algunas decisiones esenciales de arquitectura.
    """

    assert (
        batch_processor.MIN_SCORE_CRM
        == 70
    )

    assert (
        p6_email_sender.FROM_NAME
        == "Roberto | Noboweb"
    )

    assert (
        p5_email_generator.MAX_EMAIL_WORDS
        == 120
    )

    assert (
        daily_sequence.HORAS_ENTRE_EMAILS
        == 24
    )

    # ===================================================================
# MAIN API — SEGURIDAD DE ENDPOINTS
# ===================================================================


def test_main_p6_bloqueado_si_task_secret_no_existe(
    monkeypatch,
):
    """
    Si TASK_SECRET no está configurado,
    /pipeline/p6 debe fallar cerrado con 503.

    P6 nunca debe ejecutarse.
    """

    from fastapi.testclient import TestClient
    import app.main as main_module

    async def p6_prohibido(*args, **kwargs):
        raise AssertionError(
            "P6 no debía ejecutarse sin TASK_SECRET."
        )

    monkeypatch.setattr(
        main_module,
        "TASK_SECRET",
        "",
    )

    monkeypatch.setattr(
        main_module,
        "ejecutar_secuencia",
        p6_prohibido,
    )

    client = TestClient(
        main_module.app
    )

    response = client.post(
        "/pipeline/p6",
        json={
            "place_id": "TEST_PLACE_001",
            "approved_by_human": True,
        },
    )

    assert response.status_code == 503


def test_main_p6_rechaza_secret_incorrecto(
    monkeypatch,
):
    """
    Un secreto incorrecto debe devolver 403
    antes de llegar a P6.
    """

    from fastapi.testclient import TestClient
    import app.main as main_module

    async def p6_prohibido(*args, **kwargs):
        raise AssertionError(
            "P6 no debía ejecutarse con secreto incorrecto."
        )

    monkeypatch.setattr(
        main_module,
        "TASK_SECRET",
        "secret-test-correcto",
    )

    monkeypatch.setattr(
        main_module,
        "ejecutar_secuencia",
        p6_prohibido,
    )

    client = TestClient(
        main_module.app
    )

    response = client.post(
        "/pipeline/p6",
        headers={
            "X-Task-Secret":
                "secret-equivocado",
        },
        json={
            "place_id": "TEST_PLACE_001",
            "approved_by_human": True,
        },
    )

    assert response.status_code == 403


def test_main_p6_pasa_aprobacion_humana_al_motor(
    monkeypatch,
):
    """
    El endpoint debe transmitir explícitamente
    approved_by_human al motor P6.
    """

    from fastapi.testclient import TestClient
    import app.main as main_module

    llamadas = []

    async def fake_p6(
        place_id,
        approved_by_human=False,
    ):
        llamadas.append({
            "place_id":
                place_id,

            "approved_by_human":
                approved_by_human,
        })

        return {
            "status":
                "pending_approval"
        }

    monkeypatch.setattr(
        main_module,
        "TASK_SECRET",
        "secret-test",
    )

    monkeypatch.setattr(
        main_module,
        "ejecutar_secuencia",
        fake_p6,
    )

    client = TestClient(
        main_module.app
    )

    response = client.post(
        "/pipeline/p6",
        headers={
            "X-Task-Secret":
                "secret-test",
        },
        json={
            "place_id":
                "TEST_PLACE_001",

            "approved_by_human":
                False,
        },
    )

    assert response.status_code == 200

    assert len(llamadas) == 1

    assert (
        llamadas[0]["approved_by_human"]
        is False
    )


def test_main_antiguo_get_recipient_email_ya_no_existe():
    """
    La antigua ruta GET que modificaba destinatarios
    debe haber desaparecido.
    """

    from fastapi.testclient import TestClient
    import app.main as main_module

    client = TestClient(
        main_module.app
    )

    response = client.get(
        "/setup/recipient-email/"
        "TEST_PLACE_001/"
        "test@example.com"
    )

    assert response.status_code == 404


def test_main_recipient_email_requiere_secret(
    monkeypatch,
):
    """
    La nueva ruta POST para cambiar destinatario
    debe exigir autenticación.
    """

    from fastapi.testclient import TestClient
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "TASK_SECRET",
        "secret-test",
    )

    client = TestClient(
        main_module.app
    )

    response = client.post(
        "/setup/recipient-email",
        json={
            "place_id":
                "TEST_PLACE_001",

            "email":
                "test@example.com",
        },
    )

    assert response.status_code == 403


def test_main_sequence_score_69_no_ejecuta_p5(
    monkeypatch,
):
    """
    /pipeline/sequence debe respetar el gate.

    Score 69:
    P5 no puede ejecutarse.
    """

    from fastapi.testclient import TestClient
    import app.main as main_module

    async def fake_reviews(
        *args,
        **kwargs,
    ):
        return []

    async def fake_guardar_reviews(
        *args,
        **kwargs,
    ):
        return 0

    async def fake_p3(
        *args,
        **kwargs,
    ):
        return {
            "website_title":
                "Test"
        }

    async def fake_p4(
        *args,
        **kwargs,
    ):
        return {
            "lead_score": 69,
            "problema_principal":
                "Problema test",
        }

    async def p5_prohibido(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "P5 no debía ejecutarse para score 69."
        )

    monkeypatch.setattr(
        main_module,
        "obtener_reviews",
        fake_reviews,
    )

    monkeypatch.setattr(
        main_module,
        "procesar_y_guardar_reviews",
        fake_guardar_reviews,
    )

    monkeypatch.setattr(
        main_module,
        "analizar_y_guardar",
        fake_p3,
    )

    monkeypatch.setattr(
        main_module,
        "generar_keypoints",
        fake_p4,
    )

    monkeypatch.setattr(
        main_module,
        "generar_secuencia_emails",
        p5_prohibido,
    )

    client = TestClient(
        main_module.app
    )

    response = client.post(
        "/pipeline/sequence",
        json={
            "place_id":
                "TEST_PLACE_001",

            "url":
                "https://example.com",

            "max_reviews":
                1,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert (
        data["p5"]["status"]
        == "skipped"
    )

    assert (
        data["p5"]["lead_score"]
        == 69
    )


def test_main_daily_sequence_fail_closed_sin_secret(
    monkeypatch,
):
    """
    El cron tampoco puede quedar abierto
    si TASK_SECRET desaparece.
    """

    from fastapi.testclient import TestClient
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "TASK_SECRET",
        "",
    )

    client = TestClient(
        main_module.app
    )

    response = client.post(
        "/tasks/daily-sequence"
    )

    assert response.status_code == 503