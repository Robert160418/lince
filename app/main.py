import asyncio
import sys
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import hmac

from fastapi import FastAPI, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import SUPABASE_URL, LINCE_API_TOKEN, TASK_SECRET
from app.utils.supabase_client import supabase_select
from app.pipelines.p1_google_maps import scrape_google_maps, procesar_y_guardar_leads
from app.utils.batch_processor import process_lote
from app.pipelines.p2_reviews import obtener_reviews, procesar_y_guardar_reviews
from app.pipelines.p3_website_analysis import scrape_website, analizar_y_guardar
from app.pipelines.p4_keypoints import generar_keypoints
from app.pipelines.p5_email_generator import generar_secuencia_emails
from app.pipelines.p6_email_sender import ejecutar_secuencia

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Lince API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas que no exigen token: la página del panel (pide el token en el
# navegador), sus estáticos, el chequeo de salud y la tarea del cron, que
# tiene su propio secreto (TASK_SECRET).
RUTAS_PUBLICAS = {"/", "/prospectos", "/health", "/tasks/daily-sequence"}


def _token_valido(recibido: str) -> bool:
    return bool(LINCE_API_TOKEN) and hmac.compare_digest(recibido or "", LINCE_API_TOKEN)


@app.middleware("http")
async def exigir_token(request: Request, call_next):
    ruta = request.url.path
    if request.method == "OPTIONS" or ruta in RUTAS_PUBLICAS or ruta.startswith("/static/"):
        return await call_next(request)
    if not LINCE_API_TOKEN:
        return JSONResponse({"detail": "Lince sin configurar: falta LINCE_API_TOKEN en .env"}, status_code=503)
    if not _token_valido(request.headers.get("x-lince-token", "")):
        return JSONResponse({"detail": "Token inválido o ausente"}, status_code=401)
    return await call_next(request)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "templates" / "index.html", media_type="text/html; charset=utf-8")


# ----- Modelos de entrada -----

class P1Body(BaseModel):
    query: str
    limit: int = 20

class P2Body(BaseModel):
    place_id: str
    max_reviews: int = 10

class P3Body(BaseModel):
    place_id: str
    url: str

class P4Body(BaseModel):
    place_id: str

class P5Body(BaseModel):
    place_id: str

class P6Body(BaseModel):
    place_id: str
    to_email: Optional[str] = None
    to_name: Optional[str] = None

class SequenceBody(BaseModel):
    place_id: str
    url: str
    max_reviews: int = 5

class BatchBody(BaseModel):
    lote_id: str


# ----- Endpoints generales -----

@app.get("/leads")
async def get_leads():
    data = await supabase_select("leads")
    return data


@app.get("/setup/recipient-email/{place_id}/{email}")
async def set_recipient_email(place_id: str, email: str):
    import urllib.parse, requests as req
    from app.config import SUPABASE_HEADERS
    url = f"{SUPABASE_URL}/rest/v1/emails?place_id=eq.{urllib.parse.quote(place_id)}"
    headers = {**SUPABASE_HEADERS, "Prefer": "return=minimal"}
    r = req.patch(url, json={"recipient_email": email}, headers=headers)
    return {"status": r.status_code, "place_id": place_id, "recipient_email": email}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/sheets/ping")
async def sheets_ping():
    try:
        from app.utils.google_sheets import get_sheet_url, _get_client
        client = _get_client()
        if not client:
            return {"status": "error", "detail": "No se pudo crear el cliente de Google Sheets."}
        url = await get_sheet_url()
        return {"status": "ok", "sheet_url": url}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ----- Pipelines -----

@app.get("/lotes")
async def get_lotes():
    leads = await supabase_select("leads")
    lotes: dict = {}
    for lead in leads:
        lid = lead.get("lote_id") or "sin_lote"
        if lid not in lotes:
            lotes[lid] = {
                "lote_id": lid,
                "query": lead.get("query", ""),
                "count": 0,
                "place_ids": [],
            }
        lotes[lid]["count"] += 1
        lotes[lid]["place_ids"].append(lead.get("place_id", ""))
    return sorted(lotes.values(), key=lambda x: x["lote_id"], reverse=True)


@app.post("/pipeline/batch")
async def ejecutar_batch(body: BatchBody):
    resultado = await process_lote(body.lote_id)
    return resultado


@app.post("/pipeline/p1")
async def ejecutar_p1(body: P1Body, background_tasks: BackgroundTasks):
    resultados = await scrape_google_maps(query=body.query, limit=body.limit)
    resultado = await procesar_y_guardar_leads(resultados, query=body.query)

    lote_id = resultado.get("lote_id", "") if isinstance(resultado, dict) else ""

    if lote_id:
        background_tasks.add_task(process_lote, lote_id)

    return {
        "status": "ok",
        "message": f"Lote '{lote_id}' creado. Pipeline P2-P6 corriendo en segundo plano.",
        "encontrados": len(resultados),
        "guardados": resultado.get("guardados", 0) if isinstance(resultado, dict) else resultado,
        "lote_id": lote_id,
        "sheet_url": "https://docs.google.com/spreadsheets/d/1hgNERuux2eZ1MDv-tgCDp_qva-fqf1RHF9Qu4Qysjjg/edit",
        "leads": resultados,
    }


@app.post("/pipeline/p2")
async def ejecutar_p2(body: P2Body):
    reviews = await obtener_reviews(place_id=body.place_id, max_reviews=body.max_reviews)
    guardadas = await procesar_y_guardar_reviews(body.place_id, reviews)
    return {
        "status": "ok",
        "place_id": body.place_id,
        "reviews_encontradas": len(reviews),
        "reviews_guardadas": guardadas,
    }


