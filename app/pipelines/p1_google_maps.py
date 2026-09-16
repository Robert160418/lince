import asyncio
import base64
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

    # 3) Ficha directa de Google Maps:
    #    reconstruir Place ID ChIJ desde
    #    !1s0xHEX1:0xHEX2
    m = re.search(
        r'!1s(0x[0-9a-fA-F]+):(0x[0-9a-fA-F]+)',
        combined,
    )

    if m:
        try:
            h1 = int(m.group(1), 16)
            h2 = int(m.group(2), 16)

            raw = (
                b"\x0a\x12\x09"
                + h1.to_bytes(8, "little")
                + b"\x11"
                + h2.to_bytes(8, "little")
            )

            return (
                base64.urlsafe_b64encode(raw)
                .decode()
                .rstrip("=")
            )

        except Exception:
            pass

    # 4) Fallback: slug URL decodificado
    #    (p.ej. "Restaurante+El+Sol" → "Restaurante El Sol")
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

        # Google Maps puede responder de dos formas:
        # 1) lista de resultados con div[role="feed"]
        # 2) ficha directa de un negocio en búsquedas exactas
        if panel.count() > 0:
            for _ in range(5):
                try:
                    panel.evaluate("el => el.scrollBy(0, 1000)")
                    page.wait_for_timeout(1500)
                except Exception:
                    break

            listings = page.query_selector_all(
                'a[href*="/maps/place/"]'
            )

        else:
            # Búsqueda exacta: Google abrió directamente
            # la ficha del negocio, sin panel de resultados.
            direct_place = (
                "/maps/place/" in page.url
                or page.query_selector("h1.DUwDvf") is not None
                or page.query_selector("h1.fontHeadlineLarge") is not None
            )

            if direct_place:
                try:
                    # La ficha puede aparecer antes de que Google
                    # termine de cambiar /maps/search/ por /maps/place/.
                    # Esperamos la URL final para poder reconstruir ChIJ.
                    try:
                        page.wait_for_url(
                            "**/maps/place/**",
                            timeout=7000,
                        )
                    except Exception:
                        page.wait_for_timeout(2500)

                    name_el = (
                        page.query_selector("h1.DUwDvf")
                        or page.query_selector("h1.fontHeadlineLarge")
                    )

                    nombre = (
                        name_el.inner_text().strip()
                        if name_el
                        else page.title().split(" - Google Maps")[0].strip()
                    )

                    href = page.url
                    rating = _extract_rating(page)

                    phone_el = page.query_selector(
                        'button[data-item-id*="phone"]'
                    )
                    phone = (
                        phone_el.get_attribute("data-item-id")
                        if phone_el
                        else None
                    )
                    if phone:
                        phone = phone.replace(
                            "phone:tel:",
                            "",
                        )

                    website_el = page.query_selector(
                        'a[data-item-id="authority"]'
                    )
                    website = (
                        website_el.get_attribute("href")
                        if website_el
                        else None
                    )

                    address_el = page.query_selector(
                        'button[data-item-id="address"]'
                    )
                    address = (
                        address_el.inner_text().strip()
                        if address_el
                        else None
                    )

                    place_id = _extract_place_id(
                        href,
                        page,
                    )

                    resultados.append({
                        "place_id": place_id,
                        "name": nombre,
                        "rating": rating,
                        "phone": phone,
                        "site": website,
                        "full_address": address,
                        "query": query,
                    })

                except Exception as e:
                    print(
                        f"Error scraping ficha directa: {e}"
                    )

                browser.close()
                return resultados[:limit]

            listings = page.query_selector_all(
                'a[href*="/maps/place/"]'
            )

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

    # La pestaña se crea únicamente cuando exista
    # al menos UN lead nuevo guardado correctamente.
    sheet_creado = False
    guardados = 0
    duplicados = 0
    errores = 0

    for negocio in resultados:
        if not negocio.get("name"):
            continue

        try:
            lead_data = {
                **negocio,
                "lote_id": lote_id,
            }

            resp = await supabase_insert(
                "leads",
                lead_data,
            )

            status = (
                resp.get("status")
                if isinstance(resp, dict)
                else None
            )

            if status in (200, 201):

                guardados += 1

                if _SHEETS_AVAILABLE:
                    try:
                        if not sheet_creado:
                            await create_lote_sheet(
                                lote_id
                            )
                            sheet_creado = True

                        await add_lead_to_sheet(
                            lote_id,
                            lead_data,
                        )

                    except Exception as e:
                        print(
                            "Google Sheets error "
                            f"para {negocio.get('name')}: {e}"
                        )

            elif status == 409:

                duplicados += 1

                print(
                    "Lead duplicado omitido: "
                    f"{negocio.get('name')} "
                    f"({negocio.get('place_id')})"
                )

            else:

                errores += 1

                print(
                    f"Error HTTP {status} guardando "
                    f"{negocio.get('name')}"
                )

        except Exception as e:

            errores += 1

            print(
                f"Error guardando "
                f"{negocio.get('name')}: {e}"
            )

    # Si no hubo ningún lead nuevo, no existe lote
    # operativo y no debe arrancar P2→P5.
    lote_operativo = (
        lote_id
        if guardados > 0
        else ""
    )

    return {
        "guardados": guardados,
        "duplicados": duplicados,
        "errores": errores,
        "lote_id": lote_operativo,
    }
