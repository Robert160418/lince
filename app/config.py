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

# Token de acceso al panel y a la API. Sin él, todas las rutas (salvo /health)
# responden 503: Lince nunca queda abierto a internet por olvido.
# Generar con: openssl rand -hex 24
LINCE_API_TOKEN = os.getenv("LINCE_API_TOKEN", "")

# Remitente de la prospección. Recomendado: un dominio SEPARADO de noboweb.com
# (ej. hola@noboweb-mail.com) para no arriesgar la reputación del correo principal.
OUTREACH_FROM_EMAIL = os.getenv("OUTREACH_FROM_EMAIL", "roberto@noboweb.com")
OUTREACH_FROM_NAME = os.getenv("OUTREACH_FROM_NAME", "Roberto Noboa | Noboweb")

# Secuencia de correo: pocos toques y espaciados. Cada valor es el número de
# días que se espera DESPUÉS del correo anterior (el primero sale al ejecutar P6).
SECUENCIA_MAX_EMAILS = 3
SECUENCIA_DIAS_ESPERA = {2: 3, 3: 6}  # día 1 → +3 días → correo 2 → +6 días → correo 3

# Número de WhatsApp de Noboweb (para los mensajes de prospección)
NOBOWEB_WHATSAPP = os.getenv("NOBOWEB_WHATSAPP", "593984985373")

# Puente hacia portal.noboweb.com — sincroniza leads calificados (P4) al CRM
# del portal. Si quedan vacíos, la sincronización simplemente se omite
# (ver app/utils/portal_bridge.py) y Lince sigue funcionando normal.
PORTAL_WEBHOOK_URL = os.getenv("PORTAL_WEBHOOK_URL", "")
LINCE_WEBHOOK_SECRET = os.getenv("LINCE_WEBHOOK_SECRET", "")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": "Bearer " + (SUPABASE_KEY or ""),
    "Content-Type": "application/json",
}
