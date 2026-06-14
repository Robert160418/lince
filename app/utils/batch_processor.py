"""
Batch processor — corre P2 → P3 → P4 → P5 en todos los leads de un lote
y actualiza el Google Sheet en tiempo real.
"""
import asyncio
from app.utils.supabase_client import supabase_select

try:
    from app.utils.google_sheets import update_lead_in_sheet, get_sheet_url
    _SHEETS_AVAILABLE = True
except Exception:
    _SHEETS_AVAILABLE = False
    async def update_lead_in_sheet(*a, **k): return None
    async def get_sheet_url(): return None

from app.pipelines.p2_reviews import obtener_reviews, procesar_y_guardar_reviews
from app.pipelines.p3_website_analysis import analizar_y_guardar
from app.pipelines.p4_keypoints import generar_keypoints
from app.pipelines.p5_email_generator import generar_secuencia_emails


async def process_lote(lote_id: str) -> dict:
    """Procesa todos los leads del lote a través de P2→P3→P4→P5.
    Actualiza el Google Sheet después de cada paso.
    Devuelve un resumen con resultados por lead.
    """
    leads = await supabase_select("leads", {"lote_id": f"eq.{lote_id}"})

    if not leads:
        return {"error": f"No se encontraron leads para el lote '{lote_id}'"}

    sheet_url = await get_sheet_url() if _SHEETS_AVAILABLE else None
    results = []

    for lead in leads:
        place_id = lead.get("place_id")
        name = lead.get("name", place_id)
        result = {"place_id": place_id, "name": name, "steps": {}}
        print(f"\n🔄 Procesando: {name} ({place_id})")

        # ── P2: Reviews ──────────────────────────────────────────────────────
        try:
            reviews = await obtener_reviews(place_id=place_id, max_reviews=10)
            await procesar_y_guardar_reviews(place_id, reviews)
            result["steps"]["p2"] = {"status": "ok", "reviews": len(reviews)}
            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(lote_id, place_id, {
                    "P2 Reviews": f"✅ {len(reviews)}"
                })
        except Exception as e:
            print(f"  P2 error: {e}")
            result["steps"]["p2"] = {"status": "error", "error": str(e)}
            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(lote_id, place_id, {"P2 Reviews": "❌"})

        # ── P3: Website ───────────────────────────────────────────────────────
        site = lead.get("site")
        if site:
            try:
                await analizar_y_guardar(place_id=place_id, url=site)
                result["steps"]["p3"] = {"status": "ok"}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {"P3 Web": "✅"})
            except Exception as e:
                print(f"  P3 error: {e}")
                result["steps"]["p3"] = {"status": "error", "error": str(e)}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {"P3 Web": "❌"})
        else:
            result["steps"]["p3"] = {"status": "skipped", "reason": "sin website"}
            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(lote_id, place_id, {"P3 Web": "— sin web"})

        # ── P4: Keypoints IA ──────────────────────────────────────────────────
        try:
            kp = await generar_keypoints(place_id)
            if kp.get("error"):
                result["steps"]["p4"] = {"status": "error", "error": kp["error"]}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "Lead Score": "❌", "Temperatura": ""
                    })
            else:
                score = kp.get("lead_score") or 0
                problema = kp.get("problema_principal", "")
                oportunidad = kp.get("oportunidad", "")
                temp = (
                    "🔥 Caliente" if score >= 70
                    else "🟡 Tibio" if score >= 40
                    else "❄️ Frío"
                )
                result["steps"]["p4"] = {"status": "ok", "score": score, "temp": temp}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "Lead Score": str(score),
                        "Temperatura": temp,
                        "Problema Principal": problema,
                        "Oportunidad": oportunidad,
                    })
        except Exception as e:
            print(f"  P4 error: {e}")
            result["steps"]["p4"] = {"status": "error", "error": str(e)}

        # ── P5: Secuencia de emails ───────────────────────────────────────────
        try:
            em = await generar_secuencia_emails(place_id)
            if em.get("error"):
                result["steps"]["p5"] = {"status": "error", "error": em["error"]}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {"P5 Emails": "❌"})
            else:
                emails = em.get("emails", [])
                asunto1 = ""
                if emails:
                    asunto1 = emails[0].get("subject") or emails[0].get("asunto") or ""
                result["steps"]["p5"] = {"status": "ok", "emails": len(emails)}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "P5 Emails": f"✅ {len(emails)}",
                        "Asunto Email 1": asunto1,
                    })
        except Exception as e:
            print(f"  P5 error: {e}")
            result["steps"]["p5"] = {"status": "error", "error": str(e)}

        results.append(result)

        # Pausa breve entre leads para no quemar rate limits de APIs
        await asyncio.sleep(1.5)

    # Resumen
    ok_count = sum(
        1 for r in results
        if all(s.get("status") in ("ok", "skipped")
               for s in r["steps"].values())
    )

    return {
        "status": "ok",
        "lote_id": lote_id,
        "total_leads": len(leads),
        "completados_ok": ok_count,
        "sheet_url": sheet_url,
        "results": results,
    }
