# Lince · Prospección uno a uno

Lince ya no se usa como máquina de envío masivo, sino como **radar**: encuentra negocios en Google Maps, detecta un dato real de cada uno y deja listo el mensaje para que una persona lo envíe.

## Flujo diario (20 minutos)

1. **Panel → P1:** busca un rubro y una zona, por ejemplo `taller mecánico norte Guayaquil` (20 resultados).
2. **📲 Prospectos del día** (`/prospectos`): la lista sale ordenada por oportunidad. Cada tarjeta muestra el hallazgo con datos reales, por ejemplo: *«tiene 10 reseñas en Google y los primeros resultados al buscar … tienen en promedio 80»*.
3. **WhatsApp:** abre el chat con el mensaje ya escrito. Revísalo, ajústalo si quieres y envíalo. La tarjeta queda marcada como contactada en ese navegador.
4. **Auditoría (JSON):** descarga la entrada para el PDF de auditoría de Noboweb, con la posición, la calificación, las reseñas y los competidores ya cargados. Lo que no se pudo medir queda como `PENDIENTE` y se completa a mano (ver `noboweb-landing/docs/ventas/AUDITORIA.md`).
5. **Descargar CSV:** sirve para llevar el seguimiento en una hoja de cálculo (columna `estado`).

Reglas:
- **WhatsApp solo uno a uno, enviado por una persona.** Los envíos masivos automáticos hacen que WhatsApp bloquee el número.
- Los teléfonos fijos aparecen como «Llamar».
- No se inventan datos: el hallazgo sale solo de lo que midió P1.

## Correo (canal secundario)

- **3 correos espaciados:** el día 1, 3 días después y 6 días después. Antes eran 5, uno por día.
- **El prompt prohíbe inventar** casos de éxito, testimonios o cifras.
- **Cada correo lleva una forma de darse de baja:** el texto «responda BAJA» y la cabecera `List-Unsubscribe`.
- **El remitente se configura** con `OUTREACH_FROM_EMAIL` y `OUTREACH_FROM_NAME`. Recomendación: un dominio aparte de `noboweb.com` (por ejemplo `hola@noboweb-mail.com`) con SPF, DKIM y DMARC, para que una queja de spam no afecte el correo principal.

## Seguridad

- Todo el panel y toda la API exigen la cabecera `X-Lince-Token`, con el valor de `LINCE_API_TOKEN`. El panel pide el token una vez y lo guarda en el navegador.
- Si falta `LINCE_API_TOKEN`, la API responde 503: nunca queda abierta por olvido.
- Las rutas públicas son solo `/`, `/prospectos`, `/health` y `/tasks/daily-sequence`. Esta última exige `TASK_SECRET`.
- Se eliminaron `/debug` y `/test-db`.

## Despliegue en el VPS (una vez)

```bash
cd /opt/lince            # o la carpeta donde corre el servicio (¿/opt/lince-v2?)
git pull origin main
LINCE_DIR=$(pwd) bash setup_vps_cron.sh
```

El script:
- Genera claves aleatorias para `TASK_SECRET` y `LINCE_API_TOKEN` si faltan o si siguen con el valor viejo publicado en el repositorio.
- Muestra el token del panel **una sola vez**: guárdalo.
- Rehace el cron para que lea la clave del `.env`.
- Reinicia el servicio.

Opcional: aplica `migrations/003_leads_reviews_position.sql` en Supabase para guardar la cantidad de reseñas y la posición en el mapa. Sin esa migración, P1 sigue funcionando, pero la lista no puede comparar reseñas ni posiciones.

## Pruebas

```bash
pytest tests/test_prospeccion.py tests/test_seguridad.py tests/test_secuencia.py
```

Estas pruebas no necesitan servidor ni APIs. Las de `tests/test_pipelines.py` son de integración: requieren el servidor corriendo con Supabase, OpenAI y Brevo configurados.
