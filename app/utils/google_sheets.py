import json
import asyncio
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from app.config import GOOGLE_SHEET_ID, GOOGLE_SHEETS_CREDENTIALS

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_client = None

# ── Columnas del sheet de lotes ──────────────────────────────────────────────
LOTE_HEADERS = [
    "place_id", "Negocio", "Rating ⭐", "Teléfono", "Website", "Dirección",
    "P2 Reviews", "P3 Web", "Lead Score", "Temperatura",
    "Problema Principal", "Oportunidad", "P5 Emails",
    "Email Destino", "P6 Enviado", "Asunto Email 1"
]
COL = {h: i + 1 for i, h in enumerate(LOTE_HEADERS)}   # nombre → índice 1-based


# ── Credenciales ─────────────────────────────────────────────────────────────
def _load_credentials():
    if not GOOGLE_SHEETS_CREDENTIALS or not GOOGLE_SHEET_ID:
        return None
    try:
        credentials_json = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    except (json.JSONDecodeError, TypeError):
        try:
            path = Path(GOOGLE_SHEETS_CREDENTIALS)
            credentials_json = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return Credentials.from_service_account_info(credentials_json, scopes=SCOPES)


def _get_client():
    global _client
    if _client is not None:
        return _client
    credentials = _load_credentials()
    if not credentials:
        return None
    _client = gspread.authorize(credentials)
    return _client


# ── Helpers síncronos ─────────────────────────────────────────────────────────
def _get_or_create_ws(sheet_name: str):
    """Devuelve (o crea) una pestaña en el spreadsheet."""
    client = _get_client()
    if not client:
        return None
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=sheet_name, rows=500, cols=len(LOTE_HEADERS) + 2
        )
        ws.append_row(LOTE_HEADERS, value_input_option="USER_ENTERED")
        ws.format(f"A1:{chr(64+len(LOTE_HEADERS))}1", {"textFormat": {"bold": True}})
        return ws


def _create_lote_sheet_sync(lote_id: str):
    return _get_or_create_ws(lote_id)


def _add_lead_to_sheet_sync(lote_id: str, lead: dict):
    ws = _get_or_create_ws(lote_id)
    if not ws:
        return None
    row = [
        lead.get("place_id", ""),
        lead.get("name", ""),
        lead.get("rating", ""),
        lead.get("phone", ""),
        lead.get("site", ""),
        lead.get("full_address", ""),
        "⏳",   # P2 Reviews
        "⏳",   # P3 Web
        "",     # Lead Score
        "",     # Temperatura
        "",     # Problema Principal
        "",     # Oportunidad
        "⏳",   # P5 Emails
        "",     # Email Destino
        "⏳",   # P6 Enviado
        "",     # Asunto Email 1
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    return True


def _update_lead_in_sheet_sync(lote_id: str, place_id: str, updates: dict):
    """Actualiza columnas específicas para un lead identificado por place_id."""
    ws = _get_or_create_ws(lote_id)
    if not ws:
        return None
    try:
        cell = ws.find(place_id, in_column=1)
    except Exception:
        return None
    if not cell:
        return None

    row_num = cell.row
    cells_to_update = []
    for col_name, value in updates.items():
        col_num = COL.get(col_name)
        if col_num:
            cells_to_update.append(gspread.Cell(row_num, col_num, str(value) if value is not None else ""))

    if cells_to_update:
        ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")
    return True


def _append_row_sync(sheet_name: str, row: list):
    """Compatibilidad: agrega una fila a cualquier pestaña (usado en P2)."""
    client = _get_client()
    if not client:
        return None
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
    worksheet.append_row(row, value_input_option="USER_ENTERED")
    return True


def _get_sheet_url_sync():
    client = _get_client()
    if not client:
        return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)
        return spreadsheet.url
    except Exception:
        return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"


# ── Wrappers async ─────────────────────────────────────────────────────────────
async def create_lote_sheet(lote_id: str):
    return await asyncio.to_thread(_create_lote_sheet_sync, lote_id)

async def add_lead_to_sheet(lote_id: str, lead: dict):
    return await asyncio.to_thread(_add_lead_to_sheet_sync, lote_id, lead)

async def update_lead_in_sheet(lote_id: str, place_id: str, updates: dict):
    return await asyncio.to_thread(_update_lead_in_sheet_sync, lote_id, place_id, updates)

async def get_sheet_url():
    return await asyncio.to_thread(_get_sheet_url_sync)

async def append_row(sheet_name: str, row: list):
    return await asyncio.to_thread(_append_row_sync, sheet_name, row)
