-- =====================================================================
-- Migración 002: tabla `emails` alineada con el código real (P5 y P6)
-- Reemplaza el esquema de 001 (una fila por email) por el esquema que
-- usa la aplicación: UNA FILA POR LEAD con columnas por día.
--
-- ⚠️ Si ya ejecutaste 001 y la tabla está vacía o solo tiene datos de
-- prueba, elimina la tabla vieja primero descomentando la línea DROP.
-- =====================================================================

-- DROP TABLE IF EXISTS emails;

CREATE TABLE IF NOT EXISTS emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id TEXT NOT NULL,
    company_name TEXT,
    recipient_email TEXT,

    -- Secuencia de 5 emails generada por P5
    email_1_subject TEXT,
    email_1_body TEXT,
    email_2_subject TEXT,
    email_2_body TEXT,
    email_3_subject TEXT,
    email_3_body TEXT,
    email_4_subject TEXT,
    email_4_body TEXT,
    email_5_subject TEXT,
    email_5_body TEXT,

    -- Estado del envío (P6)
    current_email_day INTEGER DEFAULT 0,
    sent_at_day1 TIMESTAMP WITH TIME ZONE,
    sent_at_day2 TIMESTAMP WITH TIME ZONE,
    sent_at_day3 TIMESTAMP WITH TIME ZONE,
    sent_at_day4 TIMESTAMP WITH TIME ZONE,
    sent_at_day5 TIMESTAMP WITH TIME ZONE,
    sequence_stopped BOOLEAN DEFAULT false,
    replied BOOLEAN DEFAULT false,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_emails_place_id ON emails(place_id);
CREATE INDEX IF NOT EXISTS idx_emails_pendientes
    ON emails(place_id, current_email_day)
    WHERE sequence_stopped = false AND replied = false;
