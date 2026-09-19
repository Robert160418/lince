"""Puente seguro y versionado entre Lince y Nobo Agent."""

import asyncio
from datetime import datetime, timezone

import requests

from app.config import PORTAL_WEBHOOK_URL, LINCE_WEBHOOK_SECRET


CONTRACT_VERSION = "noboweb.lince-lead.v1"


def build_portal_payload(lead: dict, keypoints: dict) -> dict:
    """Construye el contrato Lince → Nobo Agent sin autorizar contacto."""

    services = keypoints.get("servicios_recomendados") or []
    if not isinstance(services, list):
        services = [str(services)]

    score_breakdown = keypoints.get("score_breakdown") or []
    if not isinstance(score_breakdown, list):
        score_breakdown = []

    observed_at = datetime.now(timezone.utc).isoformat()
    place_id = lead.get("place_id")
    primary_service = keypoints.get("servicio_principal")
    if not primary_service and services:
        primary_service = services[0]

    # Los campos superiores preservan compatibilidad con el webhook actual.
    payload = {
        "place_id": place_id,
        "name": lead.get("name"),
        "phone": lead.get("phone") or lead.get("telephone"),
        "site": lead.get("site"),
        "full_address": lead.get("full_address"),
        "rating": lead.get("rating"),
        "query": lead.get("query"),
        "lote_id": lead.get("lote_id"),
        "lead_score": keypoints.get("lead_score"),
        "problema_principal": keypoints.get("problema_principal"),
        "oportunidad": keypoints.get("oportunidad"),
        "argumento_venta": keypoints.get("argumento_venta"),
        "servicios_recomendados": services,
        "servicio_principal": primary_service,
        "contract_version": CONTRACT_VERSION,
        "observed_at": observed_at,
        "source": "lince",
        "skill_case": {
            "case_id": f"LINCE-{place_id}" if place_id else None,
            "source": "lince",
            "source_lead_id": place_id,
            "client": lead.get("name"),
            "owner": "Roberto Noboa",
            "goal": "Calificar la oportunidad y definir el servicio inicial de Noboweb.",
            "request_type": "prospeccion",
            "market": lead.get("full_address") or lead.get("query"),
            "segment": lead.get("query"),
            "offer": primary_service,
            "evidence": {
                "observed_at": observed_at,
                "website": lead.get("site"),
                "rating": lead.get("rating"),
                "problem": keypoints.get("problema_principal"),
                "opportunity": keypoints.get("oportunidad"),
                "score": keypoints.get("lead_score"),
                "score_version": keypoints.get("score_version"),
                "score_breakdown": score_breakdown,
                "recommended_services": services,
                "primary_service": primary_service,
            },
            "authorization": {
                "public_research": True,
                "create_or_update_crm_lead": True,
                "prepare_outreach": True,
                "send_outreach": False,
                "mutate_client_systems": False,
            },
        },
    }
    return payload


async def push_lead_to_portal(lead: dict, keypoints: dict) -> dict:
    if not PORTAL_WEBHOOK_URL or not LINCE_WEBHOOK_SECRET:
        return {"status": "skipped", "reason": "PORTAL_WEBHOOK_URL o LINCE_WEBHOOK_SECRET no configurados"}

    payload = build_portal_payload(lead, keypoints)

    try:
        resp = await asyncio.to_thread(
            requests.post,
            PORTAL_WEBHOOK_URL,
            json={"leads": [payload]},
            headers={
                "X-Lince-Secret": LINCE_WEBHOOK_SECRET,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  [Portal CRM] error {resp.status_code}: {resp.text[:200]}")
            return {
                "status": "error",
                "http_status": resp.status_code,
                "contract_version": CONTRACT_VERSION,
            }

        try:
            response_data = resp.json()
        except ValueError:
            response_data = {}

        print(f"  [Portal CRM] lead sincronizado: {lead.get('place_id')}")
        return {
            **response_data,
            "status": "ok",
            "contract_version": CONTRACT_VERSION,
        }
    except Exception as e:
        print(f"  [Portal CRM] excepción al sincronizar: {e}")
        return {
            "status": "error",
            "error": str(e),
            "contract_version": CONTRACT_VERSION,
        }
