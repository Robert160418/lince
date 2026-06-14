import asyncio
import re
from datetime import datetime
from playwright.sync_api import sync_playwright
from app.utils.supabase_client import supabase_insert

# Google Sheets es opcional — si no hay credenciales configuradas, se omite silenciosamente
try:
    from app.utils.google_sheets import create_lote_sheet, add_lead_to_sheet
    _SHEETS_AVAILABLE = True
except Exception:
    _SHEETS_AVAILABLE = False
    async def create_lote_sheet(*a, **k): return None
    async def add_lead_to_sheet(*a, **k): return None


def _make_lote_id(query: str) -> str:
    """Genera un identificador único para el lote: query_YYYYMMDD_HHMM"""
    safe = re.sub(r'[^a-zA-Z0-9À-ɏ]', '_', query.strip())[:35]
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    return f"{safe}_{ts}"


def _scrape_sync(query: str, limit: int) -> list:
    resultados = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        panel = page.locator('div[role="feed"]')
        for _ in range(5):
            panel.evaluate("el => el.scrollBy(0, 1000)")
            page.wait_for_timeout(1500)

        listings = page.query_selector_all('a[href*="/maps/place/"]')
        seen = set()

        for listing in listings[:limit]:
            try:
                nombre = listing.get_attribute("aria-label")
                href = listing.get_attribute("href")
                if not nombre or href in seen:
                    continue
                seen.add(href)

                detalle = browser.new_page()
                detalle.goto(href, wait_until="domcontentloaded", timeout=60000)
                detalle.wait_for_timeout(2000)

                rating_el = detalle.query_selector('span[aria-hidden="true"].fontDisplayLarge')
                rating_text = rating_el.inner_text() if rating_el else None
                try:
                    rating = float(rating_text.replace(",", ".")) if rating_text else None
                except Exception:
                    rating = None

                phone_el = detalle.query_selector('button[data-item-id*="phone"]')
                phone = phone_el.get_attribute("data-item-id") if phone_el else None
                if phone:
                    phone = phone.replace("phone:tel:", "")

                website_el = detalle.query_selector('a[data-item-id="authority"]')
                website = website_el.get_attribute("href") if website_el else None

                address_el = detalle.query_selector('button[data-item-id="address"]')
                address = address_el.inner_text().strip() if address_el else None

                # Extraer place_id real (ChIJ...) del href; si no aparece,
                # usar el slug del nombre como respaldo
                m = re.search(r"(ChIJ[A-Za-z0-9_-]{10,})", href)
                place_id = m.group(1) if m else href.split("/place/")[-1].split("/")[0]

                resultados.append({
                    "place_id": place_id,
                    "name": nombre,
                    "rating": rating,
                    "phone": phone,
                    "site": website,
                    "full_address": address,
                    "query": query,
                })
                detalle.close()
            except Exception as e:
                print(f"Error scraping listing: {e}")
                continue

        browser.close()
    return resultados


async def scrape_google_maps(query: str, limit: int = 20) -> list:
    loop = asyncio.get_event_loop()
    resultados = await loop.run_in_executor(None, _scrape_sync, query, limit)
    return resultados


async def procesar_y_guardar_leads(resultados: list, query: str = "") -> dict:
    """Guarda leads en Supabase y Google Sheets.
    Devuelve dict con {guardados, lote_id, sheet_url}.
    """
    lote_id = _make_lote_id(query)

    # Crear pestaña en Google Sheets para este lote
    if _SHEETS_AVAILABLE:
        try:
            await create_lote_sheet(lote_id)
        except Exception as e:
            print(f"Google Sheets create_lote_sheet error: {e}")

    guardados = 0
    for negocio in resultados:
        if negocio.get("name"):
            try:
                lead_data = {**negocio, "lote_id": lote_id}
                resp = await supabase_insert("leads", lead_data)
                if resp.get("status") in (200, 201):
                    guardados += 1
                    # Agregar fila al Sheet
                    if _SHEETS_AVAILABLE:
                        try:
                            await add_lead_to_sheet(lote_id, negocio)
                        except Exception as e:
                            print(f"Google Sheets add_lead error: {e}")
                else:
                    print(f"Error HTTP {resp.get('status')} guardando {negocio.get('name')}")
            except Exception as e:
                print(f"Error guardando {negocio.get('name')}: {e}")

    return {"guardados": guardados, "lote_id": lote_id}
