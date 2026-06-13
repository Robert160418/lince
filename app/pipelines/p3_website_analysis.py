import re
import asyncio
import requests
from bs4 import BeautifulSoup
from app.utils.supabase_client import supabase_update_lead


def _scrape_sync(url: str) -> dict:
    if not url.startswith("http"):
        url = "https://" + url

    try:
        response = requests.get(url, timeout=15, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        html = response.text
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {"url": url, "error": str(e)}

    soup = BeautifulSoup(html, "html.parser")

    # Título y descripción
    title = soup.title.string.strip() if soup.title else ""
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content", "")

    # Generator (WordPress, Wix, etc.)
    generator = ""
    meta_gen = soup.find("meta", attrs={"name": "generator"})
    if meta_gen:
        generator = meta_gen.get("content", "")
    if not generator:
        if "wp-content" in html:
            generator = "WordPress"
        elif "wix.com" in html:
            generator = "Wix"
        elif "squarespace" in html:
            generator = "Squarespace"
        elif "shopify" in html:
            generator = "Shopify"

    # Facebook Pixel
    has_fb_pixel = "fbq(" in html or "facebook-pixel" in html or "connect.facebook.net" in html

    # Google Tag Manager
    has_gtm = "googletagmanager.com/gtm" in html or "GTM-" in html

    # Emails
    emails = list(set(re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", html)))
    emails = [e for e in emails if not e.endswith((".png", ".jpg", ".svg", ".gif", ".css", ".js"))]

    # Redes sociales
    social = {}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "instagram.com" in href and "instagram" not in social:
            social["instagram"] = href
        elif "facebook.com" in href and "facebook" not in social:
            social["facebook"] = href
        elif "tiktok.com" in href and "tiktok" not in social:
            social["tiktok"] = href
        elif "linkedin.com" in href and "linkedin" not in social:
            social["linkedin"] = href

    return {
        "url": url,
        "website_title": title[:200],
        "website_description": description[:500],
        "website_generator": generator[:100],
        "website_has_fb_pixel": has_fb_pixel,
        "website_has_gtm": has_gtm,
        "contact_email": emails[0] if emails else None,
        "company_instagram": social.get("instagram"),
        "company_facebook": social.get("facebook"),
        "company_linkedin": social.get("linkedin"),
    }


async def scrape_website(url: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _scrape_sync, url)


async def analizar_y_guardar(place_id: str, url: str):
    datos = await scrape_website(url)

    update_data = {
        "website_title": datos.get("website_title"),
        "website_description": datos.get("website_description"),
        "website_generator": datos.get("website_generator"),
        "website_has_fb_pixel": datos.get("website_has_fb_pixel", False),
        "website_has_gtm": datos.get("website_has_gtm", False),
        "company_instagram": datos.get("company_instagram"),
        "company_facebook": datos.get("company_facebook"),
        "company_linkedin": datos.get("company_linkedin"),
        "get_website_data": True,
        "data_website_ok": "ok",
    }
    # Remover nulos para no sobreescribir datos existentes
    update_data = {k: v for k, v in update_data.items() if v is not None}

    await supabase_update_lead(place_id, update_data)
    return datos
