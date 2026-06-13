# Joya de la Corona - Guía de Pruebas

## Tabla de contenidos
1. [Setup y verificación](#setup-y-verificación)
2. [Pruebas de endpoints](#pruebas-de-endpoints)
3. [Casos de uso end-to-end](#casos-de-uso-end-to-end)
4. [Testing con pytest](#testing-con-pytest)
5. [Debugging](#debugging)

---

## Setup y verificación

### 1. Verificar que el servidor está corriendo

```bash
# En una terminal, ejecuta:
cd c:\proyectos\joya-de-la-corona
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Deberías ver:
```
INFO:     Started server process [XXXX]
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### 2. Verificar health check

```bash
curl http://localhost:8000/health
```

Respuesta esperada:
```json
{"status":"saludable"}
```

### 3. Verificar configuración

```bash
curl http://localhost:8000/debug
```

Respuesta esperada:
```json
{
  "supabase_url": "https://bpycimognxzipvleqvsu.supabase.co",
  "supabase_key_primeros_10": "eyJhbGciOi..."
}
```

### 4. Verificar base de datos

```bash
curl http://localhost:8000/test-db
```

Respuesta esperada:
```json
{"tablas":"ok","datos":[...]}
```

### 5. Ejecutar verificación completa

```bash
python verify_setup.py
```

---

## Pruebas de endpoints

### P1: Google Maps Scraping

**Endpoint:** `POST /pipeline/p1`

**Descripción:** Busca negocios en Google Maps (usa mock si no hay API key)

**Request:**
```bash
curl -X POST http://localhost:8000/pipeline/p1 \
  -H "Content-Type: application/json" \
  -d '{
    "query": "restaurantes Ciudad de México",
    "limit": 5
  }'
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "encontrados": 5,
  "guardados": 5,
  "leads": [
    {
      "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
      "name": "Contramar",
      "category": "Restaurante",
      "rating": 4.7,
      "reviews_count": 850,
      "address": "Calle Alfonso Reyes 183, Mexico City, Mexico",
      "phone": "+52 55 1234 5678",
      "website": "https://contramar.com.mx",
      "city": "Mexico City",
      "country": "MX"
    }
    // ...más leads
  ]
}
```

---

### P2: Google Reviews

**Endpoint:** `POST /pipeline/p2`

**Descripción:** Obtiene reviews de un negocio por place_id

**Request:**
```bash
curl -X POST http://localhost:8000/pipeline/p2 \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
    "max_reviews": 10
  }'
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
  "reviews_guardadas": 3
}
```

---

### P3: Website Analysis

**Endpoint:** `POST /pipeline/p3`

**Descripción:** Analiza el sitio web de un negocio

**Request:**
```bash
curl -X POST http://localhost:8000/pipeline/p3 \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
    "url": "https://contramar.com.mx"
  }'
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "resultado": {
    "url": "https://contramar.com.mx",
    "seo_title": "Contramar - Restaurante de Mariscos",
    "seo_description": "Disfruta de la mejor comida con ingredientes frescos...",
    "contact_email_found": "info@contramar.com",
    "social_media": {
      "instagram": "https://instagram.com/contramar",
      "facebook": "https://facebook.com/contramar"
    },
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ"
  }
}
```

---

### P4: Keypoints & Lead Score

**Endpoint:** `POST /pipeline/p4`

**Descripción:** Genera análisis IA con problemas, oportunidades y lead score

**Request:**
```bash
curl -X POST http://localhost:8000/pipeline/p4 \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ"
  }'
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "resultado": {
    "problema_principal": "Baja presencia en redes sociales y marketing digital limitado",
    "oportunidad": "Implementar estrategia de marketing digital y gestión de redes sociales",
    "argumento_venta": "Ayudamos a restaurantes a aumentar sus reservas un 40% promedio",
    "lead_score": 8,
    "razon_score": "Rating alto (4.7+), reviews abundantes, sitio web existente",
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ"
  }
}
```

---

### P5: Email Generator

**Endpoint:** `POST /pipeline/p5`

**Descripción:** Genera secuencia de 5 emails personalizados

**Request:**
```bash
curl -X POST http://localhost:8000/pipeline/p5 \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ"
  }'
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "emails_generados": 5,
  "emails": [
    {
      "dia": 1,
      "asunto": "Idea rápida para aumentar reservas en 30 días",
      "cuerpo": "Hola, encontré tu restaurante y me impresionó la comida y reseñas..."
    },
    {
      "dia": 2,
      "asunto": "Restaurant en CDMX subió reservas 45% con esto",
      "cuerpo": "Un restaurante de 4.6 rating en Condesa implementó nuestra estrategia..."
    },
    // ...3 emails más (días 3-5)
  ]
}
```

---

### P6: Email Sender

**Endpoint:** `POST /pipeline/p6`

**Descripción:** Envía el email del día de la secuencia

**Request:**
```bash
curl -X POST http://localhost:8000/pipeline/p6 \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
    "to_email": "contacto@restaurante.com",
    "to_name": "Gerente del Restaurante"
  }'
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "dia": 1,
  "enviado_a": "contacto@restaurante.com",
  "resultado": {
    "messageId": "<202605062028.20728070435@smtp-relay.mailin.fr>"
  }
}
```

---

### Sequence Completa (P2-P5)

**Endpoint:** `POST /pipeline/sequence`

**Descripción:** Ejecuta P2, P3, P4, P5 en cascada para un lead

**Request:**
```bash
curl -X POST http://localhost:8000/pipeline/sequence \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
    "url": "https://contramar.com.mx",
    "max_reviews": 5
  }'
```

**Respuesta esperada:**
```json
{
  "status": "ok",
  "p2": {
    "status": "ok",
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
    "reviews_guardadas": 3
  },
  "p3": {
    "status": "ok",
    "resultado": { /* ... */ }
  },
  "p4": {
    "status": "ok",
    "resultado": { /* ... */ }
  },
  "p5": {
    "status": "ok",
    "emails_generados": 5,
    "emails": [ /* ... */ ]
  }
}
```

---

## Casos de uso end-to-end

### Caso 1: Flujo completo (escaneo → análisis → emails)

```bash
# 1. Buscar negocios
RESPONSE1=$(curl -s -X POST http://localhost:8000/pipeline/p1 \
  -H "Content-Type: application/json" \
  -d '{"query": "restaurantes México", "limit": 1}')

PLACE_ID=$(echo $RESPONSE1 | jq -r '.leads[0].place_id')
WEBSITE=$(echo $RESPONSE1 | jq -r '.leads[0].website')

echo "Place ID encontrado: $PLACE_ID"
echo "Website: $WEBSITE"

# 2. Ejecutar secuencia (P2-P5)
curl -X POST http://localhost:8000/pipeline/sequence \
  -H "Content-Type: application/json" \
  -d "{
    \"place_id\": \"$PLACE_ID\",
    \"url\": \"$WEBSITE\",
    \"max_reviews\": 5
  }"

# 3. Enviar primer email (P6)
curl -X POST http://localhost:8000/pipeline/p6 \
  -H "Content-Type: application/json" \
  -d "{
    \"place_id\": \"$PLACE_ID\",
    \"to_email\": \"test@example.com\",
    \"to_name\": \"Contacto\"
  }"
```

### Caso 2: Análisis de un lead específico

```bash
PLACE_ID="ChIJwYl1nwyucZQRi1J2mVlp2IQ"

# P3: Análisis de website
curl -X POST http://localhost:8000/pipeline/p3 \
  -H "Content-Type: application/json" \
  -d "{
    \"place_id\": \"$PLACE_ID\",
    \"url\": \"https://contramar.com.mx\"
  }"

# P4: Generar keypoints
curl -X POST http://localhost:8000/pipeline/p4 \
  -H "Content-Type: application/json" \
  -d "{\"place_id\": \"$PLACE_ID\"}"

# P5: Generar emails
curl -X POST http://localhost:8000/pipeline/p5 \
  -H "Content-Type: application/json" \
  -d "{\"place_id\": \"$PLACE_ID\"}"
```

---

## Testing con pytest

### Instalar pytest

```bash
pip install pytest pytest-asyncio pytest-cov
```

### Crear archivo de tests

Archivo: `tests/test_pipelines.py`

```python
import pytest
import asyncio
from app.pipelines.p1_google_maps import scrape_google_maps, procesar_y_guardar_leads
from app.pipelines.p5_email_generator import generar_secuencia_emails
from app.pipelines.p6_email_sender import enviar_email

@pytest.mark.asyncio
async def test_p1_scrape():
    """Test que P1 devuelve leads"""
    results = await scrape_google_maps(query="restaurante", limit=2)
    assert len(results) > 0
    assert 'place_id' in results[0]
    assert 'name' in results[0]

@pytest.mark.asyncio
async def test_p5_email_generation():
    """Test que P5 genera 5 emails"""
    emails = await generar_secuencia_emails(place_id="test_place_id")
    
    # Handle both dict y list responses
    if isinstance(emails, dict):
        email_list = emails.get('emails', [])
    else:
        email_list = emails
    
    assert len(email_list) == 5
    assert email_list[0].get('dia') == 1
    assert email_list[0].get('asunto')
    assert email_list[0].get('cuerpo')

@pytest.mark.asyncio
async def test_p6_email_send():
    """Test que P6 puede enviar email (mock)"""
    result = await enviar_email(
        to_email="test@example.com",
        to_name="Test User",
        asunto="Test Subject",
        cuerpo="Test body"
    )
    assert result is not None
    # Con BREVO mock, devuelve {"message": "mock_sent", ...}
```

### Ejecutar tests

```bash
# Todos los tests
pytest tests/ -v

# Con coverage
pytest tests/ --cov=app --cov-report=html

# Tests específicos
pytest tests/test_pipelines.py::test_p1_scrape -v
```

---

## Debugging

### Habilitar logging detallado

Editar `app/main.py`:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@app.post("/pipeline/p1")
async def ejecutar_p1(body: PipelineP1):
    logger.debug(f"P1 iniciado con query: {body.query}")
    # ...
```

### Verificar respuestas de Supabase

```python
import asyncio
from app.utils.supabase_client import supabase_select, supabase_insert

async def debug_supabase():
    # Verificar tabla leads
    leads = await supabase_select('leads', {})
    print(f"Leads en BD: {len(leads)}")
    print(f"Primero: {leads[0] if leads else 'N/A'}")
    
    # Verificar tabla emails
    emails = await supabase_select('emails', {})
    print(f"Emails en BD: {len(emails)}")

asyncio.run(debug_supabase())
```

### Verificar logs del servidor

```bash
# En la ventana donde corre uvicorn, verás logs como:
# INFO:     127.0.0.1:12345 - "POST /pipeline/p1 HTTP/1.1" 200 OK
# INFO:     Application startup complete
```

### Endpoints de debug

```bash
# Ver configuración cargada
curl http://localhost:8000/debug

# Ver estado de DB
curl http://localhost:8000/test-db

# Ver health
curl http://localhost:8000/health
```

---

## Checklist de verificación

- [ ] Servidor corre sin errores (`uvicorn app.main:app --reload`)
- [ ] `/health` devuelve `{"status":"saludable"}`
- [ ] `/debug` muestra SUPABASE_URL y SUPABASE_KEY
- [ ] `/test-db` devuelve `{"tablas":"ok",...}`
- [ ] P1 devuelve al menos 1 lead
- [ ] P5 devuelve 5 emails
- [ ] Tabla `emails` existe en Supabase (ejecutar SQL migration)
- [ ] `verify_setup.py` pasa sin errores
- [ ] `/pipeline/sequence` completa sin timeout (< 180s)
- [ ] P6 envía email sin error 500

---

## Solución de problemas

### Error: "Could not find the 'asunto' column of 'emails'"

**Solución:** Ejecutar la migración SQL:
```bash
# Ve a https://app.supabase.com → SQL Editor
# Copia y ejecuta: migrations/001_create_emails_table.sql
```

### Error: 500 en P6 después de P5

**Solución:** Verificar que tabla `emails` existe y tiene datos:
```bash
python -c "import asyncio; from app.utils.supabase_client import supabase_select; print(asyncio.run(supabase_select('emails', {})))"
```

### Timeout en /pipeline/sequence

**Solución:** Reducir `max_reviews` o usar valores más pequeños:
```bash
curl -X POST http://localhost:8000/pipeline/sequence \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
    "url": "https://example.com",
    "max_reviews": 2
  }'
```

### APIs externas no configuradas (OutScraper, Apify, OpenAI)

**Comportamiento:** Se usan datos mock automáticamente
**Verificar:** En `app/config.py` que `OUTSCRAPER_API_KEY`, `APIFY_API_KEY`, `OPENAI_API_KEY` sean válidas
**Logs:** Verás mensajes como "Usando datos de demostración"

---

## Referencias

- Swagger API: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Supabase: https://app.supabase.com
- FastAPI docs: https://fastapi.tiangolo.com/

