import asyncio

import httpx

from app.config import APIFY_API_KEY
from app.utils.supabase_client import supabase_insert


# Google Sheets es opcional.
# Si no hay credenciales configuradas, se omite silenciosamente.
try:
    from app.utils.google_sheets import append_row as _append_row

    _SHEETS_AVAILABLE = True
except Exception:
    _SHEETS_AVAILABLE = False

    async def _append_row(*args, **kwargs):
        return None


APIFY_BASE_URL = "https://api.apify.com/v2"
REVIEWS_ACTOR = "compass/crawler-google-places"


async def obtener_reviews(place_id: str, max_reviews: int = 20):
    """
    Obtiene reviews reales de Google Maps usando Apify.

    Si Apify no está configurado, falla o no devuelve resultados válidos,
    retorna una lista vacía.

    Nunca genera ni devuelve reviews ficticias.
    """

    # Validar API key
    key_str = str(APIFY_API_KEY).strip().lower() if APIFY_API_KEY else ""

    is_placeholder = (
        "tu_key" in key_str
        or "none" in key_str
        or "example" in key_str
        or len(key_str) < 10
    )

    if not APIFY_API_KEY or is_placeholder:
        print(
            "P2 Reviews: APIFY_API_KEY no configurada o inválida. "
            "Reviews no disponibles."
        )
        return []

    if not place_id:
        print("P2 Reviews: place_id vacío. Reviews no disponibles.")
        return []

    try:
        async with httpx.AsyncClient(timeout=120) as client:

            # ---------------------------------------------------------
            # 1. Iniciar actor de Apify
            # ---------------------------------------------------------
            response = await client.post(
                f"{APIFY_BASE_URL}/acts/{REVIEWS_ACTOR}/runs",
                params={"token": APIFY_API_KEY},
                json={
                    "startUrls": [
                        {
                            "url": (
                                "https://www.google.com/maps/place/"
                                f"?q=place_id:{place_id}"
                            )
                        }
                    ],
                    "maxReviews": max_reviews,
                    "reviewsSort": "newest",
                    "language": "es",
                },
            )

            response.raise_for_status()

            run_data = response.json()
            run_id = run_data.get("data", {}).get("id")

            if not run_id:
                print(
                    f"P2 Reviews: Apify no devolvió run_id "
                    f"para place_id={place_id}."
                )
                return []

            # ---------------------------------------------------------
            # 2. Esperar finalización del actor
            # ---------------------------------------------------------
            status_response = None
            final_status = None

            for _ in range(30):
                await asyncio.sleep(5)

                status_response = await client.get(
                    f"{APIFY_BASE_URL}/acts/{REVIEWS_ACTOR}/runs/{run_id}",
                    params={"token": APIFY_API_KEY},
                )

                status_response.raise_for_status()

                status_data = status_response.json().get("data", {})
                final_status = status_data.get("status")

                if final_status == "SUCCEEDED":
                    break

                if final_status in (
                    "FAILED",
                    "ABORTED",
                    "TIMED-OUT",
                ):
                    print(
                        f"P2 Reviews: ejecución Apify terminó "
                        f"con estado {final_status}."
                    )
                    return []

            # Si después del tiempo de espera no terminó correctamente
            if final_status != "SUCCEEDED":
                print(
                    f"P2 Reviews: Apify no terminó dentro del tiempo esperado. "
                    f"Estado={final_status}"
                )
                return []

            # ---------------------------------------------------------
            # 3. Obtener dataset generado por Apify
            # ---------------------------------------------------------
            status_data = status_response.json().get("data", {})
            dataset_id = status_data.get("defaultDatasetId")

            if not dataset_id:
                print(
                    f"P2 Reviews: Apify no devolvió dataset_id "
                    f"para place_id={place_id}."
                )
                return []

            results_response = await client.get(
                f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
                params={"token": APIFY_API_KEY},
            )

            results_response.raise_for_status()

            data = results_response.json()

            # ---------------------------------------------------------
            # 4. Normalizar respuesta
            # ---------------------------------------------------------
            if isinstance(data, list):
                return data

            if isinstance(data, dict):
                items = data.get("items")

                if isinstance(items, list):
                    return items

            print(
                f"P2 Reviews: Apify devolvió un formato inesperado "
                f"para place_id={place_id}."
            )
            return []

    except httpx.HTTPStatusError as e:
        print(
            f"P2 Reviews: error HTTP de Apify "
            f"{e.response.status_code}. Reviews no disponibles."
        )
        return []

    except httpx.RequestError as e:
        print(
            f"P2 Reviews: error de conexión con Apify: {e}. "
            "Reviews no disponibles."
        )
        return []

    except Exception as e:
        print(
            f"P2 Reviews: error inesperado: {e}. "
            "Reviews no disponibles."
        )
        return []


async def procesar_y_guardar_reviews(place_id: str, reviews: list):
    """
    Guarda en Supabase únicamente reviews reales obtenidas por P2.

    Si la lista está vacía, devuelve 0 sin generar información ficticia.
    """

    guardadas = 0

    if not reviews:
        print(
            f"P2 Reviews: no hay reviews reales para guardar "
            f"en place_id={place_id}."
        )
        return 0

    # Apify puede devolver:
    # - una lista de objetos con una clave "reviews" interna
    # - una lista directa de reviews
    items = []

    for item in reviews:
        if not isinstance(item, dict):
            continue

        nested_reviews = item.get("reviews")

        if isinstance(nested_reviews, list):
            items.extend(nested_reviews)
        else:
            items.append(item)

    # -------------------------------------------------------------
    # Guardar reviews normalizadas
    # -------------------------------------------------------------
    for review in items:

        if not isinstance(review, dict):
            continue

        author = (
            review.get("name")
            or review.get("reviewer")
            or review.get("author")
        )

        rating = (
            review.get("stars")
            or review.get("rating")
            or review.get("score")
        )

        text = (
            review.get("text")
            or review.get("review")
            or review.get("content")
        )

        date = (
            review.get("publishAt")
            or review.get("date")
            or review.get("createdAt")
        )

        likes = (
            review.get("likesCount")
            or review.get("likes")
            or 0
        )

        data = {
            "place_id": place_id,
            "author": author,
            "rating": rating,
            "text": text,
            "date": date,
            "likes": likes,
        }

        await supabase_insert("reviews", data)
        guardadas += 1

        if _SHEETS_AVAILABLE:
            await _append_row(
                "Reviews",
                [
                    place_id,
                    data["author"],
                    data["rating"],
                    data["date"],
                    data["likes"],
                    data["text"],
                ],
            )

    print(
        f"P2 Reviews: {guardadas} reviews reales guardadas "
        f"para place_id={place_id}."
    )

    return guardadas