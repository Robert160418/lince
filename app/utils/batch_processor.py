"""
Batch processor — procesa P2 → P3 → P4 y, únicamente para leads
calificados, genera P5.

P6 NO se ejecuta automáticamente desde el batch.
Los leads calificados quedan pendientes de aprobación humana antes
del primer contacto.

Flujo Lince 2.0 Hardening:

P2 Reviews
    ↓
P3 Website
    ↓
P4 Diagnóstico + Score
    ↓
Score < 70 → Sheets / histórico
Score >= 70 → CRM + P5
    ↓
Aprobación humana
    ↓
P6 envío (fuera del batch automático)
"""

import asyncio

from app.utils.supabase_client import supabase_select

try:
    from app.utils.google_sheets import (
        create_lote_sheet,
        add_lead_to_sheet,
        update_lead_in_sheet,
        write_summary_row,
        get_sheet_url,
    )

    _SHEETS_AVAILABLE = True

except Exception:
    _SHEETS_AVAILABLE = False

    async def create_lote_sheet(*a, **k):
        return None

    async def add_lead_to_sheet(*a, **k):
        return None

    async def update_lead_in_sheet(*a, **k):
        return None

    async def write_summary_row(*a, **k):
        return None

    async def get_sheet_url():
        return None


from app.pipelines.p2_reviews import (
    obtener_reviews,
    procesar_y_guardar_reviews,
)
from app.pipelines.p3_website_analysis import analizar_y_guardar
from app.pipelines.p4_keypoints import generar_keypoints
from app.pipelines.p5_email_generator import generar_secuencia_emails
from app.utils.portal_bridge import push_lead_to_portal


# ------------------------------------------------------------------
# CONFIGURACIÓN COMERCIAL TEMPORAL
# ------------------------------------------------------------------

# Mientras construimos el scoring objetivo de Lince 2.0,
# utilizamos la definición histórica de "lead caliente".
MIN_SCORE_CRM = 70


def normalizar_score(value) -> int:
    """
    Convierte de forma segura el score devuelto por P4 a entero.

    Evita que valores inesperados de la IA rompan el pipeline.
    """

    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return 0

    return max(0, min(score, 100))


def servicios_a_texto(servicios) -> str:
    """
    Normaliza servicios_recomendados para Sheets y logs.
    """

    if isinstance(servicios, list):
        return ", ".join(str(s) for s in servicios if s)

    if servicios:
        return str(servicios)

    return ""