@app.post("/pipeline/p3")
async def ejecutar_p3(body: P3Body):
    datos = await analizar_y_guardar(place_id=body.place_id, url=body.url)
    datos["place_id"] = body.place_id
    return {"status": "ok", "resultado": datos}


@app.post("/pipeline/p4")
async def ejecutar_p4(body: P4Body):
    resultado = await generar_keypoints(body.place_id)
    if resultado.get("error"):
        return {"status": "error", "error": resultado["error"]}
    return {"status": "ok", "resultado": resultado}


@app.post("/pipeline/p5")
async def ejecutar_p5(body: P5Body):
    resultado = await generar_secuencia_emails(body.place_id)
    if resultado.get("error"):
        return {"status": "error", "error": resultado["error"]}
    emails = resultado.get("emails", [])
    return {"status": "ok", "emails_generados": len(emails), "emails": emails}


@app.post("/pipeline/p6")
async def ejecutar_p6(body: P6Body):
    if body.to_email:
        await set_recipient_email(body.place_id, body.to_email)
    resultado = await ejecutar_secuencia(body.place_id)
    if resultado.get("error"):
        return {"status": "error", "error": resultado["error"]}
    return {"status": "ok", **resultado}


@app.post("/pipeline/sequence")
async def ejecutar_secuencia_completa(body: SequenceBody):
    salida = {"status": "ok", "place_id": body.place_id}

    try:
        reviews = await obtener_reviews(place_id=body.place_id, max_reviews=body.max_reviews)
        guardadas = await procesar_y_guardar_reviews(body.place_id, reviews)
        salida["p2"] = {"status": "ok", "reviews_encontradas": len(reviews), "reviews_guardadas": guardadas}
    except Exception as e:
        salida["p2"] = {"status": "error", "error": str(e)}

    try:
        datos = await analizar_y_guardar(place_id=body.place_id, url=body.url)
        salida["p3"] = {"status": "ok", "resultado": datos}
    except Exception as e:
        salida["p3"] = {"status": "error", "error": str(e)}

    try:
        kp = await generar_keypoints(body.place_id)
        if kp.get("error"):
            salida["p4"] = {"status": "error", "error": kp["error"]}
        else:
            salida["p4"] = {"status": "ok", "resultado": kp}
    except Exception as e:
        salida["p4"] = {"status": "error", "error": str(e)}

    try:
        em = await generar_secuencia_emails(body.place_id)
        if em.get("error"):
            salida["p5"] = {"status": "error", "error": em["error"]}
        else:
            emails = em.get("emails", [])
            salida["p5"] = {"status": "ok", "emails_generados": len(emails), "emails": emails}
    except Exception as e:
        salida["p5"] = {"status": "error", "error": str(e)}

    return salida


# ── Prospección uno a uno (WhatsApp) y auditoría express ──────────────────────

async def _lote(lote_id: str) -> list:
    leads = await supabase_select("leads", {"lote_id": f"eq.{lote_id}"})
    return leads if isinstance(leads, list) else []


@app.get("/prospectos", include_in_schema=False)
async def pagina_prospectos():
    return FileResponse(BASE_DIR / "templates" / "prospectos.html", media_type="text/html; charset=utf-8")


@app.get("/api/prospectos")
async def api_prospectos(lote_id: str, limite: int = 20):
    from app.utils.prospeccion import lista_del_dia
    return lista_del_dia(await _lote(lote_id), limite=limite)


@app.get("/api/prospectos.csv")
async def api_prospectos_csv(lote_id: str, limite: int = 50):
    import csv, io
    from fastapi.responses import Response
    from app.utils.prospeccion import lista_del_dia
    filas = lista_del_dia(await _lote(lote_id), limite=limite)
    buf = io.StringIO()
    campos = ["negocio", "canal", "telefono", "hallazgo", "posicion_mapa", "calificacion", "resenas", "web", "whatsapp", "mensaje"]
    w = csv.DictWriter(buf, fieldnames=campos + ["estado"], extrasaction="ignore")
    w.writeheader()
    for f in filas:
        w.writerow({**f, "estado": ""})
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="prospectos_{lote_id}.csv"'})


@app.get("/api/prospectos/{place_id}/auditoria")
async def api_auditoria(place_id: str):
    from app.utils.prospeccion import auditoria_json
    leads = await supabase_select("leads", {"place_id": f"eq.{place_id}"})
    if not leads or not isinstance(leads, list):
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    lead = leads[0]
    lote = await _lote(lead.get("lote_id", "")) if lead.get("lote_id") else [lead]
    return auditoria_json(lead, lote)


# ── Tareas programadas ────────────────────────────────────────────────────────

@app.post("/tasks/daily-sequence")
async def tarea_secuencia_diaria(x_task_secret: str = Header(default="")):
    """
    Endpoint protegido que ejecuta la secuencia diaria de emails.
    Llamado por el cron del VPS cada manana via curl.

    Header requerido: X-Task-Secret: <valor de TASK_SECRET en .env>
    """
    if not TASK_SECRET:
        raise HTTPException(status_code=503, detail="Falta TASK_SECRET en .env")
    if not hmac.compare_digest(x_task_secret or "", TASK_SECRET):
        raise HTTPException(status_code=403, detail="Acceso no autorizado")

    from app.tasks.daily_sequence import run_daily_sequence
    resultado = await run_daily_sequence()
    return {"status": "ok", **resultado}
