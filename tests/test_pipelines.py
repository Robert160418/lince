"""
Tests automáticos para Joya de la Corona
Uso: pytest tests/ -v
"""

import pytest
import asyncio
import httpx
from pathlib import Path

# Configuración
BASE_URL = "http://localhost:8000"
TIMEOUT = 180.0
TEST_PLACE_ID = "ChIJwYl1nwyucZQRi1J2mVlp2IQ"
TEST_EMAIL = "test@example.com"


class TestHealthCheck:
    """Tests de verificación básica"""

    def test_health_endpoint(self):
        """Verifica que el servidor está en línea"""
        response = httpx.get(f"{BASE_URL}/health", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_debug_endpoint(self):
        """Verifica que la configuración está cargada"""
        response = httpx.get(f"{BASE_URL}/debug", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "supabase_url" in data
        assert "supabase_key_primeros_10" in data

    def test_test_db_endpoint(self):
        """Verifica que Supabase está conectado"""
        response = httpx.get(f"{BASE_URL}/test-db", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert "tablas" in data
        assert data["tablas"] == "ok"


class TestPipeline1:
    """Tests del Pipeline P1 (Google Maps Scraping)"""

    def test_p1_basic(self):
        """Ejecuta P1 con query básica"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p1",
            json={"query": "restaurantes", "limit": 2},
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["encontrados"] >= 0
        assert data["guardados"] >= 0
        assert isinstance(data["leads"], list)

    def test_p1_with_limit(self):
        """P1 respeta el parámetro limit"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p1",
            json={"query": "café", "limit": 1},
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["leads"]) <= 1

    def test_p1_leads_structure(self):
        """P1 devuelve leads con estructura correcta"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p1",
            json={"query": "hotel", "limit": 1},
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["leads"]:
            lead = data["leads"][0]
            required_fields = ["place_id", "name", "rating", "phone", "site", "full_address"]
            for field in required_fields:
                assert field in lead, f"Lead falta campo: {field}"


class TestPipeline2:
    """Tests del Pipeline P2 (Reviews)"""

    def test_p2_basic(self):
        """Ejecuta P2 para un place_id"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p2",
            json={"place_id": TEST_PLACE_ID, "max_reviews": 3},
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["place_id"] == TEST_PLACE_ID
        assert "reviews_guardadas" in data
        assert data["reviews_guardadas"] >= 0

    def test_p2_with_different_place_id(self):
        """P2 funciona con diferentes place_ids"""
        place_ids = [
            TEST_PLACE_ID,
            "ChIJ7zF5Sw-ucZQRi1J2mVlp2IQ"
        ]
        for place_id in place_ids:
            response = httpx.post(
                f"{BASE_URL}/pipeline/p2",
                json={"place_id": place_id, "max_reviews": 1},
                timeout=TIMEOUT
            )
            assert response.status_code == 200


class TestPipeline3:
    """Tests del Pipeline P3 (Website Analysis)"""

    def test_p3_basic(self):
        """Ejecuta P3 con URL válida"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p3",
            json={
                "place_id": TEST_PLACE_ID,
                "url": "https://contramar.com.mx"
            },
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "resultado" in data
        resultado = data["resultado"]
        assert resultado["place_id"] == TEST_PLACE_ID
        assert "url" in resultado
        assert "website_title" in resultado

    def test_p3_handles_invalid_url(self):
        """P3 maneja URLs inválidas gracefully"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p3",
            json={
                "place_id": TEST_PLACE_ID,
                "url": "https://nonexistent-domain-12345.com"
            },
            timeout=TIMEOUT
        )
        # Debería devolver 200 con datos mock si falla
        assert response.status_code == 200


class TestPipeline4:
    """Tests del Pipeline P4 (Keypoints & Lead Score)"""

    def test_p4_basic(self):
        """Ejecuta P4 para un place_id"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p4",
            json={"place_id": TEST_PLACE_ID},
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        resultado = data["resultado"]
        assert "problema_principal" in resultado
        assert "oportunidad" in resultado
        assert "argumento_venta" in resultado
        assert "lead_score" in resultado
        assert "razon_score" in resultado
        assert 1 <= resultado["lead_score"] <= 100


class TestPipeline5:
    """Tests del Pipeline P5 (Email Generator)"""

    def test_p5_generates_5_emails(self):
        """P5 genera exactamente 5 emails"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p5",
            json={"place_id": TEST_PLACE_ID},
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["emails_generados"] == 5
        
        # Handle both old list and new dict response
        emails = data["emails"]
        if isinstance(emails, dict):
            email_list = emails.get("emails", [])
        else:
            email_list = emails
        
        assert len(email_list) == 5

    def test_p5_email_structure(self):
        """P5 genera emails con estructura correcta"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p5",
            json={"place_id": TEST_PLACE_ID},
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        
        emails = data["emails"]
        if isinstance(emails, dict):
            email_list = emails.get("emails", [])
        else:
            email_list = emails
        
        for i, email in enumerate(email_list, 1):
            assert email["dia"] == i
            assert "asunto" in email
            assert "cuerpo" in email
            assert len(email["asunto"]) > 0
            assert len(email["cuerpo"]) > 0


class TestPipeline6:
    """Tests del Pipeline P6 (Email Sender)"""

    def test_p6_sends_email(self):
        """P6 envía un email"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p6",
            json={
                "place_id": TEST_PLACE_ID,
                "to_email": TEST_EMAIL,
                "to_name": "Test User"
            },
            timeout=TIMEOUT
        )
        # 200 o error graceful
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "message" in data


