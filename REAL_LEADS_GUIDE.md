# Guía: Sacar Leads Reales

## Estado Actual
La aplicación está funcionando con datos **mock** (de demostración). Para sacar **leads reales** de Google Maps, necesitas configurar las APIs externas.

## Opciones para Sacar Leads Reales

### Opción 1: OutScraper API (Recomendado)

OutScraper es la forma más directa para scraping de Google Maps. 

**Pasos:**
1. Regístrate en https://outscraper.com
2. Obtén tu API key (Free plan: 100 requests/mes)
3. Edita `.env` y agrega:
   ```
   OUTSCRAPER_API_KEY=tu_api_key_aqui
   ```
4. Reinicia el servidor
5. Usa el botón P1 normalmente

**Estructura de P1 (OutScraper):**
```json
{
  "query": "restaurantes Mexico City",
  "limit": 20
}
```

### Opción 2: Google Maps API + Geocoding

Si prefieres usar Google Maps API directamente:

**Pasos:**
1. Ve a https://console.cloud.google.com
2. Activa "Places API" y "Maps JavaScript API"
3. Crea una API key
4. Agrega a `.env`:
   ```
   GOOGLE_MAPS_API_KEY=tu_api_key_aqui
   ```

### Opción 3: Apify (Para scraping avanzado)

Apify permite scraping sin API key restrictiva.

**Pasos:**
1. Regístrate en https://apify.com
2. Obtén API key en Settings
3. Agrega a `.env`:
   ```
   APIFY_API_KEY=tu_api_key_aqui
   ```

---

## Configuración Actual (.env)

Edita el archivo `.env` en la raíz del proyecto:

```bash
# Supabase (ya configurado)
SUPABASE_URL=https://bpycimognxzipvleqvsu.supabase.co
SUPABASE_KEY=eyJhbGciOi...

# APIs para leads (VACIAS = usan MOCKS)
OUTSCRAPER_API_KEY=
APIFY_API_KEY=
OPENAI_API_KEY=

# APIs para email
BREVO_API_KEY=

# Google Sheets (opcional)
GOOGLE_SHEET_ID=
GOOGLE_SHEETS_CREDENTIALS_PATH=
```

---

## Flujo Completo con Leads Reales

Una vez configurados los APIs:

### 1. Ejecutar P1 (Scraping)
```bash
POST /pipeline/p1
{
  "query": "cafeterías Bogotá",
  "limit": 50
}
```

Esto devuelve 50 cafeterías reales de Bogotá, guardadas en Supabase.

### 2. Seleccionar un Lead
En la UI, abre el dropdown "Lead seleccionado" y elige uno de los leads encontrados.

### 3. Ejecutar Secuencia P2-P5
Haz click en "Ejecutar secuencia P2-P5" para:
- **P2:** Obtener 20+ reviews reales del Google Maps
- **P3:** Analizar su sitio web
- **P4:** Generar análisis IA (necesita OpenAI API)
- **P5:** Generar 5 emails personalizados

### 4. Enviar Email (P6)
```bash
POST /pipeline/p6
{
  "place_id": "ChIJ...",
  "to_email": "gerente@negocio.com",
  "to_name": "Juan"
}
```

---

## Comparación: Mock vs Real

| Aspecto | Mock | Real |
|--------|------|------|
| Fuente | Hardcoded en código | Google Maps / OutScraper |
| Datos | Ejemplo de restaurante | 50+ negocios reales |
| Reviews | 3 reviews fake | 20+ reviews reales |
| Análisis IA | Resultado fijo | Generado con OpenAI GPT-4 |
| Emails | Template genérico | Personalizados con datos reales |
| Tiempo | Instant | 30-60s por secuencia |

---

## Recomendación de APIs (Presupuesto Gratuito)

### Opción Mínima (Gratis)
```
✓ OutScraper: 100 requests/mes (GRATIS)
✓ Google Maps API: $0.01-0.10 por request (primeros 28,500 request gratis)
✓ OpenAI API: Requiere pago ($0.0015 por 1K tokens)
✓ Brevo: Hasta 300 emails/día (GRATIS)
```

**Costo estimado/mes:** $5-20 (si generas muchos leads)

### Opción Recomendada para Negocio
```
✓ OutScraper Pro: $30-100/mes
✓ OpenAI API: $5-20/mes (gpt-4o-mini es muy barato)
✓ Brevo: $25/mes (30K emails)
✓ Supabase: $25/mes (Pro)

Total: ~$85-170/mes
```

---

## Cómo Obtener las APIs

### OutScraper
1. https://outscraper.com/sign-up
2. Free plan: 100 requests/mes
3. Copia tu API key

