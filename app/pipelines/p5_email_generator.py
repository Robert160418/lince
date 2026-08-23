import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY
from app.utils.supabase_client import (
    supabase_select,
    supabase_insert,
    supabase_update_lead,
)


client = AsyncOpenAI(api_key=OPENAI_API_KEY)


# -------------------------------------------------------------------
# CONFIGURACIÓN
# -------------------------------------------------------------------

MAX_EMAIL_WORDS = 120
TARGET_EMAIL_WORDS = 105

FRASES_RIESGO = (
    "caso de éxito",
    "casos de éxito",
    "hemos ayudado a",
    "ayudamos a empresas como",
    "nuestros clientes aumentaron",
    "nuestros clientes han aumentado",
    "garantizamos",
    "resultado garantizado",
    "resultados garantizados",
    "duplicar tus ventas",
    "duplicar sus ventas",
    "triplicar tus ventas",
    "triplicar sus ventas",
)


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------


def _tiene_valor(value: Any) -> bool:
    """
    Comprueba si un valor contiene información útil.
    """

    if value is None:
        return False

    texto = str(value).strip().lower()

    return texto not in (
        "",
        "none",
        "null",
        "n/a",
        "na",
        "no tiene",
    )


def _email_valido(value: Any) -> bool:
    """
    Validación básica del email antes de guardarlo como destinatario.
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


def _contar_palabras(texto: str) -> int:
    """
    Cuenta palabras de un texto.
    """

    return len(
        str(texto).split()
    )


def _detectar_afirmacion_riesgosa(
    texto: str,
):
    """
    Busca algunas afirmaciones comerciales especialmente peligrosas
    que no deben aparecer sin evidencia verificable.
    """

    texto_normalizado = str(
        texto
    ).lower()

    for frase in FRASES_RIESGO:

        if frase in texto_normalizado:
            return frase

    return None


def _normalizar_servicios(
    servicios,
) -> list:
    """
    Limpia la lista de servicios recibida desde P4.
    """

    if not isinstance(servicios, list):
        return []

    resultado = []

    for servicio in servicios:

        if not servicio:
            continue

        servicio = str(
            servicio
        ).strip()

        if (
            servicio
            and servicio not in resultado
        ):
            resultado.append(
                servicio
            )

    return resultado[:5]


def _validar_secuencia(
    emails,
) -> tuple[list, str | None]:
    """
    Valida la respuesta generada por OpenAI.

    Requisitos:
    - exactamente 5 emails
    - asunto y cuerpo presentes
    - máximo 120 palabras
    - sin afirmaciones comerciales peligrosas conocidas
    """

    if not isinstance(
        emails,
        list,
    ):

        return [], (
            "OpenAI no devolvió una lista "
            "de emails válida"
        )

    if len(emails) != 5:

        return [], (
            "OpenAI no generó exactamente "
            "5 emails"
        )

    resultado = []

    for index, email in enumerate(
        emails,
        start=1,
    ):

        if not isinstance(
            email,
            dict,
        ):

            return [], (
                f"Email {index} "
                "tiene formato inválido"
            )

        asunto = (
            email.get("asunto")
            or email.get("subject")
            or ""
        )

        cuerpo = (
            email.get("cuerpo")
            or email.get("body")
            or ""
        )

        asunto = str(
            asunto
        ).strip()

        cuerpo = str(
            cuerpo
        ).strip()

        if not asunto:

            return [], (
                f"Email {index} "
                "no tiene asunto"
            )

        if not cuerpo:

            return [], (
                f"Email {index} "
                "no tiene cuerpo"
            )

        palabras = _contar_palabras(
            cuerpo
        )

        if palabras > MAX_EMAIL_WORDS:

            return [], (
                f"Email {index} tiene "
                f"{palabras} palabras; "
                f"máximo permitido "
                f"{MAX_EMAIL_WORDS}"
            )

        texto_completo = (
            f"{asunto} {cuerpo}"
        )

        frase_riesgo = (
            _detectar_afirmacion_riesgosa(
                texto_completo
            )
        )

        if frase_riesgo:

            return [], (
                f"Email {index} contiene "
                "una afirmación no permitida: "
                f"'{frase_riesgo}'"
            )

        resultado.append(
            {
                "dia": index,
                "asunto": asunto,
                "cuerpo": cuerpo,
            }
        )

    return resultado, None


def _servicios_texto(
    servicios: list,
) -> str:
    """
    Convierte servicios en texto para el prompt.
    """

    return "\n".join(
        f"- {servicio}"
        for servicio in servicios
    )


# -------------------------------------------------------------------
# P5 PRINCIPAL
# -------------------------------------------------------------------


async def generar_secuencia_emails(
    place_id: str,
) -> dict:
    """
    Genera una secuencia comercial de 5 emails basada únicamente
    en evidencia obtenida previamente por Lince.

    P5 NO envía emails.

    Solamente prepara la secuencia para posterior revisión/aprobación.
    """

    # ---------------------------------------------------------------
    # LEAD
    # ---------------------------------------------------------------

    leads = await supabase_select(
        "leads",
        {
            "place_id":
                f"eq.{place_id}"
        },
    )

    lead = (
        leads[0]
        if leads
        else {}
    )

    if not lead:

        return {
            "error":
                f"Lead {place_id} "
                "no encontrado"
        }

    # ---------------------------------------------------------------
    # KEYPOINTS DE P4
    # ---------------------------------------------------------------

    keypoints = await supabase_select(
        "keypoints",
        {
            "place_id":
                f"eq.{place_id}"
        },
    )

    kp = (
        keypoints[0]
        if keypoints
        else {}
    )

    if not kp:

        return {
            "error": (
                "P5 requiere un análisis P4 "
                "válido antes de generar emails"
            )
        }

    # ---------------------------------------------------------------
    # PROTECCIÓN CONTRA DUPLICADOS
    # ---------------------------------------------------------------

    existentes = await supabase_select(
        "emails",
        {
            "place_id":
                f"eq.{place_id}"
        },
    )

    if existentes:

        return {
            "error": (
                "Ya existe una secuencia de emails "
                f"para place_id={place_id}. "
                "P5 no generó un duplicado."
            )
        }

    # ---------------------------------------------------------------
    # DATOS DE P4
    # ---------------------------------------------------------------

    painpoints = (
        kp.get(
            "painpoints_and_opportunities",
            {},
        )
        or {}
    )

    personalization = (
        kp.get(
            "keypoints_for_personalization",
            {},
        )
        or {}
    )

    servicios = (
        _normalizar_servicios(
            kp.get(
                "servicios_recomendados",
                [],
            )
        )
    )

    if not servicios:

        return {
            "error": (
                "P5 no encontró servicios "
                "recomendados válidos de P4"
            )
        }

    servicio_principal = (
        personalization.get(
            "servicio_principal"
        )
    )

    if (
        not servicio_principal
        or servicio_principal
        not in servicios
    ):

        servicio_principal = (
            servicios[0]
        )

    problema_principal = (
        painpoints.get(
            "problema_principal"
        )
        or ""
    )

    oportunidad = (
        painpoints.get(
            "oportunidad"
        )
        or ""
    )

    argumento_venta = (
        personalization.get(
            "argumento_venta"
        )
        or ""
    )

    score_breakdown = (
        personalization.get(
            "score_breakdown",
            [],
        )
        or []
    )

    lead_score = (
        kp.get("lead_score")
        or lead.get("lead_score")
        or 0
    )

    # ---------------------------------------------------------------
    # EVIDENCIA REAL PARA REDACCIÓN
    # ---------------------------------------------------------------

    evidencia = {
        "negocio": {
            "nombre":
                lead.get("name"),

            "categoria":
                lead.get("category"),

            "sitio_web":
                lead.get("site"),

            "tecnologia_web_detectada":
                lead.get(
                    "website_generator"
                ),

            "titulo_web":
                lead.get(
                    "website_title"
                ),

            "descripcion_web":
                lead.get(
                    "website_description"
                ),

            "gtm_detectado":
                lead.get(
                    "website_has_gtm",
                    False,
                ),

            "meta_pixel_detectado":
                lead.get(
                    "website_has_fb_pixel",
                    False,
                ),

            "instagram_detectado":
                lead.get(
                    "company_instagram"
                ),

            "facebook_detectado":
                lead.get(
                    "company_facebook"
                ),

            "rating_google":
                lead.get("rating"),
        },

        "analisis_p4": {
            "problema_principal":
                problema_principal,

            "oportunidad":
                oportunidad,

            "argumento_venta":
                argumento_venta,

            "servicio_principal":
                servicio_principal,

            "servicios_recomendados":
                servicios,

            "score_interno":
                lead_score,

            "score_breakdown":
                score_breakdown,
        },
    }

    evidencia_json = json.dumps(
        evidencia,
        ensure_ascii=False,
        indent=2,
    )

    servicios_txt = (
        _servicios_texto(
            servicios
        )
    )

    # ---------------------------------------------------------------
    # PROMPT
    # ---------------------------------------------------------------

    prompt = f"""