class TestSequence:
    """Tests de la secuencia completa (P2-P5)"""

    def test_sequence_executes(self):
        """Ejecuta la secuencia completa"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/sequence",
            json={
                "place_id": TEST_PLACE_ID,
                "url": "https://contramar.com.mx",
                "max_reviews": 2
            },
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "p2" in data
        assert "p3" in data
        assert "p4" in data
        assert "p5" in data

    def test_sequence_p2_output(self):
        """Verifica output de P2 en sequence"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/sequence",
            json={
                "place_id": TEST_PLACE_ID,
                "url": "https://example.com",
                "max_reviews": 1
            },
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["p2"]["status"] == "ok"
        assert "reviews_guardadas" in data["p2"]

    def test_sequence_p4_output(self):
        """Verifica output de P4 en sequence"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/sequence",
            json={
                "place_id": TEST_PLACE_ID,
                "url": "https://example.com",
                "max_reviews": 1
            },
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        resultado = data["p4"]["resultado"]
        assert "lead_score" in resultado
        assert 1 <= resultado["lead_score"] <= 100


class TestErrorHandling:
    """Tests de manejo de errores"""

    def test_p1_with_empty_query(self):
        """P1 maneja query vacía"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p1",
            json={"query": "", "limit": 5},
            timeout=TIMEOUT
        )
        # Debería devolver 200 (vacío) o error validado
        assert response.status_code in [200, 422]

    def test_invalid_json(self):
        """Endpoints rechazan JSON inválido"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p1",
            content="invalid json",
            timeout=TIMEOUT
        )
        assert response.status_code >= 400

    def test_missing_required_fields(self):
        """Endpoints validan campos requeridos"""
        response = httpx.post(
            f"{BASE_URL}/pipeline/p1",
            json={"limit": 5},  # falta 'query'
            timeout=TIMEOUT
        )
        assert response.status_code in [422]


# Tests asincronos
@pytest.mark.asyncio
async def test_async_p1():
    """Test asincrónico de P1"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/pipeline/p1",
            json={"query": "restaurante", "limit": 1},
            timeout=TIMEOUT
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_async_sequence():
    """Test asincrónico de sequence"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/pipeline/sequence",
            json={
                "place_id": TEST_PLACE_ID,
                "url": "https://example.com",
                "max_reviews": 1
            },
            timeout=TIMEOUT
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
