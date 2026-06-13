# Creación de tabla `emails` en Supabase

> ⚠️ **Actualizado (junio 2026):** el esquema anterior (una fila por email, columnas
> `dia/asunto/cuerpo`) quedó obsoleto y NO es compatible con el código.
> Usa el SQL de `migrations/002_emails_table_v2.sql`, que es el esquema real
> que usan los pipelines P5 (generación) y P6 (envío): **una fila por lead**
> con columnas `email_1_subject … email_5_body`.

## SQL a ejecutar

Copia y pega el contenido de `migrations/002_emails_table_v2.sql` en
Supabase Dashboard → SQL Editor → New query → Run.

Si ya habías creado la tabla con el esquema viejo (migración 001) y no tiene
datos importantes, descomenta la línea `DROP TABLE IF EXISTS emails;` al
inicio del archivo antes de ejecutarlo.

## Pasos

1. Ve a tu proyecto Supabase: https://app.supabase.com
2. Abre SQL Editor (menú izquierdo)
3. Haz clic en "New query"
4. Pega el SQL de `migrations/002_emails_table_v2.sql`
5. Haz clic en "Run"

## Verificación

```bash
cd c:\proyectos\joya-de-la-corona
python -c "import asyncio; from app.utils.supabase_client import supabase_select; print(asyncio.run(supabase_select('emails')))"
```

Si devuelve `[]` (lista vacía), está funcionando correctamente.

## Columnas principales

- **place_id**: ID del negocio/lead
- **company_name**: nombre del negocio
- **recipient_email**: email del destinatario (se puede fijar luego con `/setup/recipient-email/{place_id}/{email}` o desde P6)
- **email_1_subject … email_5_body**: la secuencia de 5 correos generada por P5
- **current_email_day**: último día enviado (0 = ninguno)
- **sent_at_day1 … sent_at_day5**: fecha/hora de cada envío
- **sequence_stopped / replied**: pausan la secuencia (P6 los respeta)
