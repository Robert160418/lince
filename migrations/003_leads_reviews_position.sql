-- =====================================================================
-- Migración 003: datos de Google Maps que usa la auditoría express
-- reviews_count: cantidad de reseñas del negocio
-- map_position:  posición en el mapa para la búsqueda del lote (1 = primero)
-- Opcional: si no se aplica, P1 guarda el lead sin estos dos campos.
-- =====================================================================
ALTER TABLE leads ADD COLUMN IF NOT EXISTS reviews_count INTEGER;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS map_position INTEGER;
