import asyncio
import hashlib
import hmac
import secrets
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests as req

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

from fastapi import (
    BackgroundTasks,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    ADMIN_PASSWORD,
    ADMIN_SESSION_SECRET,
    SUPABASE_HEADERS,
    SUPABASE_KEY,
    SUPABASE_URL,
    TASK_SECRET,
)

from app.utils.supabase_client import supabase_select

from app.pipelines.p1_google_maps import (
    procesar_y_guardar_leads,
    scrape_google_maps,
)

from app.utils.batch_processor import (
    MIN_SCORE_CRM,
    process_lote,
)

from app.pipelines.p2_reviews import (
    obtener_reviews,
    procesar_y_guardar_reviews,
)

from app.pipelines.p3_website_analysis import (
    analizar_y_guardar,
)

from app.pipelines.p4_keypoints import (
    generar_keypoints,
)

from app.pipelines.p5_email_generator import (
    generar_secuencia_emails,
)

from app.pipelines.p6_email_sender import (
    ejecutar_secuencia,
)


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Lince API",
    version="2.0",
)


# ===================================================================
# CORS
# ===================================================================

# TODO:
# Antes de producción final debemos sustituir "*" por los dominios
# exactos que realmente consumen Lince.
#
# Esto se mantiene temporalmente por compatibilidad con la interfaz
# actual. CORS NO sustituye autenticación.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================================================================
# ARCHIVOS ESTÁTICOS
# ===================================================================

app.mount(
    "/static",
    StaticFiles(
        directory=BASE_DIR / "static"
    ),
    name="static",
)


@app.get(
    "/",
    include_in_schema=False,
)
async def index():
    return FileResponse(
        BASE_DIR / "templates" / "index.html",
        media_type="text/html; charset=utf-8",
    )


# ===================================================================
# SEGURIDAD
# ===================================================================


def require_task_secret(
    x_task_secret: str,
):
    """
    Protección fail-closed.

    Si TASK_SECRET no está configurado,
    las operaciones sensibles NO se ejecutan.

    Nunca convertir una ausencia de configuración
    en permiso implícito.
    """

    if not TASK_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "TASK_SECRET no está configurado. "
                "Operación sensible bloqueada."
            ),
        )

    if not x_task_secret:
        raise HTTPException(
            status_code=403,
            detail="Acceso no autorizado",
        )

    if not secrets.compare_digest(
        x_task_secret,
        TASK_SECRET,
    ):
        raise HTTPException(
            status_code=403,
            detail="Acceso no autorizado",
        )


def verify_admin_session(cookie_val: str) -> bool:
    if not cookie_val or not ADMIN_SESSION_SECRET:
        return False
    try:
        timestamp_str, signature = cookie_val.split(".", 1)
        timestamp = int(timestamp_str)

        ahora = time.time()
        age = ahora - timestamp

        # 12 horas = 43200 segundos. Tolerancia de reloj = 60 seg en el futuro.
        if age > 43200 or age < -60:
            return False

        expected_sig = hmac.new(
            ADMIN_SESSION_SECRET.encode(),
            timestamp_str.encode(),
            hashlib.sha256
        ).hexdigest()

        return secrets.compare_digest(expected_sig, signature)
    except Exception:
        return False


def verify_admin_or_task_secret(
    request: Request,
    x_task_secret: str = Header(default="", alias="X-Task-Secret"),
):
    """
    Validación reutilizable para aceptar DOS mecanismos:
    A) X-Task-Secret válido
    B) cookie administrativa válida y no expirada
    """
    if not TASK_SECRET and not ADMIN_SESSION_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Ningún mecanismo de seguridad está configurado."
        )

    # 1. Validar X-Task-Secret si se envía
    if TASK_SECRET and x_task_secret:
        if secrets.compare_digest(x_task_secret, TASK_SECRET):
            return True

    # 2. Validar Cookie
    cookie_val = request.cookies.get("lince_admin_session")
    if cookie_val and verify_admin_session(cookie_val):
        return True

    raise HTTPException(status_code=403, detail="Acceso no autorizado")



def validar_email_basico(
    email: str,
):
    email = (
        email
        .strip()
        .lower()
    )

    if (
        "@" not in email
        or "." not in email.split("@")[-1]
        or " " in email
    ):
        raise HTTPException(
            status_code=422,
            detail="Email de destinatario inválido",
        )

    return email


