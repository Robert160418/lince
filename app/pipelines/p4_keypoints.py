import json
from typing import Any

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY
from app.utils.supabase_client import (
    supabase_select,
    supabase_update_lead,
    supabase_insert,
)


client = AsyncOpenAI(api_key=OPENAI_API_KEY)


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


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _tiene_valor(value: Any) -> bool:
    """
    Determina si un campo contiene información real.
    """

    if value is None:
        return False

    if isinstance(value, bool):
        return value

    texto = str(value).strip().lower()

    return texto not in (
        "",
        "none",
        "null",
        "n/a",
        "na",
        "false",
        "no",
        "no tiene",
    )


def _es_true(value: Any) -> bool:
    """
    Normaliza valores booleanos que pueden venir como bool,
    número o texto desde Supabase.
    """

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        return value.strip().lower() in (
            "true",
            "1",
            "yes",
            "si",
            "sí",
        )

    return False


def _rating_float(value: Any):
    """
    Convierte rating a float de forma segura.
    """

    try:
        if value is None or value == "":
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


# -------------------------------------------------------------------
# SCORING OBJETIVO LINCE 2.0
# -------------------------------------------------------------------


def calcular_score_objetivo(lead: dict) -> tuple[int, list]:
    """
    Calcula un score comercial de 0 a 100 usando únicamente
    señales verificables disponibles en Lince.

    El score mide dos cosas:

    1. Necesidad / oportunidad digital.
    2. Facilidad de contactar y trabajar comercialmente el lead.

    GPT NO participa en este cálculo.
    """

    score = 0
    razones = []

    site = lead.get("site")

    website_audit_status = str(
        lead.get("data_website_ok") or ""
    ).strip().lower()

    website_audit_ok = website_audit_status == "ok"

    website_title = lead.get("website_title")
    website_description = lead.get("website_description")

    has_gtm = _es_true(
        lead.get("website_has_gtm")
    )

    has_fb_pixel = _es_true(
        lead.get("website_has_fb_pixel")
    )

    instagram = lead.get("company_instagram")
    facebook = lead.get("company_facebook")

    phone = (
        lead.get("phone")
        or lead.get("telephone")
    )

    email = (
        lead.get("contact_email")
        or lead.get("email")
    )

    address = lead.get("full_address")

    rating = _rating_float(
        lead.get("rating")
    )

    # ---------------------------------------------------------------
    # 1. PRESENCIA WEB
    # ---------------------------------------------------------------

    if not _tiene_valor(site):

        score += 55

        razones.append({
            "senal": "sin_sitio_web",
            "puntos": 55,
            "detalle": (
                "No se detectó sitio web."
            ),
        })

    elif website_audit_ok:

        if not _tiene_valor(website_title):

            score += 6

            razones.append({
                "senal": "titulo_web_no_detectado",
                "puntos": 6,
                "detalle": (
                    "No se detectó título web útil."
                ),
            })

        if not _tiene_valor(
            website_description
        ):

            score += 6

            razones.append({
                "senal": "meta_description_no_detectada",
                "puntos": 6,
                "detalle": (
                    "No se detectó meta descripción."
                ),
            })

        if not has_gtm:

            score += 8

            razones.append({
                "senal": "gtm_no_detectado",
                "puntos": 8,
                "detalle": (
                    "Google Tag Manager no fue detectado."
                ),
            })

        if not has_fb_pixel:

            score += 8

            razones.append({
                "senal": "pixel_meta_no_detectado",
                "puntos": 8,
                "detalle": (
                    "Meta/Facebook Pixel no fue detectado."
                ),
            })

        # -----------------------------------------------------------
        # 2. REDES SOCIALES
        # -----------------------------------------------------------

        if not _tiene_valor(instagram):

            score += 10

            razones.append({
                "senal": "instagram_no_detectado",
                "puntos": 10,
                "detalle": (
                    "No se detectó Instagram "
                    "desde el sitio web."
                ),
            })

        if not _tiene_valor(facebook):

            score += 8

            razones.append({
                "senal": "facebook_no_detectado",
                "puntos": 8,
                "detalle": (
                    "No se detectó Facebook "
                    "desde el sitio web."
                ),
            })

    else:

        razones.append({
            "senal": "auditoria_web_no_concluyente",
            "puntos": 0,
            "detalle": (
                "Existe sitio web, pero la auditoría no fue "
                "concluyente; las señales web y sociales no "
                "aumentan el score."
            ),
        })

    # ---------------------------------------------------------------
    # 3. REPUTACIÓN GOOGLE
    # ---------------------------------------------------------------

    if rating is not None:

        # Tener rating disponible mejora la calidad
        # de la información para decidir.
        score += 2

        razones.append({
            "senal": "rating_disponible",
            "puntos": 2,
            "detalle": (
                f"Rating Google disponible: {rating}."
            ),
        })

        if rating < 4.0:

            score += 10

            razones.append({
                "senal": "rating_bajo",
                "puntos": 10,
                "detalle": (
                    f"Rating Google inferior a 4.0: "
                    f"{rating}."
                ),
            })

        elif rating < 4.3:

            score += 5

            razones.append({
                "senal": "rating_mejorable",
                "puntos": 5,
                "detalle": (
                    f"Rating Google mejorable: "
                    f"{rating}."
                ),
            })

    # ---------------------------------------------------------------
    # 4. CONTACTABILIDAD
    # ---------------------------------------------------------------

    if _tiene_valor(phone):

        score += 12

        razones.append({
            "senal": "telefono_disponible",
            "puntos": 12,
            "detalle": (
                "Existe teléfono para contacto comercial."
            ),
        })

    if _tiene_valor(email):

        score += 8

        razones.append({
            "senal": "email_disponible",
            "puntos": 8,
            "detalle": (
                "Existe email para contacto comercial."
            ),
        })

    if _tiene_valor(address):

        score += 3

        razones.append({
            "senal": "direccion_disponible",
            "puntos": 3,
            "detalle": (
                "Existe dirección física del negocio."
            ),
        })

    # ---------------------------------------------------------------
    # CAP 0-100
    # ---------------------------------------------------------------

    score = max(
        0,
        min(int(score), 100),
    )

    return score, razones


