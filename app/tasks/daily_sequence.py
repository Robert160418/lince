"""
daily_sequence.py
─────────────────

Tarea automática de seguimiento de Lince.

IMPORTANTE:

- El primer email NO se envía desde esta tarea.
- El primer contacto debe haber sido aprobado y enviado previamente.
- Esta tarea procesa únicamente seguimientos posteriores.
- Respeta los estados seguros de P6 Lince 2.0.
- Nunca interpreta un estado incierto como email enviado.

Se invoca desde:

POST /tasks/daily-sequence

El endpoint está protegido mediante X-Task-Secret y puede ser
ejecutado por el cron del VPS.
"""

import asyncio
from datetime import datetime, timezone

from app.utils.supabase_client import supabase_select
from app.pipelines.p6_email_sender import ejecutar_secuencia


# -------------------------------------------------------------------
# GOOGLE SHEETS OPCIONAL
# -------------------------------------------------------------------

try:
    from app.utils.google_sheets import update_lead_in_sheet

    _SHEETS_OK = True

except Exception:
    _SHEETS_OK = False

    async def update_lead_in_sheet(*a, **k):
        return None


# -------------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------------

# Por ahora conservamos la cadencia histórica.
# Más adelante podemos reemplazarla por una secuencia comercial
# diferente para cada día.
HORAS_ENTRE_EMAILS = 24


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------


def _normalizar_dia(value) -> int:
    """
    Convierte current_email_day a entero seguro.
    """

    try:
        return int(value or 0)

    except (TypeError, ValueError):
        return 0


def _parse_datetime_utc(value):
    """
    Convierte timestamps ISO de Supabase a datetime UTC.

    Soporta:
    - timestamps terminados en Z
    - timestamps con offset
    - timestamps sin timezone
    """

    if not value:
        return None

    try:
        fecha = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

    except (TypeError, ValueError):
        return None

    if fecha.tzinfo is None:
        fecha = fecha.replace(
            tzinfo=timezone.utc
        )

    return fecha.astimezone(
        timezone.utc
    )


async def _actualizar_sheet(
    place_id: str,
    updates: dict,
):
    """
    Actualiza Google Sheets sin bloquear la secuencia si falla.
    """

    if not _SHEETS_OK:
        return

    try:

        leads_data = await supabase_select(
            "leads",
            {
                "place_id":
                    f"eq.{place_id}"
            },
        )

        if (
            not leads_data
            or not isinstance(
                leads_data,
                list,
            )
        ):
            return

        lote_id = (
            leads_data[0].get(
                "lote_id",
                "",
            )
        )

        if not lote_id:
            return

        await update_lead_in_sheet(
            lote_id,
            place_id,
            updates,
        )

    except Exception as e:

        print(
            f"     ⚠️ Sheet no actualizado: {e}"
        )


# -------------------------------------------------------------------
# LÓGICA PRINCIPAL
# -------------------------------------------------------------------