async def actualizar_recipient_email(
    place_id: str,
    email: str,
):
    """
    Actualiza el destinatario de una secuencia.

    Esta función no es endpoint público.
    Los endpoints que la utilizan deben autenticar
    al usuario previamente.
    """

    if not SUPABASE_URL:
        raise HTTPException(
            status_code=503,
            detail="Supabase no está configurado",
        )

    email = validar_email_basico(
        email
    )

    encoded_place_id = urllib.parse.quote(
        place_id,
        safe="",
    )

    url = (
        f"{SUPABASE_URL}"
        f"/rest/v1/emails"
        f"?place_id=eq.{encoded_place_id}"
    )

    headers = {
        **SUPABASE_HEADERS,
        "Prefer": "return=minimal",
    }

    try:
        response = await asyncio.to_thread(
            req.patch,
            url,
            json={
                "recipient_email": email
            },
            headers=headers,
            timeout=15,
        )

    except req.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No se pudo actualizar "
                "el destinatario."
            ),
        ) from exc

    if not (
        200
        <= response.status_code
        < 300
    ):
        raise HTTPException(
            status_code=502,
            detail=(
                "Supabase rechazó la actualización "
                f"del destinatario: "
                f"{response.status_code}"
            ),
        )

    return {
        "status": "ok",
        "place_id": place_id,
        "recipient_email": email,
    }


# ===================================================================
# MODELOS
# ===================================================================

class LoginBody(BaseModel):
    password: str

class P1Body(BaseModel):
    query: str
    limit: int = 20


class P2Body(BaseModel):
    place_id: str
    max_reviews: int = 10


class P3Body(BaseModel):
    place_id: str
    url: str


class P4Body(BaseModel):
    place_id: str


class P5Body(BaseModel):
    place_id: str


class P6Body(BaseModel):
    place_id: str

    to_email: Optional[str] = None
    to_name: Optional[str] = None

    # CRÍTICO:
    # False por defecto.
    #
    # El primer contacto nunca puede salir
    # por accidente.
    approved_by_human: bool = False


class SequenceBody(BaseModel):
    place_id: str
    url: str
    max_reviews: int = 5


class BatchBody(BaseModel):
    lote_id: str


class RecipientEmailBody(BaseModel):
    place_id: str
    email: str


# ===================================================================
# ENDPOINTS GENERALES
# ===================================================================

@app.post("/admin/login")
async def admin_login(body: LoginBody, response: Response):
    if not ADMIN_PASSWORD or not ADMIN_SESSION_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Autenticación administrativa no configurada."
        )

    if not secrets.compare_digest(body.password, ADMIN_PASSWORD):
        raise HTTPException(
            status_code=403,
            detail="Contraseña incorrecta."
        )

    timestamp_str = str(int(time.time()))
    signature = hmac.new(
        ADMIN_SESSION_SECRET.encode(),
        timestamp_str.encode(),
        hashlib.sha256
    ).hexdigest()

    session_val = f"{timestamp_str}.{signature}"

    response.set_cookie(
        key="lince_admin_session",
        value=session_val,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
        max_age=43200,
    )

    return {"status": "ok", "message": "Sesión iniciada"}


@app.get("/leads")
async def get_leads():
    """
    Endpoint histórico.

    TODO:
    proteger toda la interfaz Lince mediante
    autenticación administrativa antes de
    exposición pública definitiva.
    """

    return await supabase_select(
        "leads"
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0",
    }


@app.get("/sheets/ping")
async def sheets_ping():
    try:
        from app.utils.google_sheets import (
            _get_client,
            get_sheet_url,
        )

        client = _get_client()

        if not client:
            return {
                "status": "error",
                "detail": (
                    "No se pudo crear "
                    "el cliente de Google Sheets."
                ),
            }

        url = await get_sheet_url()

        return {
            "status": "ok",
            "sheet_url": url,
        }

    except Exception as exc:
        return {
            "status": "error",
            "detail": str(exc),
        }


@app.get("/debug")
async def debug():
    """
    No revela claves.

    TODO:
    retirar/proteger este endpoint antes
    de producción definitiva.
    """

    return {
        "supabase_url_configurada":
            bool(SUPABASE_URL),

        "supabase_key_configurada":
            bool(SUPABASE_KEY),

        "task_secret_configurado":
            bool(TASK_SECRET),
    }


@app.get("/test-db")
async def test_db():
    try:
        data = await supabase_select(
            "leads"
        )

        return {
            "tablas": "ok",
            "registros": len(data),
        }

    except Exception as exc:
        return {
            "error": str(exc),
        }


# ===================================================================
# DESTINATARIO
# ===================================================================


@app.post(
    "/setup/recipient-email"
)
async def set_recipient_email(
    request: Request,
    body: RecipientEmailBody,
    x_task_secret: str = Header(
        default="",
        alias="X-Task-Secret",
    ),
):
    """
    Operación protegida.

    Reemplaza el antiguo GET público que
    modificaba datos.
    """

    verify_admin_or_task_secret(
        request,
        x_task_secret
    )

    return await actualizar_recipient_email(
        body.place_id,
        body.email,
    )


# ===================================================================
# LOTES
# ===================================================================