Eres copywriter de prospección B2B para Noboweb
(https://noboweb.com), una agencia digital que trabaja con
negocios locales y profesionales.

Debes generar una secuencia de 5 emails de prospección.

La secuencia será REVISADA POR UNA PERSONA antes de ser enviada.

Tu prioridad es credibilidad, personalización y conversación.

============================================================
REGLAS CRÍTICAS
============================================================

Utiliza ÚNICAMENTE la evidencia proporcionada.

NO inventes información.

NO inventes casos de éxito.

NO afirmes que Noboweb ha trabajado con negocios similares
si esa información no está en la evidencia.

NO inventes porcentajes, estadísticas, clientes, resultados,
ventas conseguidas ni cifras.

NO prometas resultados garantizados.

NO digas que podemos duplicar, triplicar o garantizar ventas.

NO inventes urgencia, fechas límite ni escasez.

NO digas que un sitio es lento porque aquí no existe una
medición de velocidad.

NO digas que el negocio no aparece en Google porque Lince
todavía no mide posiciones SEO.

NO digas que el negocio "no tiene Instagram/Facebook" cuando
solo sabemos que Lince no detectó esos enlaces.

En esos casos utiliza expresiones como:

"no detectamos..."
"no encontramos enlazado..."
"parece haber una oportunidad para revisar..."

NO menciones al prospecto:

- lead_score
- score
- Lince
- Supabase
- inteligencia artificial
- scraping
- Google Maps scraping

NO critiques agresivamente al negocio.

El tono debe ser profesional, breve, humano y respetuoso.

No uses:

"Espero que este correo te encuentre bien"

ni otros saludos genéricos.

Cada email debe tener un máximo absoluto de
{MAX_EMAIL_WORDS} palabras.

Preferiblemente utiliza entre 60 y
{TARGET_EMAIL_WORDS} palabras.

Cada email debe tener UN solo objetivo.

Los asuntos deben ser cortos y naturales.

Firma siempre:

Roberto
Noboweb
noboweb.com

============================================================
EVIDENCIA DISPONIBLE
============================================================

{evidencia_json}

============================================================
SERVICIOS RECOMENDADOS POR P4
============================================================

Servicio principal:

{servicio_principal}

Servicios posibles:

{servicios_txt}

============================================================
ESTRUCTURA DE LA SECUENCIA
============================================================

EMAIL 1 — OBSERVACIÓN PERSONALIZADA

Usa una observación verificable.

Presenta brevemente la oportunidad.

Menciona principalmente:
"{servicio_principal}"

Termina con una pregunta sencilla.

No intentes cerrar una venta.

------------------------------------------------------------

EMAIL 2 — OPORTUNIDAD

NO uses un caso de éxito.

Explica una oportunidad concreta basada únicamente
en los datos disponibles.

Puedes explicar qué revisaría Noboweb o qué podría
mejorarse.

CTA suave:
preguntar si quieren que les compartamos una observación
o diagnóstico breve.

------------------------------------------------------------

EMAIL 3 — PROBLEMA + PREGUNTA

Haz una pregunta directa relacionada con:

"{problema_principal}"

Puedes introducir UN servicio complementario si tiene
sentido.

El objetivo es conseguir respuesta.

------------------------------------------------------------

EMAIL 4 — MINI PLAN

Resume entre 2 y 3 acciones concretas que podrían tener
sentido para el negocio.

No uses falsa urgencia.

No digas "antes de que sea tarde", "última oportunidad",
"cupos", descuentos ficticios ni fechas límite inventadas.

------------------------------------------------------------

EMAIL 5 — CIERRE RESPETUOSO

Último seguimiento.

Muy breve.

Indica que no quieres insistir.

Deja abierta la posibilidad de conversar.

Incluye noboweb.com.

No presiones.

============================================================
FORMATO
============================================================

Responde ÚNICAMENTE JSON válido:

{{
  "emails": [
    {{
      "dia": 1,
      "asunto": "asunto corto",
      "cuerpo": "texto"
    }},
    {{
      "dia": 2,
      "asunto": "asunto corto",
      "cuerpo": "texto"
    }},
    {{
      "dia": 3,
      "asunto": "asunto corto",
      "cuerpo": "texto"
    }},
    {{
      "dia": 4,
      "asunto": "asunto corto",
      "cuerpo": "texto"
    }},
    {{
      "dia": 5,
      "asunto": "asunto corto",
      "cuerpo": "texto"
    }}
  ]
}}
"""

    # ---------------------------------------------------------------
    # OPENAI + VALIDACIÓN
    # ---------------------------------------------------------------

    ultimo_error = None
    emails = []

    # Dos intentos como máximo.
    # Si el primero incumple reglas, solicitamos una corrección.
    for intento in range(2):

        try:

            if intento == 0:

                contenido_prompt = (
                    prompt
                )

            else:

                contenido_prompt = (
                    prompt
                    + "\n\n"
                    + "IMPORTANTE: La respuesta anterior "
                    + "incumplió una regla de validación: "
                    + str(ultimo_error)
                    + ". Corrígela y devuelve nuevamente "
                    + "los 5 emails completos."
                )

            response = (
                await client.chat.completions.create(
                    model="gpt-4o-mini",

                    messages=[
                        {
                            "role": "user",
                            "content":
                                contenido_prompt,
                        }
                    ],

                    response_format={
                        "type":
                            "json_object"
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

                ultimo_error = (
                    "OpenAI devolvió "
                    "contenido vacío"
                )

                continue

            resultado = json.loads(
                content
            )

            emails_brutos = (
                resultado.get(
                    "emails",
                    [],
                )
            )

            emails_validados, error = (
                _validar_secuencia(
                    emails_brutos
                )
            )

            if error:

                ultimo_error = error
                continue

            emails = emails_validados
            ultimo_error = None

            break

        except Exception as e:

            ultimo_error = str(e)

    # ---------------------------------------------------------------
    # SI FALLAN LOS DOS INTENTOS
    # ---------------------------------------------------------------

    if ultimo_error:

        print(
            f"P5 OpenAI/validación error: "
            f"{ultimo_error}"
        )

        return {
            "error": ultimo_error
        }

    if len(emails) != 5:

        return {
            "error": (
                "P5 no obtuvo una secuencia "
                "válida de 5 emails"
            )
        }

    # ---------------------------------------------------------------
    # DESTINATARIO
    # ---------------------------------------------------------------

    contacto_email = (
        lead.get(
            "contact_email"
        )
    )

    recipient_email = (
        str(contacto_email).strip()
        if _email_valido(
            contacto_email
        )
        else None
    )

    # ---------------------------------------------------------------
    # GUARDAR SECUENCIA
    # ---------------------------------------------------------------

    email_data = {
        "place_id":
            place_id,

        "company_name":
            lead.get(
                "name",
                "",
            ),

        # Nunca utilizar teléfono como email.
        # P6 exigirá un destinatario válido antes de enviar.
        "recipient_email":
            recipient_email,

        "current_email_day":
            0,
    }

    for i, email in enumerate(
        emails,
        start=1,
    ):

        email_data[
            f"email_{i}_subject"
        ] = email["asunto"]

        email_data[
            f"email_{i}_body"
        ] = email["cuerpo"]

    await supabase_insert(
        "emails",
        email_data,
    )

    # ---------------------------------------------------------------
    # ACTUALIZAR LEAD
    # ---------------------------------------------------------------

    await supabase_update_lead(
        place_id,
        {
            "craft_emails":
                True,

            "craft_emails_ok":
                "ok",
        },
    )

    print(
        f"P5 Lince 2.0 — "
        f"{lead.get('name', place_id)} "
        f"| 5 emails preparados "
        f"| envío NO ejecutado"
    )

    return {
        "emails":
            emails,

        "guardado":
            True,

        "recipient_email":
            recipient_email,

        "requiere_aprobacion":
            True,
    }