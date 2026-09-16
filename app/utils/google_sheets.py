import json
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from app.config import GOOGLE_SHEET_ID, GOOGLE_SHEETS_CREDENTIALS

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_client = None

# ── Columnas del sheet de lotes ──────────────────────────────────────────────
LOTE_HEADERS = [
    "place_id",              # A — ID interno
    "Negocio",               # B
    "Rating ⭐",             # C
    "Teléfono",              # D
    "Website",               # E
    "Dirección",             # F
    "P2 Reviews",            # G — cantidad / ✅ / ❌
    "P3 Web",                # H — ✅ / ❌ / — sin web
    "Lead Score",            # I — 0-100
    "Temperatura",           # J — 🔥 Caliente / 🟡 Tibio / ❄️ Frío
    "Problema Principal",    # K — texto IA
    "Oportunidad",           # L — texto IA
    "Servicio Principal",    # M — servicio más urgente para este lead
    "Servicios Recomendados",# N — lista de servicios separados por coma
    "Email Destino",         # O — email del contacto
    "P5 Emails",             # P — ✅ 5 / ❌
    "Email 1 — Asunto",      # Q
    "Email 2 — Asunto",      # R
    "Email 3 — Asunto",      # S
    "P6 Estado",             # T — ✅ Enviado / ❌ / — sin email
    "Fecha Envío",           # U — timestamp
    "Estado",                # V — resumen global: ✅ Completo / ⚠️ Parcial / ❌ Error / ⏳ En proceso
]
COL = {h: i + 1 for i, h in enumerate(LOTE_HEADERS)}   # nombre → índice 1-based

# Paleta de colores por temperatura
_COLORS = {
    "caliente": {"red": 1.0,  "green": 0.87, "blue": 0.84},   # rojo suave 🔥
    "tibio":    {"red": 1.0,  "green": 0.96, "blue": 0.78},   # amarillo suave 🟡
    "frio":     {"red": 0.84, "green": 0.92, "blue": 1.0},    # azul suave ❄️
    "default":  {"red": 1.0,  "green": 1.0,  "blue": 1.0},    # blanco
}
# Color de cabecera
_HEADER_BG = {"red": 0.13, "green": 0.13, "blue": 0.18}
_HEADER_FG = {"red": 1.0,  "green": 1.0,  "blue": 1.0}


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


# ── Helpers de formato ────────────────────────────────────────────────────────
def _col_letter(col_num: int) -> str:
    """Convierte número de columna a letra (1→A, 26→Z, 27→AA)."""
    result = ""
    while col_num:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result

def _last_col() -> str:
    return _col_letter(len(LOTE_HEADERS))

def _score_to_color_key(score) -> str:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "default"
    if s >= 70:
        return "caliente"
    if s >= 40:
        return "tibio"
    return "frio"


def _apply_row_color_sync(ws, row_num: int, score):
    """
    Resalta Score, Temperatura y Estado usando
    una sola petición a Google Sheets.
    """
    color_key = _score_to_color_key(score)
    bg = _COLORS[color_key]

    text_color = (
        {"red": 0.70, "green": 0.08, "blue": 0.08}
        if color_key == "caliente"
        else {"red": 0.55, "green": 0.38, "blue": 0.0}
        if color_key == "tibio"
        else {"red": 0.08, "green": 0.25, "blue": 0.62}
    )

    formatos = []

    for col_name in (
        "Lead Score",
        "Temperatura",
        "Estado",
    ):
        col = _col_letter(COL[col_name])

        formatos.append({
            "range": f"{col}{row_num}",
            "format": {
                "backgroundColor": bg,
                "textFormat": {
                    "bold": True,
                    "foregroundColor": text_color,
                },
            },
        })

    ws.batch_format(formatos)


