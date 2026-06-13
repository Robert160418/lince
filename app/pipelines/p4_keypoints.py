import json
from openai import AsyncOpenAI
from app.config import OPENAI_API_KEY
from app.utils.supabase_client import supabase_select, supabase_update_lead, supabase_insert

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def generar_keypoints(place_id: str) -> dict:
    leads = await supabase_select("leads", {"place_id": f"eq.{place_id}"})
    lead = leads[0] if leads else {}

    if not lead:
        return {"error": f"Lead {place_id} no encontrado"}

    prompt = f"""
Analiza este negocio y genera un análisis completo de ventas para una agencia de marketing digital en Ecuador.

NEGOCIO: {lead.get('name', 'N/A')}
CATEGORÍA: {lead.get('category', 'N/A')}
RATING GOOGLE: {lead.get('rating', 'N/A')} estrellas
DIRECCIÓN: {lead.get('full_address', 'N/A')}
SITIO WEB: {lead.get('site', 'No tiene')}
TÍTULO WEB: {lead.get('website_title', 'N/A')}
DESCRIPCIÓN WEB: {lead.get('website_description', 'N/A')}
TECNOLOGÍA WEB: {lead.get('website_generator', 'N/A')}
TIENE GTM: {lead.get('website_has_gtm', False)}
TIENE FB PIXEL: {lead.get('website_has_fb_pixel', False)}
INSTAGRAM: {lead.get('company_instagram', 'No tiene')}
FACEBOOK: {lead.get('company_facebook', 'No tiene')}

Responde SOLO en JSON con este formato exacto:
{{
  "problema_principal": "problema concreto y específico de este negocio",
  "oportunidad": "servicio de marketing digital que le puedes ofrecer",
  "argumento_venta": "argumento principal para el primer email de contacto",
  "puntos_positivos": ["punto positivo 1", "punto positivo 2"],
  "puntos_negativos": ["problema 1", "problema 2"],
  "plan_de_accion": ["acción 1", "acción 2", "acción 3"],
  "lead_score": 75,
  "razon_score": "justificación del score del 1 al 100"
}}
"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        resultado = json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error OpenAI: {e}")
        return {"error": str(e)}

    # Guardar en keypoints con columnas correctas
    await supabase_insert("keypoints", {
        "place_id": place_id,
        "company_name": lead.get("name", ""),
        "keypoints_for_personalization": {
            "argumento_venta": resultado.get("argumento_venta"),
            "razon_score": resultado.get("razon_score"),
        },
        "painpoints_and_opportunities": {
            "problema_principal": resultado.get("problema_principal"),
            "oportunidad": resultado.get("oportunidad"),
        },
        "review_positive": resultado.get("puntos_positivos", []),
        "review_negative": resultado.get("puntos_negativos", []),
        "agency_action_plan": resultado.get("plan_de_accion", []),
        "lead_score": resultado.get("lead_score"),
    })

    # Actualizar lead en tabla leads
    await supabase_update_lead(place_id, {
        "lead_score": resultado.get("lead_score"),
        "get_keypoints": True,
        "keypoints_ok": "ok",
    })

    resultado["place_id"] = place_id
    return resultado