async def process_lote(lote_id: str) -> dict:
    """
    Procesa todos los leads del lote.

    P2 → P3 → P4 se ejecutan para todos.

    Solamente los leads que:
      - completaron P4 correctamente
      - y tienen score >= MIN_SCORE_CRM

    pasan a:
      - CRM
      - generación de emails P5

    P6 queda explícitamente pendiente de aprobación humana.
    """

    print(f"\n{'=' * 60}")
    print(f"🚀 INICIANDO PIPELINE BATCH para lote: {lote_id}")
    print(f"{'=' * 60}")

    leads = await supabase_select(
        "leads",
        {"lote_id": f"eq.{lote_id}"},
    )

    if not leads:
        print(
            f"⚠️ No se encontraron leads para lote '{lote_id}'"
        )

        return {
            "error": (
                f"No se encontraron leads para el lote '{lote_id}'"
            )
        }

    print(f"📋 {len(leads)} leads encontrados en el lote")

    # ------------------------------------------------------------------
    # Inicializar Google Sheet
    # ------------------------------------------------------------------

    sheet_url = None

    if _SHEETS_AVAILABLE:
        await create_lote_sheet(lote_id)

        for lead in leads:
            await add_lead_to_sheet(lote_id, lead)

        sheet_url = await get_sheet_url()

        print(f"📊 Google Sheet inicializado: {sheet_url}")

    else:
        print(
            "⚠️ Google Sheets no disponible — "
            "solo se actualizará Supabase"
        )

    results = []

    stats = {
        "total": len(leads),
        "ok": 0,
        "calientes": 0,
        "tibios": 0,
        "enviados": 0,
    }

    # ------------------------------------------------------------------
    # Procesar leads
    # ------------------------------------------------------------------

    for lead in leads:

        place_id = lead.get("place_id")
        name = lead.get("name", place_id)

        result = {
            "place_id": place_id,
            "name": name,
            "steps": {},
        }

        print(f"\n🔄 Procesando: {name} ({place_id})")

        lead_score = 0

        lead_ok = True
        p4_ok = False
        p5_ok = False
        califica_comercialmente = False

        # ==============================================================
        # P2 — REVIEWS
        # ==============================================================

        try:
            reviews = await obtener_reviews(
                place_id=place_id,
                max_reviews=10,
            )

            await procesar_y_guardar_reviews(
                place_id,
                reviews,
            )

            result["steps"]["p2"] = {
                "status": "ok",
                "reviews": len(reviews),
            }

            if _SHEETS_AVAILABLE:

                p2_text = (
                    f"✅ {len(reviews)} reviews"
                    if reviews
                    else "— Sin reviews disponibles"
                )

                await update_lead_in_sheet(
                    lote_id,
                    place_id,
                    {
                        "P2 Reviews": p2_text,
                        "Estado": "⏳ P2 listo",
                    },
                )

        except Exception as e:

            print(f"  P2 error: {e}")

            result["steps"]["p2"] = {
                "status": "error",
                "error": str(e),
            }

            lead_ok = False

            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(
                    lote_id,
                    place_id,
                    {
                        "P2 Reviews": "❌ Error",
                        "Estado": "⚠️ Error en P2",
                    },
                )

        # ==============================================================
        # P3 — WEBSITE
        # ==============================================================

        site = lead.get("site")

        if site:

            try:
                await analizar_y_guardar(
                    place_id=place_id,
                    url=site,
                )

                result["steps"]["p3"] = {
                    "status": "ok"
                }

                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(
                        lote_id,
                        place_id,
                        {
                            "P3 Web": "✅ Analizado",
                            "Estado": "⏳ P3 listo",
                        },
                    )

            except Exception as e:

                print(f"  P3 error: {e}")

                result["steps"]["p3"] = {
                    "status": "error",
                    "error": str(e),
                }

                lead_ok = False

                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(
                        lote_id,
                        place_id,
                        {
                            "P3 Web": "❌ Error web",
                            "Estado": "⚠️ Error en P3",
                        },
                    )

        else:

            result["steps"]["p3"] = {
                "status": "skipped",
                "reason": "sin website",
            }

            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(
                    lote_id,
                    place_id,
                    {
                        "P3 Web": "— sin web",
                    },
                )

        # ==============================================================
        # P4 — DIAGNÓSTICO + SCORE
        # ==============================================================

        kp = None

        try:

            kp = await generar_keypoints(place_id)

            if not isinstance(kp, dict):

                raise ValueError(
                    "P4 devolvió una respuesta inválida"
                )

            if kp.get("error"):

                result["steps"]["p4"] = {
                    "status": "error",
                    "error": kp["error"],
                }

                lead_ok = False

                if _SHEETS_AVAILABLE:
                    await update_lead_in_sheet(
                        lote_id,
                        place_id,
                        {
                            "Lead Score": "0",
                            "Temperatura": "❌ Error IA",
                            "Estado": "⚠️ Error en P4",
                        },
                    )

            else:

                p4_ok = True

                lead_score = normalizar_score(
                    kp.get("lead_score")
                )

                problema = kp.get(
                    "problema_principal",
                    "",
                )

                oportunidad = kp.get(
                    "oportunidad",
                    "",
                )

                servicios = (
                    kp.get("servicios_recomendados", [])
                    or []
                )

                servicio_principal = kp.get(
                    "servicio_principal",
                    "",
                )

                servicios_str = servicios_a_texto(
                    servicios
                )

                # ------------------------------------------------------
                # Temperatura
                # ------------------------------------------------------

                if lead_score >= 70:
                    temp = "🔥 Caliente"
                    stats["calientes"] += 1

                elif lead_score >= 40:
                    temp = "🟡 Tibio"
                    stats["tibios"] += 1

                else:
                    temp = "❄️ Frío"

                # ------------------------------------------------------
                # Gate comercial
                # ------------------------------------------------------

                califica_comercialmente = (
                    lead_score >= MIN_SCORE_CRM
                )

                result["steps"]["p4"] = {
                    "status": "ok",
                    "score": lead_score,
                    "temp": temp,
                    "servicios": servicios,
                    "califica": califica_comercialmente,
                }

                if _SHEETS_AVAILABLE:

                    estado_p4 = (
                        "🎯 Candidato comercial"
                        if califica_comercialmente
                        else "📦 Analizado — no califica"
                    )

                    await update_lead_in_sheet(
                        lote_id,
                        place_id,
                        {
                            "Lead Score": str(lead_score),
                            "Temperatura": temp,
                            "Problema Principal": problema,
                            "Oportunidad": oportunidad,
                            "Servicio Principal":
                                servicio_principal,
                            "Servicios Recomendados":
                                servicios_str,
                            "Estado": estado_p4,
                        },
                    )

                print(
                    f"  P4 ok — Score: {lead_score} "
                    f"{temp} | Servicios: {servicios_str}"
                )

        except Exception as e:

            print(f"  P4 error: {e}")

            result["steps"]["p4"] = {
                "status": "error",
                "error": str(e),
            }

            lead_ok = False
            p4_ok = False
            califica_comercialmente = False

            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(
                    lote_id,
                    place_id,
                    {
                        "Lead Score": "0",
                        "Temperatura": "❌ Error P4",
                        "Estado": "⚠️ Error en P4",
                    },
                )

        # ==============================================================
        # CRM — SOLO LEADS CALIFICADOS
        # ==============================================================

        if p4_ok and califica_comercialmente:

            try:

                await push_lead_to_portal(
                    lead,
                    kp,
                )

                result["steps"]["crm"] = {
                    "status": "ok"
                }

                print(
                    f"  CRM ok — {name} enviado "
                    f"como candidato comercial"
                )

            except Exception as e:

                # El CRM no debe convertir un P4 correcto en error.
                print(
                    f"  CRM warning: no se pudo sincronizar: {e}"
                )

                result["steps"]["crm"] = {
                    "status": "error",
                    "error": str(e),
                }

        else:

            reason = (
                "P4 no completado"
                if not p4_ok
                else (
                    f"score {lead_score} menor a "
                    f"{MIN_SCORE_CRM}"
                )
            )

            result["steps"]["crm"] = {
                "status": "skipped",
                "reason": reason,
            }

        # ==============================================================
        # P5 — EMAILS
        # SOLO PARA LEADS CALIFICADOS
        # ==============================================================

        if not p4_ok:

            result["steps"]["p5"] = {
                "status": "skipped",
                "reason": "P4 no completado",
            }

            print(
                "  P5 omitido — P4 no fue completado"
            )

        elif not califica_comercialmente:

            result["steps"]["p5"] = {
                "status": "skipped",
                "reason": (
                    f"score {lead_score} menor a "
                    f"{MIN_SCORE_CRM}"
                ),
            }

            print(
                f"  P5 omitido — Score {lead_score} "
                f"no supera el gate comercial"
            )

            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(
                    lote_id,
                    place_id,
                    {
                        "P5 Emails": "— No generado",
                        "P6 Estado": "— No aplica",
                        "Estado":
                            "📦 Analizado — no califica",
                    },
                )

        else:

            try:

                em = await generar_secuencia_emails(
                    place_id
                )

                if em.get("error"):

                    result["steps"]["p5"] = {
                        "status": "error",
                        "error": em["error"],
                    }

                    lead_ok = False

                    if _SHEETS_AVAILABLE:
                        await update_lead_in_sheet(
                            lote_id,
                            place_id,
                            {
                                "P5 Emails": "❌ Error",
                                "Estado": "⚠️ Error en P5",
                            },
                        )

                else:

                    emails = em.get("emails", [])

                    def _asunto(idx):
                        if idx < len(emails):

                            email = emails[idx]

                            if isinstance(email, dict):
                                return (
                                    email.get("subject")
                                    or email.get("asunto")
                                    or ""
                                )

                        return ""

                    asunto1 = _asunto(0)
                    asunto2 = _asunto(1)
                    asunto3 = _asunto(2)

                    p5_ok = True

                    result["steps"]["p5"] = {
                        "status": "ok",
                        "emails": len(emails),
                        "asuntos": [
                            _asunto(i)
                            for i in range(len(emails))
                        ],
                    }

                    if _SHEETS_AVAILABLE:
                        await update_lead_in_sheet(
                            lote_id,
                            place_id,
                            {
                                "P5 Emails":
                                    f"✅ {len(emails)} emails",
                                "Email 1 — Asunto":
                                    asunto1,
                                "Email 2 — Asunto":
                                    asunto2,
                                "Email 3 — Asunto":
                                    asunto3,
                                "Estado":
                                    "👀 Pendiente aprobación",
                            },
                        )

                    print(
                        f"  P5 ok — {len(emails)} "
                        f"emails generados"
                    )

            except Exception as e:

                print(f"  P5 error: {e}")

                result["steps"]["p5"] = {
                    "status": "error",
                    "error": str(e),
                }

                lead_ok = False

        # ==============================================================
        # P6 — BLOQUEADO EN BATCH
        # ==============================================================

        if p4_ok and califica_comercialmente and p5_ok:

            result["steps"]["p6"] = {
                "status": "pending_approval",
                "reason": (
                    "requiere aprobación humana "
                    "antes del primer contacto"
                ),
            }

            if _SHEETS_AVAILABLE:
                await update_lead_in_sheet(
                    lote_id,
                    place_id,
                    {
                        "P6 Estado":
                            "⏸️ Pendiente aprobación",
                        "Estado":
                            "👀 Pendiente aprobación",
                    },
                )

            print(
                "  P6 BLOQUEADO — requiere "
                "aprobación humana"
            )

        elif not califica_comercialmente:

            result["steps"]["p6"] = {
                "status": "skipped",
                "reason": "lead no calificado",
            }

        else:

            result["steps"]["p6"] = {
                "status": "skipped",
                "reason": "P5 no completado",
            }

        # ==============================================================
        # ESTADO FINAL
        # ==============================================================

        if not lead_ok:

            estado_final = "❌ Con errores"

        elif not p4_ok:

            estado_final = "❌ P4 no completado"

        elif not califica_comercialmente:

            estado_final = "📦 Analizado — no califica"

        elif p5_ok:

            estado_final = "👀 Pendiente aprobación"

        else:

            estado_final = "⚠️ Candidato sin emails"

        if _SHEETS_AVAILABLE:
            await update_lead_in_sheet(
                lote_id,
                place_id,
                {
                    "Estado": estado_final,
                },
            )

        if lead_ok:
            stats["ok"] += 1

        results.append(result)

        # Pausa entre leads para proteger APIs
        await asyncio.sleep(1.5)

    # ------------------------------------------------------------------
    # RESUMEN
    # ------------------------------------------------------------------

    if _SHEETS_AVAILABLE:

        try:
            await write_summary_row(
                lote_id,
                stats,
            )

        except Exception as e:
            print(
                f"  [Sheets] summary row error: {e}"
            )

    print(f"\n{'=' * 60}")
    print(
        f"✅ PIPELINE COMPLETADO — Lote: {lote_id}"
    )

    print(
        f"   Total: {stats['total']} leads | "
        f"OK: {stats['ok']} | "
        f"Errores: {stats['total'] - stats['ok']}"
    )

    print(
        f"   🔥 Calientes: {stats['calientes']}  "
        f"🟡 Tibios: {stats['tibios']}  "
        f"❄️ Fríos: "
        f"{stats['total'] - stats['calientes'] - stats['tibios']}"
    )

    # En esta fase los envíos automáticos están desactivados.
    print(
        "   ✉️ Emails enviados automáticamente: 0"
    )

    if sheet_url:
        print(f"   📊 Sheet: {sheet_url}")

    print(f"{'=' * 60}\n")

    return {
        "status": "ok",
        "lote_id": lote_id,
        "total_leads": stats["total"],
        "completados_ok": stats["ok"],
        "calientes": stats["calientes"],
        "tibios": stats["tibios"],
        "enviados": 0,
        "sheet_url": sheet_url,
        "results": results,
    }