def _format_header_sync(ws):
    """
    Diseño profesional optimizado para consumir pocas
    solicitudes de Google Sheets.
    """

    last_col = _last_col()

    formatos = [
        {
            "range": f"A2:{last_col}500",
            "format": {
                "backgroundColor": {
                    "red": 1.0,
                    "green": 1.0,
                    "blue": 1.0,
                },
                "verticalAlignment": "TOP",
                "wrapStrategy": "WRAP",
                "textFormat": {
                    "fontSize": 10,
                },
            },
        },
        {
            "range": "A1:F1",
            "format": {
                "backgroundColor": {
                    "red": 0.12,
                    "green": 0.16,
                    "blue": 0.23,
                },
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {
                        "red": 1,
                        "green": 1,
                        "blue": 1,
                    },
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
        },
        {
            "range": "G1:H1",
            "format": {
                "backgroundColor": {
                    "red": 0.15,
                    "green": 0.39,
                    "blue": 0.92,
                },
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {
                        "red": 1,
                        "green": 1,
                        "blue": 1,
                    },
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
        },
        {
            "range": "I1:N1",
            "format": {
                "backgroundColor": {
                    "red": 0.49,
                    "green": 0.23,
                    "blue": 0.93,
                },
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {
                        "red": 1,
                        "green": 1,
                        "blue": 1,
                    },
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
        },
        {
            "range": "O1:U1",
            "format": {
                "backgroundColor": {
                    "red": 0.06,
                    "green": 0.46,
                    "blue": 0.42,
                },
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {
                        "red": 1,
                        "green": 1,
                        "blue": 1,
                    },
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
        },
        {
            "range": "V1",
            "format": {
                "backgroundColor": {
                    "red": 0.08,
                    "green": 0.10,
                    "blue": 0.15,
                },
                "textFormat": {
                    "bold": True,
                    "foregroundColor": {
                        "red": 1,
                        "green": 1,
                        "blue": 1,
                    },
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
        },
        {
            "range": "B2:B500",
            "format": {
                "textFormat": {
                    "bold": True,
                },
            },
        },
        {
            "range": "C2:D500",
            "format": {
                "horizontalAlignment": "CENTER",
            },
        },
        {
            "range": "G2:J500",
            "format": {
                "horizontalAlignment": "CENTER",
            },
        },
        {
            "range": "P2:P500",
            "format": {
                "horizontalAlignment": "CENTER",
            },
        },
        {
            "range": "T2:U500",
            "format": {
                "horizontalAlignment": "CENTER",
            },
        },
    ]

    # Añadir colores existentes SIN hacer una petición por celda.
    try:
        values = ws.get_all_values()

        for row_num, row in enumerate(
            values[1:],
            start=2,
        ):
            negocio = (
                row[COL["Negocio"] - 1]
                if len(row) >= COL["Negocio"]
                else ""
            )

            if str(negocio).startswith("📊 RESUMEN"):
                formatos.append({
                    "range":
                        f"A{row_num}:{last_col}{row_num}",
                    "format": {
                        "backgroundColor": {
                            "red": 0.22,
                            "green": 0.22,
                            "blue": 0.28,
                        },
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {
                                "red": 1,
                                "green": 1,
                                "blue": 1,
                            },
                        },
                    },
                })
                continue

            score = (
                row[COL["Lead Score"] - 1]
                if len(row) >= COL["Lead Score"]
                else ""
            )

            if not str(score).strip():
                continue

            color_key = _score_to_color_key(score)
            bg = _COLORS[color_key]

            text_color = (
                {"red": 0.70, "green": 0.08, "blue": 0.08}
                if color_key == "caliente"
                else {"red": 0.55, "green": 0.38, "blue": 0.0}
                if color_key == "tibio"
                else {"red": 0.08, "green": 0.25, "blue": 0.62}
            )

            for col_name in (
                "Lead Score",
                "Temperatura",
                "Estado",
            ):
                col = _col_letter(COL[col_name])

                formatos.append({
                    "range": f"{col}{row_num}",
                    "format": {
                        "backgroundColor": bg,
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": text_color,
                        },
                    },
                })

    except Exception as exc:
        print(
            f"[Sheets] warning leyendo filas: {exc}"
        )

    # UNA escritura para todos los formatos de la pestaña.
    ws.batch_format(formatos)

    widths = [
        100, 260, 85, 140, 230, 285,
        135, 120, 90, 120, 300, 320,
        230, 330, 220, 140, 255, 255,
        255, 155, 185, 230,
    ]

    requests = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {
                        "frozenRowCount": 1,
                        "frozenColumnCount": 2,
                    },
                },
                "fields": (
                    "gridProperties.frozenRowCount,"
                    "gridProperties.frozenColumnCount"
                ),
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {
                    "pixelSize": 46,
                },
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {
                    "hiddenByUser": True,
                },
                "fields": "hiddenByUser",
            }
        },
        {
            "clearBasicFilter": {
                "sheetId": ws.id,
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "startColumnIndex": 0,
                        "endRowIndex": ws.row_count,
                        "endColumnIndex": len(LOTE_HEADERS),
                    }
                }
            }
        },
    ]

    for idx, width in enumerate(widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "COLUMNS",
                    "startIndex": idx,
                    "endIndex": idx + 1,
                },
                "properties": {
                    "pixelSize": width,
                },
                "fields": "pixelSize",
            }
        })

    # UNA segunda escritura para estructura, filtros y tamaños.
    ws.spreadsheet.batch_update(
        {"requests": requests}
    )



