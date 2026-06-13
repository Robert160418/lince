import asyncio
import sys
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import SUPABASE_URL, SUPABASE_KEY
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(BASE_DIR / "templates" / "index.html")


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


@app.get("/debug")
async def debug():
    return {
        "supabase_url": SUPABASE_URL,
        "supabase_key_primeros_10": "configurada" if SUPABASE_KEY else None,
    }


@app.get("/test-db")
async def test_db():
    try:
        data = await supabase_select("leads")
        return {"tablas": "ok", "datos": data}
    except Exception as e:
        return {"error": str(e)}


@app.get("/lotes")
async def get_lotes():
    leads = await supabase_select("leads")
    lotes: dict = {}
    for lead in leads:
        lid = lead.get("lote_id") or "sin_lote"
        if lid not in lotes:
            lotes[lid] = {"lote_id": lid, "query": lead.get("query", ""), "count": 0, "place_ids": []}
        lotes[lid]["count"] += 1
        lotes[lid]["place_ids"].append(lead.get("place_id", ""))
    return sorted(lotes.values(), key=lambda x: x["lote_id"], reverse=True)


@app.post("/pipeline/batch")
async def ejecutar_batch(body: BatchBody):
    resultado = await process_lote(body.lote_id)
    return resultado


@app.post("/pipeline/p1")
async def ejecutar_p1(body: P1Body):
    resultados = await scrape_google_maps(query=body.query, limit=body.limit)
    resultado = await procesar_y_guardar_leads(resultados, query=body.query)
    return {
        "status": "ok",
        "encontrados": len(resultados),
        "guardados": resultado.get("guardados", 0) if isinstance(resultado, dict) else resultado,
        "lote_id": resultado.get("lote_id", "") if isinstance(resultado, dict) else "",
        "leads": resultados,
    }


@app.post("/pipeline/p2")
async def ejecutar_p2(body: P2Body):
    reviews = await obtener_reviews(place_id=body.place_id, max_reviews=body.max_reviews)
    guardadas = await procesar_y_guardar_reviews(body.place_id, reviews)
    return {"status": "ok", "place_id": body.place_id, "reviews_encontradas": len(reviews), "reviews_guardadas": guardadas}


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
