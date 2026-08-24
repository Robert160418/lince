import re
import urllib.parse
from datetime import datetime, timezone

import requests

from app.config import (
    BREVO_API_KEY,
    SUPABASE_URL,
    SUPABASE_HEADERS,
)
from app.utils.supabase_client import supabase_select


BREVO_URL = "https://api.brevo.com/v3/smtp/email"

FROM_EMAIL = "roberto@noboweb.com"
FROM_NAME = "Roberto | Noboweb"

REQUEST_TIMEOUT_SECONDS = 20

_UNSET = object()


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------


def _email_valido(value) -> bool:
    """
    Validación básica del destinatario antes de intentar el envío.
    """

    if not value:
        return False

    email = str(value).strip()

    patron = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    return bool(
        re.match(
            patron,
            email,
        )
    )


def _normalizar_dia(value) -> int:
    """
    Convierte current_email_day a entero seguro.
    """

    try:
        dia = int(value or 0)
    except (TypeError, ValueError):
        return 0

    return dia


def _api_key_valida() -> bool:
    """
    Evita intentar envíos con una API key vacía o placeholder.
    """

    if not BREVO_API_KEY:
        return False

    key = str(
        BREVO_API_KEY
    ).strip().lower()

    if len(key) < 10:
        return False

    placeholders = (
        "tu_key",
        "example",
        "none",
        "your_key",
    )

    return not any(
        item in key
        for item in placeholders
    )


# -------------------------------------------------------------------
# SUPABASE — PATCH SEGURO
# -------------------------------------------------------------------


