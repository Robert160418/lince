"""
Batch processor — corre P2 → P3 → P4 → P5 → P6 en todos los leads de un lote
y actualiza el Google Sheet en tiempo real con colores, emails y estado completo.
"""
import asyncio
from datetime import datetime, timezone
from app.utils.supabase_client import supabase_select

try:
    from app.utils.google_sheets import (
        create_lote_sheet, add_lead_to_sheet,
        update_lead_in_sheet, write_summary_row, get_sheet_url
    )
    _SHEETS_AVAILABLE = True
except Exception:
    _SHEETS_AVAILABLE = False
    async def create_lote_sheet(*a, **k): return None
    async def add_lead_to_sheet(*a, **k): return None
    async def update_lead_in_sheet(*a, **k): return None
    async def write_summary_row(*a, **k): return None
    async def get_sheet_url(): return None

from app.pipelines.p2_reviews import obtener_reviews, procesar_y_guardar_reviews
from app.pipelines.p3_website_analysis import analizar_y_guardar
from app.pipelines.p4_keypoints import generar_keypoints
from app.pipelines.p5_email_generator import generar_secuencia_emails
from app.pipelines.p6_email_sender import ejecutar_secuencia


async def process_lote(lote_id: str) -> dict:
    """Procesa todos los leads del lote a través de P2→P3→P4→P5→P6.
    Actualiza el Google Sheet después de cada paso con colores y estado completo.
    Devuelve un resumen con resultados por lead.
    """
    print(f"\n{'='*60}")
    print(f"🚀 INICIANDO PIPELINE BATCH para lote: {lote_id}")
    print(f"{'='*60}")

    leads = await supabase_select("leads", {"lote_id": f"eq.{lote_id}"})

    if not leads:
        print(f"⚠️  No se encontraron leads para lote '{lote_id}'")
        return {"error": f"No se encontraron leads para el lote '{lote_id}'"}

    print(f"📋 {len(leads)} leads encontrados en el lote")

    # ── Inicializar sheet con todos los leads (una fila por lead) ──────────────
    sheet_url = None
    if _SHEETS_AVAILABLE:
        await create_lote_sheet(lote_id)
        for lead in leads:
            await add_lead_to_sheet(lote_id, lead)
        sheet_url = await get_sheet_url()
        print(f"📊 Google Sheet inicializado: {sheet_url}")
    else:
        print("⚠️  Google Sheets no disponible — solo se actualizará Supabase")

    results = []
    # Contadores para el resumen final
    stats = {
        "total": len(leads),
        "ok": 0,
        "calientes": 0,
        "tibios": 0,
        "enviados": 0,
    }

    for lead in leads:
        place_id = lead.get("place_id")
        name = lead.get("name", place_id)
        result = {"place_id": place_id, "name": name, "steps": {}}
        print(f"\n🔄 Procesando: {name} ({place_id})")

        lead_score = 0  # se actualiza en P4
        lead_ok = True  # flag para Estado final

        # ── P2: Reviews ──────────────────────────────────────────────────────
        try:
            reviews = await obtener_reviews(place_id=place_id, max_reviews=10)
            await procesar_y_guardar_reviews(place_id, reviews)
            result["steps"]["p2"] = {"status": "ok", "reviews": len(reviews)}
            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(lote_id, place_id, {
                    "P2 Reviews": f"✅ {len(reviews)} reviews",
                    "Estado": "⏳ P2 listo",
                })
        except Exception as e:
            print(f"  P2 error: {e}")
            result["steps"]["p2"] = {"status": "error", "error": str(e)}
            lead_ok = False
            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(lote_id, place_id, {
                    "P2 Reviews": "❌ Error",
                    "Estado": "⚠️ Error en P2",
                })

        # ── P3: Website ───────────────────────────────────────────────────────
        site = lead.get("site")
        if site:
            try:
                await analizar_y_guardar(place_id=place_id, url=site)
                result["steps"]["p3"] = {"status": "ok"}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "P3 Web": "✅ Analizado",
                        "Estado": "⏳ P3 listo",
                    })
            except Exception as e:
                print(f"  P3 error: {e}")
                result["steps"]["p3"] = {"status": "error", "error": str(e)}
                lead_ok = False
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "P3 Web": "❌ Error web",
                        "Estado": "⚠️ Error en P3",
                    })
        else:
            result["steps"]["p3"] = {"status": "skipped", "reason": "sin website"}
            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(lote_id, place_id, {
                    "P3 Web": "— sin web",
                })

        # ── P4: Keypoints IA ──────────────────────────────────────────────────
        try:
            kp = await generar_keypoints(place_id)
            if kp.get("error"):
                result["steps"]["p4"] = {"status": "error", "error": kp["error"]}
                lead_ok = False
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "Lead Score": "0",
                        "Temperatura": "❌ Error IA",
                        "Estado": "⚠️ Error en P4",
                    })
            else:
                lead_score = kp.get("lead_score") or 0
                problema   = kp.get("problema_principal", "")
                oportunidad = kp.get("oportunidad", "")
                temp = (
                    "🔥 Caliente" if lead_score >= 70
                    else "🟡 Tibio" if lead_score >= 40
                    else "❄️ Frío"
                )
                result["steps"]["p4"] = {
                    "status": "ok", "score": lead_score, "temp": temp
                }
                # Contadores para resumen
                if lead_score >= 70:
                    stats["calientes"] += 1
                elif lead_score >= 40:
                    stats["tibios"] += 1

                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "Lead Score":       str(lead_score),
                        "Temperatura":      temp,
                        "Problema Principal": problema,
                        "Oportunidad":      oportunidad,
                        "Estado":           "⏳ P4 listo",
                    })
                    # ← Color de la fila se aplica automáticamente en update_lead_in_sheet
                print(f"  P4 ok — Score: {lead_score} {temp}")
        except Exception as e:
            print(f"  P4 error: {e}")
            result["steps"]["p4"] = {"status": "error", "error": str(e)}
            lead_ok = False

        # ── P5: Secuencia de emails ───────────────────────────────────────────
        try:
            em = await generar_secuencia_emails(place_id)
            if em.get("error"):
                result["steps"]["p5"] = {"status": "error", "error": em["error"]}
                lead_ok = False
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "P5 Emails": "❌ Error",
                        "Estado": "⚠️ Error en P5",
                    })
            else:
                emails = em.get("emails", [])

                def _asunto(idx):
                    if idx < len(emails):
                        return emails[idx].get("subject") or emails[idx].get("asunto") or ""
                    return ""

                asunto1 = _asunto(0)
                asunto2 = _asunto(1)
                asunto3 = _asunto(2)

                result["steps"]["p5"] = {
                    "status": "ok",
                    "emails": len(emails),
                    "asuntos": [_asunto(i) for i in range(len(emails))],
                }
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "P5 Emails":       f"✅ {len(emails)} emails",
                        "Email 1 — Asunto": asunto1,
                        "Email 2 — Asunto": asunto2,
                        "Email 3 — Asunto": asunto3,
                        "Estado":           "⏳ P5 listo",
                    })
                print(f"  P5 ok — {len(emails)} emails generados")
        except Exception as e:
            print(f"  P5 error: {e}")
            result["steps"]["p5"] = {"status": "error", "error": str(e)}
            lead_ok = False

        # ── P6: Envío de email ────────────────────────────────────────────────
        try:
            p6 = await ejecutar_secuencia(place_id)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

            if p6.get("error"):
                result["steps"]["p6"] = {"status": "error", "error": p6["error"]}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "P6 Estado": "❌ " + p6["error"][:50],
                        "Estado":    "⚠️ Sin email destino" if "email" in p6["error"].lower() else "❌ Error P6",
                    })

            elif p6.get("status") in ("detenida", "completada"):
                result["steps"]["p6"] = {"status": p6["status"]}
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "P6 Estado": f"— {p6['status']}",
                        "Estado":    "✅ Completo (seq. pausada)" if p6["status"] == "detenida" else "✅ Secuencia completada",
                    })

            else:
                enviado_a = p6.get("enviado_a", "")
                asunto    = p6.get("asunto", "")
                dia       = p6.get("dia", "")
                result["steps"]["p6"] = {
                    "status": "ok", "enviado_a": enviado_a, "dia": dia
                }
                stats["enviados"] += 1
                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(lote_id, place_id, {
                        "Email Destino": enviado_a,
                        "P6 Estado":     f"✅ Enviado — Día {dia}",
                        "Fecha Envío":   now_str,
                        "Estado":        "✅ Email enviado",
                    })
                print(f"  P6 ok — Email enviado a {enviado_a} (Día {dia})")

        except Exception as e:
            print(f"  P6 error: {e}")
            result["steps"]["p6"] = {"status": "error", "error": str(e)}
            lead_ok = False
            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(lote_id, place_id, {
                    "P6 Estado": f"❌ {str(e)[:50]}",
                    "Estado":    "❌ Error P6",
                })

        # ── Estado final del lead ─────────────────────────────────────────────
        # Si terminó sin errores críticos pero no envió email, marcar como parcial
        p6_status = result["steps"].get("p6", {}).get("status", "")
        if lead_ok or p6_status in ("ok", "completada", "detenida"):
            estado_final = "✅ Completo"
            if p6_status not in ("ok",):
                estado_final = "⚠️ Sin email enviado"
        else:
            estado_final = "❌ Con errores"

        # Actualizar estado final solo si no fue ya marcado como enviado
        if p6_status == "ok":
            pass  # ya se marcó ✅ Email enviado
        elif _SHEETS_AVAILABLE:
            await update_lead_in_sheet(lote_id, place_id, {
                "Estado": estado_final,
            })

        if lead_ok:
            stats["ok"] += 1

        results.append(result)

        # Pausa breve entre leads para no saturar rate limits de APIs
        await asyncio.sleep(1.5)

    # ── Fila de resumen final ─────────────────────────────────────────────────
    if _SHEETS_AVAILABLE:
        try:
            await write_summary_row(lote_id, stats)
        except Exception as e:
            print(f"  [Sheets] summary row error: {e}")

    print(f"\n{'='*60}")
    print(f"✅ PIPELINE COMPLETADO — Lote: {lote_id}")
    print(f"   Total: {stats['total']} leads | OK: {stats['ok']} | Errores: {stats['total']-stats['ok']}")
    print(f"   🔥 Calientes: {stats['calientes']}  🟡 Tibios: {stats['tibios']}  ❄️ Fríos: {stats['total']-stats['calientes']-stats['tibios']}")
    print(f"   ✉️  Emails enviados: {stats['enviados']}")
    if sheet_url:
        print(f"   📊 Sheet: {sheet_url}")
    print(f"{'='*60}\n")

    return {
        "status":         "ok",
        "lote_id":        lote_id,
        "total_leads":    stats["total"],
        "completados_ok": stats["ok"],
        "calientes":      stats["calientes"],
        "tibios":         stats["tibios"],
        "enviados":       stats["enviados"],
        "sheet_url":      sheet_url,
        "results":        results,
    }