@app.get("/lotes")
async def get_lotes():
    leads = await supabase_select(
        "leads"
    )

    lotes: dict = {}

    for lead in leads:
        lid = (
            lead.get("lote_id")
            or "sin_lote"
        )

        if lid not in lotes:
            lotes[lid] = {
                "lote_id": lid,
                "query":
                    lead.get(
                        "query",
                        "",
                    ),
                "count": 0,
                "place_ids": [],
            }

        lotes[lid]["count"] += 1

        lotes[lid][
            "place_ids"
        ].append(
            lead.get(
                "place_id",
                "",
            )
        )

    return sorted(
        lotes.values(),
        key=lambda item:
            item["lote_id"],
        reverse=True,
    )


# ===================================================================
# PIPELINE BATCH
# ===================================================================


@app.post("/pipeline/batch")
async def ejecutar_batch(
    body: BatchBody,
):
    """
    Ejecuta P2-P5 mediante el batch seguro.

    El batch de Lince 2.0 NO ejecuta P6.
    """

    return await process_lote(
        body.lote_id
    )


# ===================================================================
# P1
# ===================================================================


@app.post("/pipeline/p1")
async def ejecutar_p1(
    body: P1Body,
    background_tasks: BackgroundTasks,
):
    resultados = (
        await scrape_google_maps(
            query=body.query,
            limit=body.limit,
        )
    )

    resultado = (
        await procesar_y_guardar_leads(
            resultados,
            query=body.query,
        )
    )

    lote_id = (
        resultado.get(
            "lote_id",
            "",
        )
        if isinstance(
            resultado,
            dict,
        )
        else ""
    )

    if lote_id:
        background_tasks.add_task(
            process_lote,
            lote_id,
        )

    guardados = (
        resultado.get(
            "guardados",
            0,
        )
        if isinstance(
            resultado,
            dict,
        )
        else resultado
    )

    return {
        "status": "ok",

        "message": (
            f"Lote '{lote_id}' creado. "
            "Pipeline seguro P2-P5 "
            "corriendo en segundo plano. "
            "P6 requiere aprobación."
        ),

        "encontrados":
            len(resultados),

        "guardados":
            guardados,

        "lote_id":
            lote_id,

        "sheet_url":
            (
                "https://docs.google.com/"
                "spreadsheets/d/"
                "1hgNERuux2eZ1MDv-tgCDp_qva-fqf1RHF9Qu4Qysjjg/"
                "edit"
            ),

        "leads":
            resultados,
    }


# ===================================================================
# P2
# ===================================================================


@app.post("/pipeline/p2")
async def ejecutar_p2(
    body: P2Body,
):
    reviews = (
        await obtener_reviews(
            place_id=body.place_id,
            max_reviews=body.max_reviews,
        )
    )

    guardadas = (
        await procesar_y_guardar_reviews(
            body.place_id,
            reviews,
        )
    )

    return {
        "status": "ok",

        "place_id":
            body.place_id,

        "reviews_encontradas":
            len(reviews),

        "reviews_guardadas":
            guardadas,
    }


# ===================================================================
# P3
# ===================================================================


@app.post("/pipeline/p3")
async def ejecutar_p3(
    body: P3Body,
):
    datos = (
        await analizar_y_guardar(
            place_id=body.place_id,
            url=body.url,
        )
    )

    datos["place_id"] = (
        body.place_id
    )

    return {
        "status": "ok",
        "resultado": datos,
    }


# ===================================================================
# P4
# ===================================================================


@app.post("/pipeline/p4")
async def ejecutar_p4(
    body: P4Body,
):
    resultado = (
        await generar_keypoints(
            body.place_id
        )
    )

    if resultado.get("error"):
        return {
            "status": "error",
            "error":
                resultado["error"],
        }

    return {
        "status": "ok",
        "resultado": resultado,
    }


# ===================================================================
# P5
# ===================================================================


@app.post("/pipeline/p5")
async def ejecutar_p5(
    request: Request,
    body: P5Body,
    x_task_secret: str = Header(
        default="",
        alias="X-Task-Secret",
    ),
):
    """
    P5 es una operación comercial interna.

    Se protege para evitar generación arbitraria
    de campañas desde Internet.
    """

    verify_admin_or_task_secret(
        request,
        x_task_secret
    )

    resultado = (
        await generar_secuencia_emails(
            body.place_id
        )
    )

    if resultado.get("error"):
        return {
            "status": "error",
            "error":
                resultado["error"],
        }

    emails = resultado.get(
        "emails",
        [],
    )

    return {
        "status": "ok",

        "emails_generados":
            len(emails),

        "emails":
            emails,

        "requiere_aprobacion":
            resultado.get(
                "requiere_aprobacion",
                True,
            ),
    }


# ===================================================================
# P6
# ===================================================================


