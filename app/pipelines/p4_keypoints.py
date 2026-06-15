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

    CATALOGO_SERVICIOS = [
        "Página web profesional",
        "Rediseño y modernización web",
        "SEO / Posicionamiento en Google",
        "Gestión de redes sociales (Instagram, Facebook)",
        "Google Ads (publicidad en buscadores)",
        "Meta Ads (publicidad en Facebook e Instagram)",
        "Gestión de reputación y reseñas Google",
        "Google My Business optimizado",
        "Email marketing y automatización",
        "Fotografía y video profesional",
        "Branding e identidad visual",
        "Chatbot y atención automática al cliente",
        "Portal de negocios / directorio online",
        "CRM y seguimiento de clientes",
    ]

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

CATÁLOGO DE SERVICIOS DISPONIBLES (elige los más relevantes para este negocio):
{chr(10).join(f'- {s}' for s in CATALOGO_SERVICIOS)}

Responde SOLO en JSON con este formato exacto:
{{
  "problema_principal": "problema concreto y específico de este negocio",
  "oportunidad": "cómo los servicios seleccionados resuelven su problema real",
  "argumento_venta": "argumento principal para el primer email de contacto",
  "puntos_positivos": ["punto positivo 1", "punto positivo 2"],
  "puntos_negativos": ["problema 1", "problema 2"],
  "plan_de_accion": ["acción 1", "acción 2", "acción 3"],
  "servicios_recomendados": ["Servicio A", "Servicio B", "Servicio C"],
  "servicio_principal": "el servicio MÁS urgente e impactante para este negocio específico",
  "lead_score": 75,
  "razon_score": "justificación del score del 1 al 100"
}}

REGLAS para servicios_recomendados:
- Elige entre 2 y 5 servicios del catálogo, los más relevantes para ESTE negocio específico.
- Si no tiene web → incluye "Página web profesional" como primero.
- Si tiene web antigua o sin pixel/GTM → incluye "Rediseño y modernización web".
- Si rating < 4 o tiene reviews negativas → incluye "Gestión de reputación y reseñas Google".
- Si no tiene Instagram ni Facebook → incluye "Gestión de redes sociales".
- Si no aparece en buscadores → incluye "SEO / Posicionamiento en Google".
- Solo incluye servicios que tengan sentido real para este negocio.
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
            "servicio_principal": resultado.get("servicio_principal"),
        },
        "painpoints_and_opportunities": {
            "problema_principal": resultado.get("problema_principal"),
            "oportunidad": resultado.get("oportunidad"),
        },
        "review_positive": resultado.get("puntos_positivos", []),
        "review_negative": resultado.get("puntos_negativos", []),
        "agency_action_plan": resultado.get("plan_de_accion", []),
        "servicios_recomendados": resultado.get("servicios_recomendados", []),
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
