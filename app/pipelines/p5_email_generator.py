import json
from openai import AsyncOpenAI
from app.config import OPENAI_API_KEY
from app.utils.supabase_client import supabase_select, supabase_insert, supabase_update_lead

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def generar_secuencia_emails(place_id: str) -> dict:
    # Obtener datos del lead y keypoints
    leads = await supabase_select("leads", {"place_id": f"eq.{place_id}"})
    keypoints = await supabase_select("keypoints", {"place_id": f"eq.{place_id}"})

    lead = leads[0] if leads else {}
    kp = keypoints[0] if keypoints else {}

    if not lead:
        return {"error": f"Lead {place_id} no encontrado"}

    # Extraer datos de keypoints (están en jsonb)
    painpoints = kp.get("painpoints_and_opportunities", {}) or {}
    kp_personalization = kp.get("keypoints_for_personalization", {}) or {}
    servicios = kp.get("servicios_recomendados", []) or []
    servicio_principal = kp_personalization.get("servicio_principal", "")

    servicios_txt = (
        "\n".join(f"  - {s}" for s in servicios)
        if servicios else "  - Marketing digital integral"
    )

    prompt = f"""
Eres un experto en cold email marketing para agencias de marketing digital en Ecuador y Latinoamérica.
La agencia se llama NoBo Web (noboweb.com) y ofrece servicios de marketing digital y desarrollo web.
Genera una secuencia de 5 emails para contactar a este negocio.

NEGOCIO: {lead.get('name', 'N/A')}
SITIO WEB: {lead.get('site', 'No tiene')}
TECNOLOGÍA WEB: {lead.get('website_generator', 'N/A')}
TIENE FB PIXEL: {lead.get('website_has_fb_pixel', False)}
INSTAGRAM: {lead.get('company_instagram', 'No tiene')}
PROBLEMA PRINCIPAL: {painpoints.get('problema_principal', 'N/A')}
OPORTUNIDAD: {painpoints.get('oportunidad', 'N/A')}
ARGUMENTO DE VENTA: {kp_personalization.get('argumento_venta', 'N/A')}
SERVICIO PRINCIPAL RECOMENDADO: {servicio_principal or 'Marketing digital'}
SERVICIOS RECOMENDADOS PARA ESTE NEGOCIO:
{servicios_txt}

Genera 5 emails en JSON. Cada email debe ser conversacional, directo, máximo 120 palabras.
NO uses saludos genéricos. Menciona el nombre del negocio específicamente.
Firma siempre como parte del equipo de NoBo Web (noboweb.com).
En los emails menciona los servicios recomendados de forma natural, empezando por el servicio principal.

Formato exacto:
{{
  "emails": [
    {{
      "dia": 1,
      "asunto": "asunto corto y directo",
      "cuerpo": "cuerpo del email"
    }},
    {{
      "dia": 2,
      "asunto": "asunto",
      "cuerpo": "cuerpo"
    }},
    {{
      "dia": 3,
      "asunto": "asunto",
      "cuerpo": "cuerpo"
    }},
    {{
      "dia": 4,
      "asunto": "asunto",
      "cuerpo": "cuerpo"
    }},
    {{
      "dia": 5,
      "asunto": "asunto",
      "cuerpo": "cuerpo"
    }}
  ]
}}

Día 1: Introducción personalizada — menciona el servicio principal y por qué lo necesitan específicamente
Día 2: Caso de éxito de negocio similar en Ecuador/LATAM usando uno de los servicios recomendados
Día 3: Pregunta directa sobre su problema específico + menciona otro servicio complementario
Día 4: Urgencia suave — lista rápida de 2-3 servicios con beneficio concreto para ellos
Día 5: Seguimiento final, cierre simple con enlace a noboweb.com
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        resultado = json.loads(response.choices[0].message.content)
        emails = resultado.get("emails", [])
    except Exception as e:
        print(f"Error OpenAI: {e}")
        return {"error": str(e)}

    if len(emails) < 5:
        return {"error": "OpenAI no generó 5 emails completos"}

    # Guardar en tabla emails con estructura correcta (una fila, columnas por día)
    email_data = {
        "place_id": place_id,
        "company_name": lead.get("name", ""),
        # Solo un email válido como destinatario; nunca el teléfono.
        # Si queda vacío, P6 lo exigirá antes de enviar.
        "recipient_email": lead.get("contact_email") or None,
        "current_email_day": 0,
    }

    for i, email in enumerate(emails[:5], start=1):
        email_data[f"email_{i}_subject"] = email.get("asunto", "")
        email_data[f"email_{i}_body"] = email.get("cuerpo", "")

    await supabase_insert("emails", email_data)

    # Actualizar estado en leads
    await supabase_update_lead(place_id, {
        "craft_emails": True,
        "craft_emails_ok": "ok",
    })

    return {"emails": emails, "guardado": True}