async def run_daily_sequence() -> dict:
    """
    Procesa seguimientos automáticos de leads que ya tuvieron
    correctamente su primer contacto.

    Reglas:

    - current_email_day debe ser >= 1
    - debe existir sent_at del último día confirmado
    - deben haber pasado HORAS_ENTRE_EMAILS
    - secuencia no detenida
    - lead no respondió
    - P6 decide finalmente si puede enviar

    Los estados inciertos nunca se consideran exitosos.
    """

    now = datetime.now(
        timezone.utc
    )

    now_str = now.strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    print(
        f"\n{'=' * 60}"
    )

    print(
        f"📅 SECUENCIA DIARIA LINCE 2.0 — {now_str}"
    )

    print(
        f"{'=' * 60}"
    )

    # ---------------------------------------------------------------
    # SOLO LEADS QUE YA TUVIERON PRIMER CONTACTO
    # ---------------------------------------------------------------

    rows = await supabase_select(
        "emails",
        {
            "current_email_day":
                "gte.1"
        },
    )

    if (
        not rows
        or isinstance(
            rows,
            dict,
        )
    ):

        print(
            "  ⚠️ Sin secuencias activas."
        )

        return {
            "procesados": 0,
            "enviados": 0,
            "omitidos": 0,
            "errores": 0,
            "revision_manual": 0,
            "resultados": [],
        }

    enviados = 0
    omitidos = 0
    errores = 0
    revision_manual = 0

    resultados = []

    # ---------------------------------------------------------------
    # PROCESAR CADA SECUENCIA
    # ---------------------------------------------------------------

    for row in rows:

        place_id = (
            row.get(
                "place_id",
                "",
            )
        )

        company = (
            row.get(
                "company_name",
                place_id,
            )
            or place_id
        )

        current_day = _normalizar_dia(
            row.get(
                "current_email_day"
            )
        )

        # -----------------------------------------------------------
        # VALIDACIÓN BÁSICA
        # -----------------------------------------------------------

        if not place_id:

            errores += 1

            resultados.append({
                "place_id": "",
                "company": company,
                "status": "error",
                "error": (
                    "Registro de emails sin place_id"
                ),
            })

            continue

        # -----------------------------------------------------------
        # SECUENCIA COMPLETA
        # -----------------------------------------------------------

        if current_day >= 5:

            omitidos += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status": "completada",
            })

            continue

        # -----------------------------------------------------------
        # RESPUESTA O STOP
        # -----------------------------------------------------------

        if row.get("replied"):

            print(
                f"  🛑 {company}: "
                "lead ya respondió"
            )

            omitidos += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status": "detenida",
                "reason": "lead respondió",
            })

            continue

        if row.get("sequence_stopped"):

            print(
                f"  🛑 {company}: "
                "secuencia detenida"
            )

            omitidos += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status": "detenida",
                "reason":
                    "sequence_stopped activo",
            })

            continue

        # -----------------------------------------------------------
        # DESTINATARIO
        # -----------------------------------------------------------

        if not row.get(
            "recipient_email"
        ):

            print(
                f"  ⏭ {company}: "
                "sin email destino"
            )

            omitidos += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status": "skipped",
                "reason":
                    "sin recipient_email",
            })

            continue

        # -----------------------------------------------------------
        # VERIFICAR CONFIRMACIÓN DEL ÚLTIMO ENVÍO
        # -----------------------------------------------------------

        last_sent_field = (
            f"sent_at_day{current_day}"
        )

        last_sent_str = row.get(
            last_sent_field
        )

        # Este caso es especialmente importante con P6 Lince 2.0.
        #
        # current_email_day avanzado + sent_at ausente puede significar
        # que el estado de entrega es incierto.
        #
        # Nunca debemos continuar automáticamente.
        if not last_sent_str:

            print(
                f"  🚨 {company}: "
                f"día {current_day} reservado "
                "sin confirmación sent_at"
            )

            revision_manual += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status":
                    "manual_review_required",
                "reason": (
                    f"current_email_day={current_day} "
                    f"pero {last_sent_field} está vacío"
                ),
            })

            await _actualizar_sheet(
                place_id,
                {
                    "P6 Estado":
                        "🚨 Revisión manual",

                    "Estado":
                        "🚨 Estado de envío incierto",
                },
            )

            continue

        # -----------------------------------------------------------
        # PARSEAR FECHA
        # -----------------------------------------------------------

        last_sent = _parse_datetime_utc(
            last_sent_str
        )

        if not last_sent:

            print(
                f"  🚨 {company}: "
                "timestamp inválido"
            )

            revision_manual += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status":
                    "manual_review_required",
                "reason":
                    "timestamp de último envío inválido",
            })

            continue

        # -----------------------------------------------------------
        # CADENCIA
        # -----------------------------------------------------------

        horas_desde_ultimo = (
            now - last_sent
        ).total_seconds() / 3600

        if (
            horas_desde_ultimo
            < HORAS_ENTRE_EMAILS
        ):

            horas_restantes = (
                HORAS_ENTRE_EMAILS
                - horas_desde_ultimo
            )

            print(
                f"  ⏳ {company}: "
                f"faltan {horas_restantes:.1f}h"
            )

            omitidos += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status": "waiting",
                "hours_remaining":
                    round(
                        horas_restantes,
                        1,
                    ),
            })

            continue

        # -----------------------------------------------------------
        # ELEGIBLE
        # -----------------------------------------------------------

        next_day = (
            current_day + 1
        )

        print(
            f"  📧 {company}: "
            f"procesando Día {next_day}…"
        )

        try:

            # No pasamos approved_by_human=True.
            #
            # El primer contacto nunca debe llegar aquí porque
            # la consulta exige current_email_day >= 1.
            #
            # Para seguimientos posteriores P6 no exige esa bandera.
            resultado = await ejecutar_secuencia(
                place_id
            )

        except Exception as e:

            print(
                f"     ❌ Excepción P6: {e}"
            )

            errores += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status": "error",
                "error": str(e),
            })

            continue

        # -----------------------------------------------------------
        # INTERPRETAR ESTADO P6
        # -----------------------------------------------------------

        status = resultado.get(
            "status"
        )

        # -----------------------------------------------------------
        # ERROR EXPLÍCITO
        # -----------------------------------------------------------

        if resultado.get("error"):

            if (
                status
                == "manual_review_required"
            ):

                revision_manual += 1

                print(
                    f"     🚨 Revisión manual: "
                    f"{resultado['error']}"
                )

                resultados.append({
                    "place_id": place_id,
                    "company": company,
                    "status":
                        "manual_review_required",
                    "error":
                        resultado["error"],
                })

                await _actualizar_sheet(
                    place_id,
                    {
                        "P6 Estado":
                            "🚨 Revisión manual",

                        "Estado":
                            "🚨 Revisar antes de continuar",
                    },
                )

            else:

                errores += 1

                print(
                    f"     ❌ Error: "
                    f"{resultado['error']}"
                )

                resultados.append({
                    "place_id": place_id,
                    "company": company,
                    "status": "error",
                    "error":
                        resultado["error"],
                })

            continue

        # -----------------------------------------------------------
        # REVISIÓN MANUAL
        # -----------------------------------------------------------

        if (
            status
            == "manual_review_required"
        ):

            revision_manual += 1

            print(
                f"     🚨 Requiere revisión manual"
            )

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status":
                    "manual_review_required",
                "mensaje":
                    resultado.get(
                        "mensaje",
                        "",
                    ),
            })

            await _actualizar_sheet(
                place_id,
                {
                    "P6 Estado":
                        "🚨 Revisión manual",

                    "Estado":
                        "🚨 Revisar antes de continuar",
                },
            )

            continue

        # -----------------------------------------------------------
        # OTRO PROCESO YA LO RESERVÓ
        # -----------------------------------------------------------

        if (
            status
            == "already_claimed"
        ):

            omitidos += 1

            print(
                f"     ↪ Otro proceso ya "
                "reservó este envío"
            )

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status":
                    "already_claimed",
            })

            continue

        # -----------------------------------------------------------
        # APROBACIÓN
        # -----------------------------------------------------------

        # No debería ocurrir aquí porque current_day >= 1,
        # pero se maneja por seguridad.
        if (
            status
            == "pending_approval"
        ):

            omitidos += 1

            print(
                f"     👀 Pendiente aprobación humana"
            )

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status":
                    "pending_approval",
            })

            continue

        # -----------------------------------------------------------
        # DETENIDA / COMPLETADA
        # -----------------------------------------------------------

        if status in (
            "completada",
            "detenida",
        ):

            print(
                f"     ℹ️ Estado: {status}"
            )

            omitidos += 1

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status": status,
            })

            continue

        # -----------------------------------------------------------
        # ÚNICO ESTADO QUE CUENTA COMO EMAIL ENVIADO
        # -----------------------------------------------------------

        if status != "enviado":

            revision_manual += 1

            print(
                f"     🚨 Estado P6 desconocido: "
                f"{status}"
            )

            resultados.append({
                "place_id": place_id,
                "company": company,
                "status":
                    "manual_review_required",
                "reason": (
                    f"P6 devolvió estado inesperado: "
                    f"{status}"
                ),
            })

            continue

        # -----------------------------------------------------------
        # EMAIL CONFIRMADO
        # -----------------------------------------------------------

        dia_enviado = resultado.get(
            "dia",
            next_day,
        )

        enviado_a = resultado.get(
            "enviado_a",
            "",
        )

        print(
            f"     ✅ Día {dia_enviado} "
            f"enviado a {enviado_a}"
        )

        enviados += 1

        await _actualizar_sheet(
            place_id,
            {
                "P6 Estado":
                    f"✅ Día {dia_enviado}/5 enviado",

                "Fecha Envío":
                    now_str,

                "Estado":
                    f"✅ Secuencia día {dia_enviado}",
            },
        )

        resultados.append({
            "place_id": place_id,
            "company": company,
            "status": "enviado",
            "dia": dia_enviado,
            "enviado_a": enviado_a,
            "message_id":
                resultado.get(
                    "message_id"
                ),
        })

        # -----------------------------------------------------------
        # PROTEGER BREVO
        # -----------------------------------------------------------

        await asyncio.sleep(
            1.2
        )

    # -------------------------------------------------------------------
    # RESUMEN
    # -------------------------------------------------------------------

    print(
        f"\n{'─' * 60}"
    )

    print(
        f"  Procesados      : {len(rows)}"
    )

    print(
        f"  Enviados        : {enviados}"
    )

    print(
        f"  Omitidos        : {omitidos}"
    )

    print(
        f"  Revisión manual : {revision_manual}"
    )

    print(
        f"  Errores         : {errores}"
    )

    print(
        f"{'=' * 60}\n"
    )

    return {
        "procesados":
            len(rows),

        "enviados":
            enviados,

        "omitidos":
            omitidos,

        "revision_manual":
            revision_manual,

        "errores":
            errores,

        "resultados":
            resultados,
    }