# -------------------------------------------------------------------
# REVIEWS REALES
# -------------------------------------------------------------------


def _es_review_mock_historica(review: dict) -> bool:
    """
    Evita utilizar posibles reviews ficticias que pudieron haber sido
    guardadas por versiones antiguas de P2.

    Se comparan los textos conocidos del antiguo sistema demo.
    """

    texto = str(
        review.get("text") or ""
    ).strip().lower()

    textos_mock = {
        (
            "excelente comida, servicio impecable y ambiente "
            "muy agradable. definitivamente volvería."
        ),
        (
            "muy buen restaurante. la comida deliciosa pero "
            "un poco caro para la porción."
        ),
        (
            "uno de los mejores lugares para comer. personal "
            "muy atento y comida de excelente calidad."
        ),
    }

    return texto in textos_mock


async def obtener_reviews_reales(
    place_id: str,
    limite: int = 10,
) -> list:
    """
    Obtiene reviews ya almacenadas en Supabase.

    Se excluyen posibles reviews demo heredadas de Lince v1.
    """

    try:

        reviews = await supabase_select(
            "reviews",
            {
                "place_id": (
                    f"eq.{place_id}"
                )
            },
        )

    except Exception as e:

        print(
            f"P4: no se pudieron leer reviews: {e}"
        )

        return []

    if not reviews:
        return []

    resultado = []

    for review in reviews:

        if not isinstance(review, dict):
            continue

        if _es_review_mock_historica(review):
            continue

        texto = (
            review.get("text")
            or review.get("review")
            or review.get("content")
            or ""
        )

        rating = (
            review.get("rating")
            or review.get("stars")
            or review.get("score")
        )

        if not texto and rating is None:
            continue

        # Evitar prompts innecesariamente grandes.
        texto = str(texto)[:700]

        resultado.append({
            "rating": rating,
            "text": texto,
        })

        if len(resultado) >= limite:
            break

    return resultado


# -------------------------------------------------------------------
# NORMALIZACIÓN DE SERVICIOS IA
# -------------------------------------------------------------------


def normalizar_servicios(
    servicios,
    lead: dict,
) -> list:
    """
    Garantiza que los servicios devueltos por la IA
    pertenezcan al catálogo real de Noboweb.
    """

    resultado = []

    if isinstance(servicios, list):

        for servicio in servicios:

            if servicio in CATALOGO_SERVICIOS:

                if servicio not in resultado:
                    resultado.append(servicio)

    # ---------------------------------------------------------------
    # Fallback mínimo determinístico
    # ---------------------------------------------------------------

    if not resultado:

        if not _tiene_valor(
            lead.get("site")
        ):

            resultado.append(
                "Página web profesional"
            )

        else:

            resultado.append(
                "SEO / Posicionamiento en Google"
            )

    return resultado[:5]


# -------------------------------------------------------------------
# P4 PRINCIPAL
# -------------------------------------------------------------------


