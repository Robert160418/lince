"""
daily_sequence.py
─────────────────
Tarea diaria: envía el siguiente email de la secuencia a los leads que
llevan ≥ HORAS_ENTRE_EMAILS desde su último envío y aún no completaron
los 5 días.

Se invoca desde el endpoint POST /tasks/daily-sequence (protegido con
X-Task-Secret) que a su vez es llamado por el cron del VPS cada mañana.
"""

import asyncio
from datetime import datetime, timezone

from app.utils.supabase_client import supabase_select
from app.pipelines.p6_email_sender import ejecutar_secuencia

try:
    from app.utils.google_sheets import update_lead_in_sheet
    _SHEETS_OK = True
except Exception:
    _SHEETS_OK = False
    async def update_lead_in_sheet(*a, **k): return None

# ── Configuración ─────────────────────────────────────────────────────────────
HORAS_ENTRE_EMAILS = 24   # mínimo de horas entre emails consecutivos


# ── Lógica principal ──────────────────────────────────────────────────────────
async def run_daily_sequence() -> dict:
    """
    Recorre la tabla `emails` buscando leads con secuencia activa y envía
    el siguiente email cuando han pasado al menos HORAS_ENTRE_EMAILS.

    Retorna un resumen con contadores y lista de resultados por lead.
    """
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")

    print(f"\n{'='*55}")
    print(f"📅 SECUENCIA DIARIA — {now_str}")
    print(f"{'='*55}")

    # Traer todos los registros con al menos 1 email enviado
    rows = await supabase_select("emails", {"current_email_day": "gte.1"})

    if not rows or isinstance(rows, dict):
        print("  ⚠️  Sin registros activos en tabla emails")
        return {"procesados": 0, "enviados": 0, "omitidos": 0, "errores": 0, "resultados": []}

    enviados = 0
    omitidos = 0
    errores  = 0
    resultados = []

    for row in rows:
        place_id    = row.get("place_id", "")
        company     = row.get("company_name", place_id)
        current_day = row.get("current_email_day", 0)

        # ── Filtros de salida rápida ──────────────────────────────────────────
        if current_day >= 5:
            continue  # secuencia ya completada

        if row.get("sequence_stopped") or row.get("replied"):
            continue  # detenida manualmente o lead respondió

        if not row.get("recipient_email"):
            continue  # sin email destino — no se puede enviar

        # ── Verificar timing: ≥ HORAS_ENTRE_EMAILS desde el último envío ─────
        last_sent_field = f"sent_at_day{current_day}"
        last_sent_str   = row.get(last_sent_field)

        if not last_sent_str:
            # No hay timestamp del último envío → omitir por seguridad
            print(f"  ⏭  {company}: sin timestamp para día {current_day}")
            omitidos += 1
            continue

        try:
            last_sent = datetime.fromisoformat(
                last_sent_str.replace("Z", "+00:00")
            )
        except ValueError:
            omitidos += 1
            continue

        horas_desde_ultimo = (now - last_sent).total_seconds() / 3600

        if horas_desde_ultimo < HORAS_ENTRE_EMAILS:
            horas_restantes = HORAS_ENTRE_EMAILS - horas_desde_ultimo
            print(f"  ⏳ {company}: faltan {horas_restantes:.1f}h para el próximo email")
            omitidos += 1
            continue

        # ── ✅ Elegible → enviar siguiente email ──────────────────────────────
        print(f"  📧 {company}: enviando Día {current_day + 1}…")
        resultado = await ejecutar_secuencia(place_id)

        # Error al enviar
        if resultado.get("error"):
            print(f"     ❌ Error: {resultado['error']}")
            errores += 1
            resultados.append({
                "place_id": place_id,
                "company":  company,
                "status":   "error",
                "error":    resultado["error"],
            })
            continue

        # Secuencia completada o pausada externamente
        if resultado.get("status") in ("completada", "detenida"):
            print(f"     ℹ️  Estado: {resultado['status']}")
            resultados.append({
                "place_id": place_id,
                "company":  company,
                "status":   resultado["status"],
            })
            continue

        # Email enviado con éxito
        dia_enviado = resultado.get("dia", current_day + 1)
        enviado_a   = resultado.get("enviado_a", "")
        print(f"     ✅ Día {dia_enviado} enviado a {enviado_a}")
        enviados += 1

        # Actualizar Google Sheet si está disponible
        if _SHEETS_OK:
            try:
                leads_data = await supabase_select("leads", {"place_id": f"eq.{place_id}"})
                if leads_data and isinstance(leads_data, list):
                    lote_id = leads_data[0].get("lote_id", "")
                    if lote_id:
                        await update_lead_in_sheet(lote_id, place_id, {
                            "P6 Estado":   f"✅ Día {dia_enviado}/5 enviado",
                            "Fecha Envío": now_str,
                            "Estado":      f"✅ Secuencia día {dia_enviado}",
                        })
            except Exception as e:
                print(f"     ⚠️  Sheet no actualizado: {e}")

        resultados.append({
            "place_id": place_id,
            "company":  company,
            "status":   "enviado",
            "dia":      dia_enviado,
            "enviado_a": enviado_a,
        })

        # Pausa breve entre envíos para no saturar Brevo rate limits
        await asyncio.sleep(1.2)

    print(f"\n{'─'*55}")
    print(f"  Procesados : {len(rows)}")
    print(f"  Enviados   : {enviados}")
    print(f"  Omitidos   : {omitidos}  (no cumplían 24h aún)")
    print(f"  Errores    : {errores}")
    print(f"{'='*55}\n")

    return {
        "procesados": len(rows),
        "enviados":   enviados,
        "omitidos":   omitidos,
        "errores":    errores,
        "resultados": resultados,
    }