def _format_all_lote_sheets_sync():
    """
    Aplica el nuevo diseño a todas las pestañas que
    tengan la estructura estándar de Lince.
    """
    client = _get_client()

    if not client:
        return {
            "status": "error",
            "detail": "Google Sheets no disponible",
        }

    spreadsheet = client.open_by_key(
        GOOGLE_SHEET_ID
    )

    formateadas = []
    omitidas = []

    for ws in spreadsheet.worksheets():

        headers = ws.row_values(1)

        if not headers:
            omitidas.append(ws.title)
            continue

        if (
            "place_id" not in headers
            or "Negocio" not in headers
            or "Lead Score" not in headers
            or "Estado" not in headers
        ):
            omitidas.append(ws.title)
            continue

        _format_header_sync(ws)
        formateadas.append(ws.title)

        # Máximo aproximado: 40 escrituras/minuto.
        # Google permite más, pero dejamos margen.
        time.sleep(3)

    return {
        "status": "ok",
        "formateadas": formateadas,
        "omitidas": omitidas,
    }



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
        _format_header_sync(ws)
        return ws


def _create_lote_sheet_sync(lote_id: str):
    return _get_or_create_ws(lote_id)


def _add_lead_to_sheet_sync(lote_id: str, lead: dict):
    ws = _get_or_create_ws(lote_id)
    if not ws:
        return None
    # ── Evitar duplicados: si el place_id ya existe en col A, no agregar ──
    place_id = lead.get("place_id", "")
    if place_id:
        try:
            existing = ws.find(place_id, in_column=1)
            if existing:
                return None  # Ya existe — no duplicar fila
        except Exception:
            pass  # No encontrado → continúa y agrega
    row = [
        place_id,
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
        "",     # Servicio Principal
        "",     # Servicios Recomendados
        "",     # Email Destino
        "⏳",   # P5 Emails
        "",     # Email 1 — Asunto
        "",     # Email 2 — Asunto
        "",     # Email 3 — Asunto
        "⏳",   # P6 Estado
        "",     # Fecha Envío
        "⏳",   # Estado
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
            cells_to_update.append(
                gspread.Cell(row_num, col_num, str(value) if value is not None else "")
            )

    if cells_to_update:
        ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")

    # Si se actualiza Lead Score, pintar la fila con el color de temperatura
    if "Lead Score" in updates:
        try:
            _apply_row_color_sync(ws, row_num, updates["Lead Score"])
        except Exception as e:
            print(f"  [Sheets] color row error: {e}")

    return True


def _write_summary_row_sync(lote_id: str, stats: dict):
    """Escribe una fila de resumen al final del lote."""
    ws = _get_or_create_ws(lote_id)
    if not ws:
        return None

    total      = stats.get("total", 0)
    ok         = stats.get("ok", 0)
    calientes  = stats.get("calientes", 0)
    tibios     = stats.get("tibios", 0)
    enviados   = stats.get("enviados", 0)
    now_str    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Fila separadora vacía
    ws.append_row([""] * len(LOTE_HEADERS))

    # Fila de resumen
    summary = [""] * len(LOTE_HEADERS)
    summary[COL["Negocio"] - 1]          = f"📊 RESUMEN — {now_str}"
    summary[COL["P2 Reviews"] - 1]       = f"Total: {total} leads"
    summary[COL["Lead Score"] - 1]       = f"OK: {ok}/{total}"
    summary[COL["Temperatura"] - 1]      = f"🔥 {calientes}  🟡 {tibios}  ❄️ {total-calientes-tibios}"
    summary[COL["Email Destino"] - 1]    = f"✉️ Enviados: {enviados}"
    summary[COL["Estado"] - 1]           = "✅ Pipeline completado"

    ws.append_row(summary, value_input_option="USER_ENTERED")

    # Pintar la fila de resumen en gris oscuro
    last_row = len(ws.col_values(1))
    ws.format(f"A{last_row}:{_last_col()}{last_row}", {
        "backgroundColor": {"red": 0.22, "green": 0.22, "blue": 0.28},
        "textFormat": {
            "bold": True,
            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
        }
    })
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

async def write_summary_row(lote_id: str, stats: dict):
    return await asyncio.to_thread(_write_summary_row_sync, lote_id, stats)

async def get_sheet_url():
    return await asyncio.to_thread(_get_sheet_url_sync)

async def format_all_lote_sheets():
    return await asyncio.to_thread(
        _format_all_lote_sheets_sync
    )

# Compatibilidad legacy
async def append_row(sheet_name: str, row: list):
    def _append():
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
    return await asyncio.to_thread(_append)
