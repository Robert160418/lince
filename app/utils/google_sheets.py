import json
import asyncio
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from app.config import GOOGLE_SHEET_ID, GOOGLE_SHEETS_CREDENTIALS

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_client = None


def _load_credentials():
    if not GOOGLE_SHEETS_CREDENTIALS or not GOOGLE_SHEET_ID:
        return None

    try:
        credentials_json = json.loads(GOOGLE_SHEETS_CREDENTIALS)
    except json.JSONDecodeError:
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


def _append_row_sync(sheet_name: str, row: list):
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


async def append_row(sheet_name: str, row: list):
    return await asyncio.to_thread(_append_row_sync, sheet_name, row)
