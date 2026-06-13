import requests
from app.config import SUPABASE_URL, SUPABASE_HEADERS


async def supabase_insert(tabla: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{tabla}"
    headers = {**SUPABASE_HEADERS, "Prefer": "return=minimal"}
    response = requests.post(url, json=data, headers=headers)
    if response.status_code not in (200, 201):
        print(f"Supabase error {response.status_code}: {response.text}")
    return {"status": response.status_code}


async def supabase_select(tabla: str, filtros: dict = None):
    url = f"{SUPABASE_URL}/rest/v1/{tabla}"
    params = filtros or {}
    response = requests.get(url, params=params, headers=SUPABASE_HEADERS)
    return response.json()


async def supabase_update(tabla: str, filtro: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{tabla}"
    response = requests.patch(url, json=data, headers=SUPABASE_HEADERS)
    return response.json() if response.text else {}


async def supabase_update_lead(place_id: str, data: dict):
    import urllib.parse
    url = f"{SUPABASE_URL}/rest/v1/leads?place_id=eq.{urllib.parse.quote(place_id)}"
    headers = {**SUPABASE_HEADERS, "Prefer": "return=minimal"}
    response = requests.patch(url, json=data, headers=headers)
    if response.status_code not in (200, 201, 204):
        print(f"Supabase update error {response.status_code}: {response.text}")
    return {"status": response.status_code}