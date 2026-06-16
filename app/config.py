import os
from pathlib import Path
from dotenv import load_dotenv

# Carga el .env desde la raiz del proyecto
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
APIFY_API_KEY = os.getenv("APIFY_API_KEY")
OUTSCRAPER_API_KEY = os.getenv("OUTSCRAPER_API_KEY")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")

if not GOOGLE_SHEETS_CREDENTIALS and GOOGLE_SHEETS_CREDENTIALS_PATH:
    try:
        GOOGLE_SHEETS_CREDENTIALS = Path(GOOGLE_SHEETS_CREDENTIALS_PATH).read_text()
    except FileNotFoundError:
        GOOGLE_SHEETS_CREDENTIALS = None

TASK_SECRET = os.getenv("TASK_SECRET", "")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": "Bearer " + (SUPABASE_KEY or ""),
    "Content-Type": "application/json",
}
