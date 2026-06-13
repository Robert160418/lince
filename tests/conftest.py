import pytest
import asyncio
from pathlib import Path
import sys

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Crea un event loop para tests asincronos"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def base_url():
    """URL base del servidor"""
    return "http://localhost:8000"


@pytest.fixture(scope="session")
def test_place_id():
    """Place ID de prueba"""
    return "ChIJwYl1nwyucZQRi1J2mVlp2IQ"


@pytest.fixture(scope="session")
def test_email():
    """Email de prueba"""
    return "test@example.com"


def pytest_configure(config):
    """Configuración inicial de pytest"""
    config.addinivalue_line(
        "markers", "slow: marca tests que son lentos"
    )
    config.addinivalue_line(
        "markers", "integration: marca tests de integración"
    )
    config.addinivalue_line(
        "markers", "unit: marca tests unitarios"
    )
