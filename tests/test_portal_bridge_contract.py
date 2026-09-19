from app.utils.portal_bridge import CONTRACT_VERSION, build_portal_payload


def test_build_portal_payload_is_versioned_and_safe():
    payload = build_portal_payload(
        {
            "place_id": "place-123",
            "name": "Clínica Ejemplo",
            "phone": "+593999999999",
            "site": "https://example.test",
            "full_address": "Quito, Ecuador",
            "rating": 4.1,
            "query": "clínicas dentales Quito",
            "lote_id": "lote-001",
        },
        {
            "lead_score": 82,
            "score_version": "lince-v2-objective-2",
            "score_breakdown": [{"senal": "gtm_no_detectado", "puntos": 8}],
            "problema_principal": "Medición incompleta",
            "oportunidad": "Mejorar medición y conversión",
            "argumento_venta": "Revisar el recorrido de consultas",
            "servicios_recomendados": ["Rediseño y modernización web"],
            "servicio_principal": "Rediseño y modernización web",
        },
    )

    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["skill_case"]["case_id"] == "LINCE-place-123"
    assert payload["skill_case"]["evidence"]["score"] == 82
    assert payload["skill_case"]["authorization"]["create_or_update_crm_lead"] is True
    assert payload["skill_case"]["authorization"]["send_outreach"] is False
    assert payload["skill_case"]["authorization"]["mutate_client_systems"] is False


def test_build_portal_payload_normalizes_single_service():
    payload = build_portal_payload(
        {"place_id": "place-456", "name": "Negocio Ejemplo"},
        {"lead_score": 75, "servicios_recomendados": "Página web profesional"},
    )

    assert payload["servicios_recomendados"] == ["Página web profesional"]
    assert payload["servicio_principal"] == "Página web profesional"
