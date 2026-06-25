import asyncio
import re
import urllib.parse as _ul
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

def _extract_rating(page) -> float | None:
    """Intenta extraer el rating usando múltiples estrategias robustas."""
    # 1) Selectores CSS conocidos (Google cambia nombres de clases frecuentemente)
    for sel in ['span.fontDisplayLarge', 'div.fontDisplayLarge', 'span.MW4etd',
                'span.ceNzKf', 'span.ZkP5Je', 'div.F7nice span']:
        try:
            el = page.query_selector(sel)
            if el:
                txt = el.inner_text().strip().replace(',', '.')
                if re.match(r'^\d+\.\d+$', txt):
                    return float(txt)
        except Exception:
            continue

    # 2) Buscar en aria-label: "4.5 estrellas" / "4.5 stars"
    try:
        result = page.evaluate("""() => {
            const all = document.querySelectorAll('[aria-label]');
            for (const el of all) {
                const lbl = el.getAttribute('aria-label') || '';
                const m = lbl.match(/(\\d+[.,]\\d+)\\s*(estrellas|stars)/i);
                if (m) return m[1].replace(',', '.');
            }
            return null;
        }""")
        if result:
            return float(result)
    except Exception:
        pass

    # 3) Título de la página: "4.5 · Restaurante …"
    try:
        title = page.title()
        m = re.search(r'(\d+[.,]\d+)', title)
        if m:
            return float(m.group(1).replace(',', '.'))
    except Exception:
        pass

    return None

def _extract_place_id(href: str, detail_page) -> str:
    """Extrae el place_id ChIJ real desde la URL del detalle o el href original."""
    # 1) URL actual de la página de detalle (después de redirecciones)
    try:
        current_url = detail_page.url
    except Exception:
        current_url = ""

    combined = current_url + " " + href
    m = re.search(r'!1s(ChIJ[A-Za-z0-9_\-]{10,})', combined)
    if m:
        return m.group(1)

    # 2) ChIJ directo en el href
    m = re.search(r'(ChIJ[A-Za-z0-9_\-]{10,})', combined)
    if m:
        return m.group(1)

    # 3) Fallback: slug URL decodificado (p.ej. "Restaurante+El+Sol" → "Restaurante El Sol")
    if "/place/" in href:
        raw = href.split("/place/")[-1].split("/")[0]
        return _ul.unquote_plus(raw)

    return href

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

                # Rating — estrategia multi-selector
                rating = _extract_rating(detalle)

                # Teléfono
                phone_el = detalle.query_selector('button[data-item-id*="phone"]')
                phone = phone_el.get_attribute("data-item-id") if phone_el else None
                if phone:
                    phone = phone.replace("phone:tel:", "")

                # Sitio web
                website_el = detalle.query_selector('a[data-item-id="authority"]')
                website = website_el.get_attribute("href") if website_el else None

                # Dirección
                address_el = detalle.query_selector('button[data-item-id="address"]')
                address = address_el.inner_text().strip() if address_el else None

                # Place ID — estrategia robusta
                place_id = _extract_place_id(href, detalle)

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
