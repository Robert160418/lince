"""Pruebas unitarias de la prospección uno a uno (no necesitan servidor ni APIs)."""
from urllib.parse import unquote

import pytest

from app.utils import prospeccion as p


def _lote():
    return [
        {"place_id": "a", "name": "Taller Uno", "map_position": 1, "rating": 4.8, "reviews_count": 120, "site": "https://uno.ec", "phone": "042000000", "query": "taller Guayaquil"},
        {"place_id": "b", "name": "Taller Dos", "map_position": 2, "rating": 4.6, "reviews_count": 80, "site": "https://dos.ec", "phone": "0991112222", "query": "taller Guayaquil"},
        {"place_id": "c", "name": "Taller Tres", "map_position": 3, "rating": 4.5, "reviews_count": 40, "site": None, "phone": None, "query": "taller Guayaquil"},
        {"place_id": "d", "name": "Motor Prueba", "map_position": 7, "rating": 4.2, "reviews_count": 10, "site": None, "phone": "+593 98 589 6547", "query": "taller Guayaquil"},
    ]


@pytest.mark.parametrize("entrada,esperado", [
    ("0985896547", "593985896547"),
    ("+593 98 589 6547", "593985896547"),
    ("098-589-6547", "593985896547"),
    ("042000000", None),          # fijo de Guayaquil: no es WhatsApp
    ("", None),
    (None, None),
])
def test_movil_ecuador(entrada, esperado):
    assert p.movil_ecuador(entrada) == esperado


def test_hallazgo_usa_solo_datos_medidos():
    lote = _lote()
    lead = lote[3]
    hs = p.hallazgos(lead, lote)
    # El más fuerte: 10 reseñas frente al promedio de los 3 primeros (120+80+40)/3 = 80
    assert hs[0][1] == "tiene 10 reseñas en Google y los primeros resultados al buscar «taller Guayaquil» tienen en promedio 80"
    textos = " ".join(t for _, t in hs)
    assert "sitio web" in textos and "puesto 7" in textos and "4.2" in textos


def test_sin_datos_no_inventa():
    lead = {"place_id": "x", "name": "Negocio", "site": "https://x.ec"}
    assert p.hallazgos(lead, [lead]) == []
    assert "vi algunas oportunidades" in p.mensaje_whatsapp(lead, [lead])


def test_lista_ordenada_por_oportunidad_y_canal():
    filas = p.lista_del_dia(_lote())
    assert filas[0]["negocio"] == "Motor Prueba"
    assert filas[0]["canal"] == "WhatsApp"
    assert filas[0]["whatsapp"].startswith("https://wa.me/593985896547?text=")
    assert "Motor Prueba" in unquote(filas[0]["whatsapp"])
    canales = {f["negocio"]: f["canal"] for f in filas}
    assert canales["Taller Uno"] == "Llamar" and canales["Taller Tres"] == "Sin teléfono"


def test_auditoria_json_marca_pendiente_lo_no_medido():
    lote = _lote()
    a = p.auditoria_json(lote[3], lote)
    g = a["google"]
    assert g["calificacion"] == 4.2 and g["resenas"] == 10 and g["posicion_mapa"] == 7
    assert g["web_enlazada"] is False
    assert g["fotos"] == p.PENDIENTE and a["whatsapp"]["minutos_respuesta"] == p.PENDIENTE
    assert a["retencion"] is None
    assert [c["nombre"] for c in a["competidores"]] == ["Taller Uno", "Taller Dos", "Taller Tres"]


def test_auditoria_sin_reseñas_medidas():
    lead = {"place_id": "x", "name": "N", "rating": None, "reviews_count": None}
    a = p.auditoria_json(lead, [lead])
    assert a["google"]["calificacion"] == p.PENDIENTE
    assert a["competidores"] == p.PENDIENTE
