import httpx
import asyncio
from app.config import APIFY_API_KEY
from app.utils.supabase_client import supabase_insert

# Google Sheets es opcional — si no hay credenciales configuradas, se omite silenciosamente
try:
    from app.utils.google_sheets import append_row as _append_row
    _SHEETS_AVAILABLE = True
except Exception:
    _SHEETS_AVAILABLE = False
    async def _append_row(*args, **kwargs):
        return None

APIFY_BASE_URL = "https://api.apify.com/v2"
REVIEWS_ACTOR = "compass/crawler-google-places"

# Datos mock para demostración
MOCK_REVIEWS = [
    {
        "reviewer": "Juan García",
        "rating": 5,
        "text": "Excelente comida, servicio impecable y ambiente muy agradable. Definitivamente volvería.",
        "date": "2024-04-15"
    },
    {
        "reviewer": "María López",
        "rating": 4,
        "text": "Muy buen restaurante. La comida deliciosa pero un poco caro para la porción.",
        "date": "2024-04-10"
    },
    {
        "reviewer": "Carlos Rodríguez",
        "rating": 5,
        "text": "Uno de los mejores lugares para comer. Personal muy atento y comida de excelente calidad.",
        "date": "2024-04-08"
    }
]

async def obtener_reviews(place_id: str, max_reviews: int = 20):
    """
    Obtiene reviews de Google Maps para un negocio usando Apify.
    Si no hay API key válida, devuelve datos de ejemplo.
    """
    # Retorna mock si no hay API key válida
    key_str = str(APIFY_API_KEY).strip().lower() if APIFY_API_KEY else ""
    is_placeholder = ("tu_key" in key_str or "none" in key_str or "example" in key_str or len(key_str) < 10)
    
    if not APIFY_API_KEY or is_placeholder:
        print(f"APIFY_API_KEY inválida. Usando datos de demostración.")
        return MOCK_REVIEWS[:max_reviews]
    
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Iniciar el actor
            response = await client.post(
                f"{APIFY_BASE_URL}/acts/{REVIEWS_ACTOR}/runs",
                params={"token": APIFY_API_KEY},
                json={
                    "startUrls": [{"url": f"https://www.google.com/maps/place/?q=place_id:{place_id}"}],
                    "maxReviews": max_reviews,
                    "reviewsSort": "newest",
                    "language": "es"
                }
            )
            run_data = response.json()
            run_id = run_data.get("data", {}).get("id")

            if not run_id:
                return MOCK_REVIEWS[:max_reviews]

            # Esperar que termine
            for _ in range(30):
                await asyncio.sleep(5)
                status_response = await client.get(
                    f"{APIFY_BASE_URL}/acts/{REVIEWS_ACTOR}/runs/{run_id}",
                    params={"token": APIFY_API_KEY}
                )
                status = status_response.json().get("data", {}).get("status")
                if status == "SUCCEEDED":
                    break

            # Obtener resultados
            dataset_id = status_response.json().get("data", {}).get("defaultDatasetId")
            results_response = await client.get(
                f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
                params={"token": APIFY_API_KEY}
            )
            data = results_response.json()
            # Normalizar formatos: Apify puede devolver lista de items o dict
            if isinstance(data, dict) and data.get("items"):
                return data.get("items")
            return data
    except Exception as e:
        print(f"Error en Apify: {e}, usando datos de ejemplo")
        return MOCK_REVIEWS[:max_reviews]

async def procesar_y_guardar_reviews(place_id: str, reviews: list):
    """
    Guarda las reviews en Supabase.
    """
    guardadas = 0
    # reviews puede ser:
    # - una lista de dicts donde cada dict contiene key 'reviews' con lista interna (actor Apify antiguo)
    # - una lista directa de reviews con campos simples (mock definido en este archivo)
    items = []
    for item in reviews:
        if isinstance(item, dict) and item.get("reviews"):
            items.extend(item.get("reviews", []))
        else:
            items.append(item)

    for r in items:
        # Soportar distintas formas de campos
        author = r.get("name") or r.get("reviewer") or r.get("author")
        rating = r.get("stars") or r.get("rating") or r.get("score")
        text = r.get("text") or r.get("review") or r.get("content")
        date = r.get("publishAt") or r.get("date") or r.get("createdAt")
        likes = r.get("likesCount") or r.get("likes") or 0

        data = {
            "place_id": place_id,
            "author": author,
            "rating": rating,
            "text": text,
            "date": date,
            "likes": likes
        }

        await supabase_insert("reviews", data)
        guardadas += 1
        if _SHEETS_AVAILABLE:
            await _append_row("Reviews", [
                place_id,
                data["author"],
                data["rating"],
                data["date"],
                data["likes"],
                data["text"]
            ])
    return guardadas