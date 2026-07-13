"""
Puente Lince → CRM del portal (portal.noboweb.com).

Después de que P4 califica un lead (score + keypoints IA), este módulo lo
empuja al webhook del portal para que aparezca automáticamente en
Clientes → CRM, sin que nadie tenga que copiarlo a mano desde el Sheet.

Si el portal no responde o las credenciales no están configuradas, no
rompe el pipeline de Lince — solo lo registra en consola. Lince sigue
funcionando de forma completamente independiente del portal.
"""
import requests
from app.config import PORTAL_WEBHOOK_URL, LINCE_WEBHOOK_SECRET


async def push_lead_to_portal(lead: dict, keypoints: dict) -> dict:
    if not PORTAL_WEBHOOK_URL or not LINCE_WEBHOOK_SECRET:
        return {"status": "skipped", "reason": "PORTAL_WEBHOOK_URL o LINCE_WEBHOOK_SECRET no configurados"}

    payload = {
        "place_id": lead.get("place_id"),
        "name": lead.get("name"),
        "phone": lead.get("phone"),
        "site": lead.get("site"),
        "full_address": lead.get("full_address"),
        "rating": lead.get("rating"),
        "query": lead.get("query"),
        "lote_id": lead.get("lote_id"),
        "lead_score": keypoints.get("lead_score"),
        "problema_principal": keypoints.get("problema_principal"),
        "oportunidad": keypoints.get("oportunidad"),
        "argumento_venta": keypoints.get("argumento_venta"),
        "servicios_recomendados": keypoints.get("servicios_recomendados") or [],
    }

    try:
        resp = requests.post(
            PORTAL_WEBHOOK_URL,
            json={"leads": [payload]},
            headers={"X-Lince-Secret": LINCE_WEBHOOK_SECRET, "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  [Portal CRM] error {resp.status_code}: {resp.text[:200]}")
            return {"status": "error", "http_status": resp.status_code}
        print(f"  [Portal CRM] lead sincronizado: {lead.get('name')}")
        return {"status": "ok", **resp.json()}
    except Exception as e:
        print(f"  [Portal CRM] excepción al sincronizar: {e}")
        return {"status": "error", "error": str(e)}