def _patch_email_row(
    place_id: str,
    update_data: dict,
    expected_current_day=_UNSET,
    return_representation: bool = False,
) -> dict:
    """
    Actualiza el registro de emails directamente mediante PostgREST.

    Si expected_current_day se proporciona, realiza una actualización
    condicional tipo compare-and-set.

    Esto permite que solamente un proceso pueda reservar un email
    determinado antes del envío.
    """

    place_encoded = urllib.parse.quote(
        str(place_id),
        safe="",
    )

    filtros = [
        f"place_id=eq.{place_encoded}"
    ]

    if expected_current_day is not _UNSET:

        if expected_current_day is None:

            filtros.append(
                "current_email_day=is.null"
            )

        else:

            filtros.append(
                "current_email_day="
                f"eq.{int(expected_current_day)}"
            )

    query = "&".join(
        filtros
    )

    url = (
        f"{SUPABASE_URL}/rest/v1/emails?"
        f"{query}"
    )

    headers = {
        **SUPABASE_HEADERS,
        "Content-Type": "application/json",
        "Prefer": (
            "return=representation"
            if return_representation
            else "return=minimal"
        ),
    }

    try:

        response = requests.patch(
            url,
            json=update_data,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    except requests.RequestException as e:

        return {
            "ok": False,
            "error": (
                f"Error conectando con Supabase: {e}"
            ),
        }

    if response.status_code not in (
        200,
        201,
        204,
    ):

        return {
            "ok": False,
            "status": response.status_code,
            "error": (
                response.text[:500]
                if response.text
                else "Error Supabase"
            ),
        }

    # ---------------------------------------------------------------
    # Compare-and-set
    # ---------------------------------------------------------------

    if return_representation:

        try:
            data = response.json()
        except Exception:
            data = []

        # Si ningún registro cumplía el filtro esperado,
        # otro proceso pudo haberlo actualizado primero.
        if not data:

            return {
                "ok": False,
                "conflict": True,
                "error": (
                    "El estado cambió antes de completar "
                    "la operación."
                ),
            }

        return {
            "ok": True,
            "data": data,
        }

    return {
        "ok": True,
        "status": response.status_code,
    }


# -------------------------------------------------------------------
# BREVO
# -------------------------------------------------------------------


def _enviar_brevo(
    to_email: str,
    to_name: str,
    asunto: str,
    cuerpo: str,
) -> dict:
    """
    Envía un único email mediante Brevo.

    Importante:

    Si ocurre un timeout o error de red, consideramos que el estado
    del envío es INCIERTO.

    No debemos reintentar automáticamente porque Brevo podría haber
    recibido el mensaje aunque nuestra aplicación no recibiera la
    respuesta.
    """

    if not _api_key_valida():

        return {
            "ok": False,
            "uncertain": False,
            "error": (
                "BREVO_API_KEY no configurada "
                "o inválida."
            ),
        }

    payload = {
        "sender": {
            "name": FROM_NAME,
            "email": FROM_EMAIL,
        },
        "to": [
            {
                "email": to_email,
                "name": to_name,
            }
        ],
        "subject": asunto,
        "textContent": cuerpo,
    }

    try:

        response = requests.post(
            BREVO_URL,
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )

    except requests.RequestException as e:

        # No sabemos con certeza si Brevo recibió la solicitud.
        # Nunca reintentar automáticamente este email.
        return {
            "ok": False,
            "uncertain": True,
            "error": (
                "Resultado del envío incierto por "
                f"problema de conexión: {e}"
            ),
        }

    if response.status_code not in (
        200,
        201,
        202,
    ):

        return {
            "ok": False,
            "uncertain": False,
            "status": response.status_code,
            "error": (
                response.text[:500]
                if response.text
                else "Brevo rechazó el envío."
            ),
        }

    message_id = None

    try:

        response_data = response.json()

        if isinstance(
            response_data,
            dict,
        ):
            message_id = (
                response_data.get(
                    "messageId"
                )
            )

    except Exception:
        pass

    return {
        "ok": True,
        "status": response.status_code,
        "message_id": message_id,
    }


# -------------------------------------------------------------------
# P6 PRINCIPAL
# -------------------------------------------------------------------


async def ejecutar_secuencia(
    place_id: str,
    approved_by_human: bool = False,
) -> dict:
    """
    Procesa UN email de la secuencia.

    SEGURIDAD LINCE 2.0:

        - TEMPORAL: todos los contactos requieren aprobación humana
            hasta implementar detección fiable de respuestas.
    - Nunca envía si el lead respondió.
    - Nunca envía si la secuencia está detenida.
    - Nunca envía dos veces el mismo día automáticamente.
    - Reserva el día en Supabase ANTES de contactar a Brevo.
    - Si el estado de entrega es incierto, bloquea la secuencia.
    """

    # ---------------------------------------------------------------
    # OBTENER SECUENCIA
    # ---------------------------------------------------------------

    email_rows = await supabase_select(
        "emails",
        {
            "place_id":
                f"eq.{place_id}"
        },
    )

    if not email_rows:

        return {
            "error": (
                f"No hay secuencia de emails para "
                f"{place_id}. Ejecuta P5 primero."
            )
        }

    # P5 nuevo impide duplicados.
    # Si existen duplicados históricos, no elegir uno arbitrariamente.
    if len(email_rows) != 1:

        return {
            "status":
                "manual_review_required",

            "error": (
                f"Se encontraron {len(email_rows)} "
                "secuencias para este place_id. "
                "Requiere revisión manual antes de enviar."
            ),
        }

    row = email_rows[0]

    # ---------------------------------------------------------------
    # RESPUESTA / STOP
    # ---------------------------------------------------------------

    if row.get("replied"):

        return {
            "status": "detenida",
            "mensaje": (
                "El lead ya respondió. "
                "No se enviarán más emails."
            ),
        }

    if row.get("sequence_stopped"):

        return {
            "status": "detenida",
            "mensaje": (
                "La secuencia está detenida."
            ),
        }

    # ---------------------------------------------------------------
    # ESTADO ACTUAL
    # ---------------------------------------------------------------

    raw_current_day = row.get(
        "current_email_day"
    )

    current_day = _normalizar_dia(
        raw_current_day
    )

    if current_day < 0 or current_day > 5:

        return {
            "status":
                "manual_review_required",

            "error": (
                "current_email_day contiene "
                f"un valor inválido: {current_day}"
            ),
        }

    # ---------------------------------------------------------------
    # DETECTAR ESTADO INCONSISTENTE
    # ---------------------------------------------------------------

    # Si Supabase dice que ya avanzamos a un día pero no existe
    # sent_at para ese día, pudo ocurrir:
    #
    # Brevo aceptó el mensaje pero la confirmación DB falló.
    #
    # Bajo ninguna circunstancia avanzar al email siguiente.
    if current_day > 0:

        sent_at_actual = row.get(
            f"sent_at_day{current_day}"
        )

        if not sent_at_actual:

            return {
                "status":
                    "manual_review_required",

                "error": (
                    f"El día {current_day} aparece reservado "
                    "pero no existe confirmación sent_at. "
                    "El envío puede haber ocurrido. "
                    "No se realizará ningún reintento automático."
                ),
            }

    # ---------------------------------------------------------------
    # SECUENCIA COMPLETA
    # ---------------------------------------------------------------

    if current_day >= 5:

        return {
            "status": "completada",
            "mensaje": (
                "Secuencia de 5 emails completada."
            ),
        }

    next_day = (
        current_day + 1
    )

    # ---------------------------------------------------------------
    # APROBACIÓN HUMANA PARA CADA CONTACTO
    # ---------------------------------------------------------------

    if not approved_by_human:

        return {
            "status":
                "pending_approval",

            "dia":
                next_day,

            "mensaje": (
                "TEMPORAL: todos los contactos requieren "
                "aprobación humana hasta implementar detección "
                "fiable de respuestas."
            ),
        }

    # ---------------------------------------------------------------
    # CONTENIDO
    # ---------------------------------------------------------------

    asunto = row.get(
        f"email_{next_day}_subject"
    )

    cuerpo = row.get(
        f"email_{next_day}_body"
    )

    to_email = row.get(
        "recipient_email"
    )

    to_name = (
        row.get(
            "company_name",
            "",
        )
        or ""
    )

    if not asunto or not cuerpo:

        return {
            "error": (
                f"No hay contenido completo "
                f"para el día {next_day}."
            )
        }

    if not _email_valido(
        to_email
    ):

        return {
            "error": (
                "No existe un email de destinatario "
                "válido. Revisa recipient_email."
            )
        }

    to_email = str(
        to_email
    ).strip()

    # Protección adicional.
    # Si sent_at del próximo día ya existe, no intentar enviar.
    if row.get(
        f"sent_at_day{next_day}"
    ):

        return {
            "status":
                "manual_review_required",

            "error": (
                f"El día {next_day} ya tiene "
                "sent_at registrado aunque "
                "current_email_day no coincide. "
                "No se enviará nuevamente."
            ),
        }

    # ---------------------------------------------------------------
    # RESERVAR EL DÍA ANTES DE BREVO
    # ---------------------------------------------------------------

    # Este PATCH es condicional.
    #
    # Dos procesos simultáneos pueden intentar enviar,
    # pero únicamente uno podrá cambiar:
    #
    # current_day → next_day
    #
    # El segundo proceso encontrará conflicto y se detendrá.
    claim = _patch_email_row(
        place_id=place_id,

        update_data={
            "current_email_day":
                next_day,
        },

        expected_current_day=
            raw_current_day,

        return_representation=True,
    )

    if not claim.get("ok"):

        if claim.get(
            "conflict"
        ):

            return {
                "status":
                    "already_claimed",

                "mensaje": (
                    "Otro proceso modificó la secuencia. "
                    "No se enviará un duplicado."
                ),
            }

        return {
            "status":
                "manual_review_required",

            "error": (
                "No fue posible reservar el "
                f"email del día {next_day}: "
                f"{claim.get('error')}"
            ),
        }

    # ---------------------------------------------------------------
    # ENVIAR CON BREVO
    # ---------------------------------------------------------------

    resultado = _enviar_brevo(
        to_email=to_email,
        to_name=to_name,
        asunto=str(asunto),
        cuerpo=str(cuerpo),
    )

    # ---------------------------------------------------------------
    # ERROR / INCERTIDUMBRE
    # ---------------------------------------------------------------

    if not resultado.get("ok"):

        # Si existe cualquier posibilidad de que Brevo haya recibido
        # el mensaje, NO revertimos current_email_day.
        #
        # Así la próxima ejecución detectará:
        #
        # current_day avanzado + sent_at ausente
        #
        # y bloqueará automáticamente la secuencia.
        if resultado.get(
            "uncertain"
        ):

            return {
                "status":
                    "manual_review_required",

                "dia":
                    next_day,

                "enviado_a":
                    to_email,

                "error":
                    resultado.get(
                        "error"
                    ),

                "mensaje": (
                    "El estado del envío es incierto. "
                    "No se reintentará automáticamente "
                    "para evitar duplicados."
                ),
            }

        # -----------------------------------------------------------
        # BREVO RECHAZÓ CLARAMENTE EL EMAIL
        # -----------------------------------------------------------

        # En este caso sí podemos intentar devolver el día anterior
        # porque sabemos que Brevo respondió con error.
        rollback = _patch_email_row(
            place_id=place_id,

            update_data={
                "current_email_day":
                    current_day,
            },

            expected_current_day=
                next_day,

            return_representation=True,
        )

        if not rollback.get("ok"):

            return {
                "status":
                    "manual_review_required",

                "error": (
                    "Brevo rechazó el email y "
                    "Supabase no pudo revertir "
                    "la reserva. Revisión manual requerida."
                ),

                "brevo_error":
                    resultado.get(
                        "error"
                    ),
            }

        return {
            "error": (
                "Brevo rechazó el envío: "
                f"{resultado.get('error')}"
            )
        }

    # ---------------------------------------------------------------
    # BREVO CONFIRMÓ ENVÍO
    # ---------------------------------------------------------------

    now = datetime.now(
        timezone.utc
    ).isoformat()

    confirmacion = _patch_email_row(
        place_id=place_id,

        update_data={
            f"sent_at_day{next_day}":
                now,
        },

        expected_current_day=
            next_day,

        return_representation=True,
    )

    # ---------------------------------------------------------------
    # BREVO ENVIÓ, PERO DB NO CONFIRMÓ
    # ---------------------------------------------------------------

    if not confirmacion.get("ok"):

        # NO revertimos.
        #
        # El email ya fue aceptado por Brevo.
        # Revertir permitiría enviarlo otra vez.
        return {
            "status":
                "manual_review_required",

            "dia":
                next_day,

            "enviado_a":
                to_email,

            "asunto":
                asunto,

            "message_id":
                resultado.get(
                    "message_id"
                ),

            "mensaje": (
                "Brevo aceptó el email pero Supabase "
                "no pudo registrar sent_at. "
                "NO reintentar automáticamente."
            ),

            "db_error":
                confirmacion.get(
                    "error"
                ),
        }

    # ---------------------------------------------------------------
    # ÉXITO COMPLETO
    # ---------------------------------------------------------------

    print(
        f"P6 Lince 2.0 — "
        f"Email día {next_day} enviado "
        f"a {to_email}"
    )

    return {
        "status":
            "enviado",

        "dia":
            next_day,

        "enviado_a":
            to_email,

        "asunto":
            asunto,

        "sent_at":
            now,

        "message_id":
            resultado.get(
                "message_id"
            ),
    }