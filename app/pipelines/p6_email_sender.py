import requests
from datetime import datetime, timezone
from app.config import BREVO_API_KEY
from app.utils.supabase_client import supabase_select, supabase_update_lead

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
FROM_EMAIL = "roberto@lince.noboweb.com"
FROM_NAME = "Roberto | Lince"


def _enviar_brevo(to_email: str, to_name: str, asunto: str, cuerpo: str) -> dict:
    response = requests.post(
        BREVO_URL,
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "sender": {"name": FROM_NAME, "email": FROM_EMAIL},
            "to": [{"email": to_email, "name": to_name}],
            "subject": asunto,
            "textContent": cuerpo
        },
        timeout=15
    )
    if response.status_code in (200, 201):
        return {"ok": True, "status": response.status_code}
    else:
        return {"ok": False, "status": response.status_code, "error": response.text}


async def ejecutar_secuencia(place_id: str) -> dict:
    # Obtener registro de emails del lead
    email_rows = await supabase_select("emails", {"place_id": f"eq.{place_id}"})

    if not email_rows:
        return {"error": f"No hay secuencia de emails para {place_id}. Ejecuta P5 primero."}

    row = email_rows[0]

    # Verificar si la secuencia está pausada o terminada
    if row.get("sequence_stopped") or row.get("replied"):
        return {"status": "detenida", "mensaje": "Secuencia pausada o el lead ya respondió"}

    current_day = row.get("current_email_day", 0)
    next_day = current_day + 1

    if next_day > 5:
        return {"status": "completada", "mensaje": "Secuencia de 5 emails completada"}

    # Obtener asunto y cuerpo del día correspondiente
    asunto = row.get(f"email_{next_day}_subject")
    cuerpo = row.get(f"email_{next_day}_body")
    to_email = row.get("recipient_email")
    to_name = row.get("company_name", "")

    if not asunto or not cuerpo:
        return {"error": f"No hay email para el día {next_day}"}

    if not to_email:
        return {"error": "No hay email del destinatario. Agrega recipient_email al registro."}

    # Enviar email via Brevo
    resultado = _enviar_brevo(to_email, to_name, asunto, cuerpo)

    if not resultado.get("ok"):
        return {"error": f"Error enviando email: {resultado.get('error')}"}

    # Actualizar estado en tabla emails
    import urllib.parse
    from app.config import SUPABASE_URL, SUPABASE_HEADERS

    now = datetime.now(timezone.utc).isoformat()
    update_data = {
        "current_email_day": next_day,
        f"sent_at_day{next_day}": now,
    }

    url = f"{SUPABASE_URL}/rest/v1/emails?place_id=eq.{urllib.parse.quote(place_id)}"
    headers = {**SUPABASE_HEADERS, "Prefer": "return=minimal"}
    requests.patch(url, json=update_data, headers=headers)

    return {
        "status": "enviado",
        "dia": next_day,
        "enviado_a": to_email,
        "asunto": asunto,
    }