async def generar_keypoints(
    place_id: str,
) -> dict:

    # ---------------------------------------------------------------
    # OBTENER LEAD
    # ---------------------------------------------------------------

    leads = await supabase_select(
        "leads",
        {
            "place_id": (
                f"eq.{place_id}"
            )
        },
    )

    lead = leads[0] if leads else {}

    if not lead:

        return {
            "error": (
                f"Lead {place_id} no encontrado"
            )
        }

    # ---------------------------------------------------------------
    # SCORE OBJETIVO
    # ---------------------------------------------------------------

    lead_score, score_breakdown = (
        calcular_score_objetivo(lead)
    )

    # ---------------------------------------------------------------
    # REVIEWS REALES
    # ---------------------------------------------------------------

    reviews = await obtener_reviews_reales(
        place_id,
        limite=10,
    )

    # ---------------------------------------------------------------
    # EVIDENCIA PARA IA
    # ---------------------------------------------------------------

    evidencia = {
        "negocio": {
            "nombre": lead.get("name"),
            "categoria": lead.get("category"),
            "query_origen": lead.get("query"),
            "direccion": lead.get(
                "full_address"
            ),
            "telefono_disponible":
                _tiene_valor(
                    lead.get("phone")
                ),
            "email_disponible":
                _tiene_valor(
                    lead.get("contact_email")
                    or lead.get("email")
                ),
        },

        "google_maps": {
            "rating": lead.get("rating"),
        },

        "web": {
            "sitio": lead.get("site"),
            "titulo": lead.get(
                "website_title"
            ),
            "descripcion": lead.get(
                "website_description"
            ),
            "tecnologia": lead.get(
                "website_generator"
            ),
            "gtm_detectado":
                _es_true(
                    lead.get(
                        "website_has_gtm"
                    )
                ),
            "meta_pixel_detectado":
                _es_true(
                    lead.get(
                        "website_has_fb_pixel"
                    )
                ),
        },

        "redes": {
            "instagram_detectado":
                lead.get(
                    "company_instagram"
                ),
            "facebook_detectado":
                lead.get(
                    "company_facebook"
                ),
            "tiktok_detectado":
                lead.get(
                    "company_tiktok"
                ),
            "linkedin_detectado":
                lead.get(
                    "company_linkedin"
                ),
        },

        "reviews_reales_disponibles":
            len(reviews),

        "reviews": reviews,

        "score_objetivo": lead_score,

        "score_breakdown":
            score_breakdown,
    }

    evidencia_json = json.dumps(
        evidencia,
        ensure_ascii=False,
        indent=2,
    )

    catalogo_texto = "\n".join(
        f"- {servicio}"
        for servicio
        in CATALOGO_SERVICIOS
    )

    # ---------------------------------------------------------------
    # PROMPT IA
    # ---------------------------------------------------------------

    prompt = f"""
Eres un analista comercial de Noboweb, una agencia de servicios
digitales para negocios locales.

Tu trabajo es interpretar únicamente la evidencia proporcionada.

IMPORTANTE:

- NO inventes información.
- NO inventes problemas que no estén respaldados por los datos.
- NO afirmes que el negocio no aparece en Google o buscadores porque
  este sistema todavía no mide posicionamiento SEO.
- NO afirmes que una web es lenta porque aquí no existe una medición
  de velocidad.
- NO afirmes que una tecnología web es antigua únicamente por el
  nombre del CMS.
- NO inventes reviews.
- NO inventes casos de éxito.
- Si no existen reviews reales, no hagas afirmaciones sobre lo que
  opinan los clientes.
- La ausencia de un enlace social detectado significa solamente que
  Lince no lo detectó; no asegures que la empresa no tiene esa red.
- El lead_score YA fue calculado mediante reglas objetivas.
- NO modifiques el score.
- NO generes otro lead_score.

SCORE OBJETIVO CALCULADO POR LINCE:
{lead_score}/100

EVIDENCIA REAL DISPONIBLE:

{evidencia_json}

CATÁLOGO REAL DE SERVICIOS NOBOWEB:

{catalogo_texto}

Analiza qué oportunidad comercial existe para Noboweb.

Selecciona entre 2 y 5 servicios del catálogo únicamente cuando los
datos justifiquen su recomendación.

REGLAS:

1. Si no se detectó sitio web:
   prioriza "Página web profesional".

2. Si existe sitio pero faltan elementos web verificables:
   puedes considerar "Rediseño y modernización web".

3. Si el rating es bajo o mejorable:
   puedes considerar
   "Gestión de reputación y reseñas Google".

4. Si no se detectaron redes sociales:
   puedes considerar
   "Gestión de redes sociales (Instagram, Facebook)",
   pero explica que las redes no fueron detectadas.

5. No recomiendes Google Ads o Meta Ads únicamente porque no exista
   Pixel o GTM.

6. No recomiendes servicios sin una razón respaldada por evidencia.

7. El argumento de venta debe ser útil para un primer contacto
   comercial, pero sin exageraciones ni afirmaciones falsas.

Responde SOLO JSON válido con esta estructura exacta:

{{
  "problema_principal": "principal brecha u oportunidad verificable",
  "oportunidad": "cómo Noboweb podría ayudar según la evidencia",
  "argumento_venta": "ángulo honesto y concreto para primer contacto",
  "puntos_positivos": [
    "fortaleza verificable 1",
    "fortaleza verificable 2"
  ],
  "puntos_negativos": [
    "brecha verificable 1",
    "brecha verificable 2"
  ],
  "plan_de_accion": [
    "acción 1",
    "acción 2",
    "acción 3"
  ],
  "servicios_recomendados": [
    "Nombre exacto del catálogo"
  ],
  "servicio_principal": "Nombre exacto del catálogo",
  "razon_score": "explicación del score objetivo usando el breakdown"
}}
"""

    # ---------------------------------------------------------------
    # OPENAI
    # ---------------------------------------------------------------

    try:

        response = (
            await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                response_format={
                    "type": "json_object"
                },
                temperature=0.2,
            )
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        if not content:

            raise ValueError(
                "OpenAI devolvió contenido vacío"
            )

        resultado = json.loads(content)

        if not isinstance(resultado, dict):

            raise ValueError(
                "OpenAI devolvió JSON inválido"
            )

    except Exception as e:

        print(f"P4 OpenAI error: {e}")

        return {
            "error": str(e)
        }

    # ---------------------------------------------------------------
    # SERVICIOS CONTROLADOS
    # ---------------------------------------------------------------

    servicios = normalizar_servicios(
        resultado.get(
            "servicios_recomendados"
        ),
        lead,
    )

    servicio_principal = resultado.get(
        "servicio_principal"
    )

    if servicio_principal not in servicios:

        servicio_principal = servicios[0]

    resultado[
        "servicios_recomendados"
    ] = servicios

    resultado[
        "servicio_principal"
    ] = servicio_principal

    # ---------------------------------------------------------------
    # EL SCORE SIEMPRE LO MANDA PYTHON
    # ---------------------------------------------------------------

    resultado["lead_score"] = lead_score

    resultado[
        "score_breakdown"
    ] = score_breakdown

    resultado[
        "score_version"
    ] = "lince-v2-objective-2"

    resultado[
        "reviews_reales_analizadas"
    ] = len(reviews)

    # ---------------------------------------------------------------
    # GUARDAR KEYPOINTS
    # ---------------------------------------------------------------

    await supabase_insert(
        "keypoints",
        {
            "place_id": place_id,

            "company_name":
                lead.get("name", ""),

            "keypoints_for_personalization": {
                "argumento_venta":
                    resultado.get(
                        "argumento_venta"
                    ),

                "razon_score":
                    resultado.get(
                        "razon_score"
                    ),

                "servicio_principal":
                    servicio_principal,

                "score_version":
                    "lince-v2-objective-2",

                "score_breakdown":
                    score_breakdown,
            },

            "painpoints_and_opportunities": {
                "problema_principal":
                    resultado.get(
                        "problema_principal"
                    ),

                "oportunidad":
                    resultado.get(
                        "oportunidad"
                    ),
            },

            "review_positive":
                resultado.get(
                    "puntos_positivos",
                    [],
                ),

            "review_negative":
                resultado.get(
                    "puntos_negativos",
                    [],
                ),

            "agency_action_plan":
                resultado.get(
                    "plan_de_accion",
                    [],
                ),

            "servicios_recomendados":
                servicios,

            "lead_score":
                lead_score,
        },
    )

    # ---------------------------------------------------------------
    # ACTUALIZAR LEAD
    # ---------------------------------------------------------------

    await supabase_update_lead(
        place_id,
        {
            "lead_score":
                lead_score,

            "get_keypoints":
                True,

            "keypoints_ok":
                "ok",
        },
    )

    resultado["place_id"] = place_id

    print(
        f"P4 Lince 2.0 — {lead.get('name', place_id)} "
        f"| Score objetivo: {lead_score}/100 "
        f"| Reviews reales: {len(reviews)}"
    )

    return resultado