-- Crear tabla emails con las columnas necesarias
CREATE TABLE IF NOT EXISTS emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id TEXT NOT NULL,
    dia INTEGER NOT NULL,
    asunto TEXT NOT NULL,
    cuerpo TEXT NOT NULL,
    enviado BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Crear índice en place_id para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_emails_place_id ON emails(place_id);

-- Crear índice en lugar_id + enviado para buscar pendientes
CREATE INDEX IF NOT EXISTS idx_emails_place_id_enviado ON emails(place_id, enviado);
