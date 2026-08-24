import asyncio
import re

import requests
from bs4 import BeautifulSoup

from app.utils.supabase_client import (
    supabase_update_lead,
)


REQUEST_TIMEOUT = 15


def _normalizar_url(url: str) -> str:
    url = (url or "").strip()

    if not url:
        return ""

    if not url.startswith(
        ("http://", "https://")
    ):
        url = "https://" + url

    return url


def _scrape_sync(url: str) -> dict:
    """
    Audita un sitio web.

    IMPORTANTE:
    Si no podemos acceder al sitio, devolvemos
    audit_ok=False.

    Nunca convertimos un error de red en:
    - sin GTM
    - sin Pixel
    - sin redes
    - sin meta description
    """

    url = _normalizar_url(url)

    if not url:
        return {
            "url": "",
            "audit_ok": False,
            "error": "URL vacía",
        }

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120 Safari/537.36"
                )
            },
        )

        # Un 404/403/500/etc. NO es una auditoría válida.
        response.raise_for_status()

        html = response.text

        if not html.strip():
            return {
                "url": response.url or url,
                "audit_ok": False,
                "error": (
                    "El sitio respondió "
                    "sin contenido HTML."
                ),
            }

    except requests.RequestException as exc:
        print(
            f"P3: error accediendo a {url}: {exc}"
        )

        return {
            "url": url,
            "audit_ok": False,
            "error": str(exc),
        }

    except Exception as exc:
        print(
            f"P3: error inesperado en {url}: {exc}"
        )

        return {
            "url": url,
            "audit_ok": False,
            "error": str(exc),
        }

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # ---------------------------------------------------------------
    # TÍTULO
    # ---------------------------------------------------------------

    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True,
        )

    # ---------------------------------------------------------------
    # META DESCRIPTION
    # ---------------------------------------------------------------

    description = ""

    meta_desc = soup.find(
        "meta",
        attrs={
            "name": re.compile(
                r"^description$",
                re.I,
            )
        },
    )

    if meta_desc:
        description = (
            meta_desc.get(
                "content",
                "",
            )
            or ""
        ).strip()

    # ---------------------------------------------------------------
    # GENERATOR / CMS
    # ---------------------------------------------------------------

    generator = ""

    meta_gen = soup.find(
        "meta",
        attrs={
            "name": re.compile(
                r"^generator$",
                re.I,
            )
        },
    )

    if meta_gen:
        generator = (
            meta_gen.get(
                "content",
                "",
            )
            or ""
        ).strip()

    html_lower = html.lower()

    if not generator:
        if "wp-content" in html_lower:
            generator = "WordPress"

        elif "wix.com" in html_lower:
            generator = "Wix"

        elif "squarespace" in html_lower:
            generator = "Squarespace"

        elif "shopify" in html_lower:
            generator = "Shopify"

    # ---------------------------------------------------------------
    # MEDICIÓN / MARKETING
    # ---------------------------------------------------------------

    has_fb_pixel = (
        "fbq(" in html
        or "facebook-pixel" in html_lower
        or "connect.facebook.net" in html_lower
    )

    has_gtm = (
        "googletagmanager.com/gtm" in html_lower
        or "gtm-" in html_lower
    )

    # ---------------------------------------------------------------
    # EMAILS
    # ---------------------------------------------------------------

    emails = list(
        set(
            re.findall(
                (
                    r"[a-zA-Z0-9_.+-]+"
                    r"@[a-zA-Z0-9-]+"
                    r"\.[a-zA-Z0-9-.]+"
                ),
                html,
            )
        )
    )

    emails = [
        email
        for email in emails
        if not email.lower().endswith(
            (
                ".png",
                ".jpg",
                ".jpeg",
                ".svg",
                ".gif",
                ".css",
                ".js",
                ".webp",
            )
        )
    ]

    emails.sort()

    # ---------------------------------------------------------------
    # REDES SOCIALES
    # ---------------------------------------------------------------

    social = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = (
            link.get("href")
            or ""
        ).strip()

        href_lower = href.lower()

        if (
            "instagram.com" in href_lower
            and "instagram" not in social
        ):
            social["instagram"] = href

        elif (
            "facebook.com" in href_lower
            and "facebook" not in social
        ):
            social["facebook"] = href

        elif (
            "tiktok.com" in href_lower
            and "tiktok" not in social
        ):
            social["tiktok"] = href

        elif (
            "linkedin.com" in href_lower
            and "linkedin" not in social
        ):
            social["linkedin"] = href

    return {
        "url":
            response.url or url,

        "audit_ok":
            True,

        "website_title":
            title[:200],

        "website_description":
            description[:500],

        "website_generator":
            generator[:100],

        "website_has_fb_pixel":
            has_fb_pixel,

        "website_has_gtm":
            has_gtm,

        "contact_email":
            emails[0]
            if emails
            else None,

        "company_instagram":
            social.get(
                "instagram"
            ),

        "company_facebook":
            social.get(
                "facebook"
            ),

        "company_tiktok":
            social.get(
                "tiktok"
            ),

        "company_linkedin":
            social.get(
                "linkedin"
            ),
    }


async def scrape_website(
    url: str,
) -> dict:
    """
    Ejecuta requests fuera del event loop.
    """

    return await asyncio.to_thread(
        _scrape_sync,
        url,
    )


async def analizar_y_guardar(
    place_id: str,
    url: str,
):
    """
    Ejecuta P3 y persiste únicamente evidencia válida.

    Si la auditoría falla:
    - marca data_website_ok = "error"
    - NO escribe False en GTM/Pixel
    - NO borra redes
    - NO borra email
    - NO inventa ausencia de señales
    """

    datos = await scrape_website(
        url
    )

    audit_ok = bool(
        datos.get(
            "audit_ok"
        )
    )

    # ---------------------------------------------------------------
    # AUDITORÍA FALLIDA
    # ---------------------------------------------------------------

    if not audit_ok:
        await supabase_update_lead(
            place_id,
            {
                "get_website_data":
                    True,

                "data_website_ok":
                    "error",
            },
        )

        return datos

    # ---------------------------------------------------------------
    # AUDITORÍA EXITOSA
    # ---------------------------------------------------------------

    update_data = {
        "website_title":
            datos.get(
                "website_title"
            ),

        "website_description":
            datos.get(
                "website_description"
            ),

        "website_generator":
            datos.get(
                "website_generator"
            ),

        # False aquí SÍ es evidencia válida porque
        # la auditoría terminó correctamente.
        "website_has_fb_pixel":
            bool(
                datos.get(
                    "website_has_fb_pixel"
                )
            ),

        "website_has_gtm":
            bool(
                datos.get(
                    "website_has_gtm"
                )
            ),

        "company_instagram":
            datos.get(
                "company_instagram"
            ),

        "company_facebook":
            datos.get(
                "company_facebook"
            ),

        "company_linkedin":
            datos.get(
                "company_linkedin"
            ),

        # Este campo ya es consumido por
        # P4, P5 y la interfaz actual.
        "contact_email":
            datos.get(
                "contact_email"
            ),

        "get_website_data":
            True,

        "data_website_ok":
            "ok",
    }

    # No escribimos None para no eliminar
    # información previamente conocida.
    #
    # Los booleanos False sí se mantienen
    # porque son resultados válidos de auditoría.
    update_data = {
        key: value
        for key, value
        in update_data.items()
        if value is not None
    }

    await supabase_update_lead(
        place_id,
        update_data,
    )

    return datos