### OpenAI
1. https://platform.openai.com/account/api-keys
2. Crea una nueva key
3. Usa gpt-4o-mini (muy barato: $0.15 por 1M tokens)

### Brevo (Sendinblue)
1. https://www.brevo.com/
2. Registro gratuito
3. Obtén API key

### Google Maps API
1. https://console.cloud.google.com
2. Habilita: Places API, Maps JavaScript API
3. Crea credenciales (API key)

---

## Testing Local con Leads Reales

**Con OutScraper API key configurada:**

```bash
# Buscar restaurantes reales
curl -X POST http://localhost:8000/pipeline/p1 \
  -H "Content-Type: application/json" \
  -d '{"query": "restaurantes Mexico City", "limit": 10}'

# Resultado: 10 restaurantes reales con place_id válidos
```

**Luego ejecutar secuencia con un lead real:**

```bash
curl -X POST http://localhost:8000/pipeline/sequence \
  -H "Content-Type: application/json" \
  -d '{
    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
    "url": "https://contramar.com.mx",
    "max_reviews": 10
  }'
```

---

## Solución de Problemas

### P1 devuelve datos mock pero quería reales
**Solución:** Verifica que `OUTSCRAPER_API_KEY` en `.env` sea válida
```bash
# Ver si está configurado
grep OUTSCRAPER_API_KEY .env
```

### Error: "OUTSCRAPER_API_KEY inválida"
**Causa:** La API key no es válida o está vacía
**Solución:** 
1. Regístrate en https://outscraper.com
2. Obtén una nueva API key
3. Actualiza `.env`
4. Reinicia el servidor: `uvicorn app.main:app --reload`

### P4 devuelve resultado fijo (no IA)
**Causa:** OPENAI_API_KEY no es válida
**Solución:**
1. Ve a https://platform.openai.com/account/api-keys
2. Crea una API key
3. Agrega a `.env`: `OPENAI_API_KEY=sk-...`
4. Reinicia

### P5 devuelve emails genéricos
**Causa:** Sin OpenAI API, usa template fijo
**Solución:** Configura `OPENAI_API_KEY` (ver P4)

---

## Próximos Pasos

1. **Elige una opción de API** (recomendado: OutScraper)
2. **Registrate y obtén la API key**
3. **Actualiza `.env`:**
   ```
   OUTSCRAPER_API_KEY=tu_key_aqui
   OPENAI_API_KEY=sk-...
   ```
4. **Reinicia el servidor:**
   ```bash
   uvicorn app.main:app --reload
   ```
5. **Ejecuta P1 nuevamente** — ahora debería traer leads reales

---

## Archivo .env Completo (Ejemplo)

```bash
# === SUPABASE (Obligatorio) ===
SUPABASE_URL=https://bpycimognxzipvleqvsu.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# === APIs para Leads (Recomendado: al menos OutScraper) ===
OUTSCRAPER_API_KEY=sk_test_...           # Recomendado
APIFY_API_KEY=apify_api_...              # Alternativa

# === APIs para Análisis ===
OPENAI_API_KEY=sk-proj-...               # Para P4 y P5 (IA)

# === APIs para Email ===
BREVO_API_KEY=xkeysib_...                # Para P6 (envío)
REDIS_URL=redis://localhost:6379         # Opcional

# === Google Sheets (Opcional) ===
GOOGLE_SHEET_ID=1a2b3c...
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/credentials.json
```

---

## Dashboard Monitoreo

Después de sacar 50+ leads, puedes:

1. **Ver en Supabase Dashboard:**
   - Ve a https://app.supabase.com
   - Tabla `leads` → verás todos los leads scrapeados
   - Tabla `reviews` → reviews descargadas
   - Tabla `emails` → emails generados

2. **Exportar a CSV:**
   ```bash
   # En Supabase: SQL Editor
   SELECT * FROM leads LIMIT 100;
   # Botón "Download CSV"
   ```

3. **Análisis en Python:**
   ```bash
   python -c "
   import asyncio
   from app.utils.supabase_client import supabase_select
   
   async def get_stats():
       leads = await supabase_select('leads', {})
       print(f'Total leads: {len(leads)}')
       print(f'Rating promedio: {sum(l[\"rating\"] for l in leads) / len(leads):.1f}')
   
   asyncio.run(get_stats())
   "
   ```

---

## Soporte

Si tienes problemas:

1. **Verifica logs del servidor:** Mira la terminal donde corre uvicorn
2. **Prueba health check:** `curl http://localhost:8000/health`
3. **Ve a Swagger UI:** http://localhost:8000/docs — prueba endpoints allí
4. **Lee TEST_DOCUMENTATION.md** — guía completa de pruebas