@app.post("/pipeline/p6")
async def ejecutar_p6(
    request: Request,
    body: P6Body,

    x_task_secret: str = Header(
        default="",
        alias="X-Task-Secret",
    ),
):
    """
    Endpoint sensible.

    Requiere:

    1. Autenticación (TASK_SECRET o cookie de administrador).
    2. approved_by_human=True para enviar cualquier email.

    El motor P6 mantiene además sus propias
    protecciones de idempotencia.
    """

    verify_admin_or_task_secret(
        request,
        x_task_secret
    )

    if body.to_email:
        await actualizar_recipient_email(
            body.place_id,
            body.to_email,
        )

    resultado = (
        await ejecutar_secuencia(
            body.place_id,

            approved_by_human=(
                body.approved_by_human
            ),
        )
    )

    if resultado.get("error"):
        return {
            "status": "error",
            "error":
                resultado["error"],
        }

    return resultado


# ===================================================================
# SECUENCIA MANUAL P2-P5
# ===================================================================


@app.post("/pipeline/sequence")
async def ejecutar_secuencia_completa(
    body: SequenceBody,
):
    """
    Endpoint histórico/manual.

    Importante:
    respeta el gate comercial antes de P5.

    NO ejecuta P6.
    """

    salida = {
        "status": "ok",
        "place_id":
            body.place_id,
    }

    # -------------------------------
    # P2
    # -------------------------------

    try:
        reviews = (
            await obtener_reviews(
                place_id=body.place_id,
                max_reviews=body.max_reviews,
            )
        )

        guardadas = (
            await procesar_y_guardar_reviews(
                body.place_id,
                reviews,
            )
        )

        salida["p2"] = {
            "status": "ok",

            "reviews_encontradas":
                len(reviews),

            "reviews_guardadas":
                guardadas,
        }

    except Exception as exc:
        salida["p2"] = {
            "status": "error",
            "error": str(exc),
        }

    # -------------------------------
    # P3
    # -------------------------------

    try:
        datos = (
            await analizar_y_guardar(
                place_id=body.place_id,
                url=body.url,
            )
        )

        salida["p3"] = {
            "status": "ok",
            "resultado": datos,
        }

    except Exception as exc:
        salida["p3"] = {
            "status": "error",
            "error": str(exc),
        }

    # -------------------------------
    # P4
    # -------------------------------

    kp = None

    try:
        kp = await generar_keypoints(
            body.place_id
        )

        if kp.get("error"):
            salida["p4"] = {
                "status": "error",
                "error":
                    kp["error"],
            }

            kp = None

        else:
            salida["p4"] = {
                "status": "ok",
                "resultado": kp,
            }

    except Exception as exc:
        salida["p4"] = {
            "status": "error",
            "error": str(exc),
        }

        kp = None

    # -------------------------------
    # GATE COMERCIAL
    # -------------------------------

    score = 0

    if kp:
        try:
            score = int(
                kp.get(
                    "lead_score",
                    0,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            score = 0

    if (
        not kp
        or score < MIN_SCORE_CRM
    ):
        salida["p5"] = {
            "status": "skipped",

            "reason": (
                "Lead no supera "
                "el gate comercial."
            ),

            "lead_score":
                score,

            "min_score":
                MIN_SCORE_CRM,
        }

        return salida

    # -------------------------------
    # P5
    # -------------------------------

    try:
        em = (
            await generar_secuencia_emails(
                body.place_id
            )
        )

        if em.get("error"):
            salida["p5"] = {
                "status": "error",
                "error":
                    em["error"],
            }

        else:
            emails = em.get(
                "emails",
                [],
            )

            salida["p5"] = {
                "status": "ok",

                "emails_generados":
                    len(emails),

                "emails":
                    emails,

                "requiere_aprobacion":
                    em.get(
                        "requiere_aprobacion",
                        True,
                    ),
            }

    except Exception as exc:
        salida["p5"] = {
            "status": "error",
            "error": str(exc),
        }

    return salida


# ===================================================================
# DAILY SEQUENCE
# ===================================================================


@app.post("/tasks/daily-sequence")
async def tarea_secuencia_diaria(
    x_task_secret: str = Header(
        default="",
        alias="X-Task-Secret",
    ),
):
    """
    Cron protegido.

    Protección FAIL-CLOSED:

    - Si TASK_SECRET no existe -> bloqueado.
    - Si no coincide -> bloqueado.
    - Nunca inicia campañas nuevas.
    - daily_sequence solo continúa campañas
      cuyo primer contacto ya fue enviado.
    """

    require_task_secret(
        x_task_secret
    )

    from app.tasks.daily_sequence import (
        run_daily_sequence,
    )

    resultado = (
        await run_daily_sequence()
    )

    return {
        "status": "ok",
        **resultado,
    }