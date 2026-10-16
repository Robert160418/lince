"""
Prospección uno a uno: convierte los leads de un lote (P1) en una lista diaria
para contactar por WhatsApp, cada uno con un hallazgo REAL de su negocio, y en
el JSON de entrada de la auditoría de Noboweb (noboweb-landing/scripts/auditoria.mjs).

Reglas:
- Solo se usan datos medidos por P1 (posición, calificación, reseñas, web).
  Lo que no se midió sale como "PENDIENTE" en la auditoría: nunca se inventa.
- WhatsApp solo para celulares ecuatorianos (09…); los fijos quedan para llamar.
- Nada se envía solo: el mensaje queda listo y el envío lo hace una persona.
"""

import re
import urllib.parse
from datetime import date

PENDIENTE = "PENDIENTE"


# ── Datos básicos ─────────────────────────────────────────────────────────────

def movil_ecuador(telefono) -> str | None:
    """Devuelve el celular en formato internacional (5939XXXXXXXX) o None si es fijo o inválido."""
    if not telefono:
        return None
    digitos = re.sub(r"\D", "", str(telefono))
    if digitos.startswith("593"):
        resto = digitos[3:]
    elif digitos.startswith("0"):
        resto = digitos[1:]
    else:
        resto = digitos
    if len(resto) == 9 and resto.startswith("9"):
        return "593" + resto
    return None


def _num(valor):
    return valor if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None


def competidores(lead: dict, lote: list, n: int = 3) -> list:
    """Los n primeros del mapa en la misma búsqueda, sin contar al propio negocio."""
    otros = [x for x in lote if x.get("place_id") != lead.get("place_id")]
    otros.sort(key=lambda x: _num(x.get("map_position")) or 999)
    return otros[:n]


def promedio_resenas(comps: list) -> int | None:
    valores = [_num(c.get("reviews_count")) for c in comps]
    valores = [v for v in valores if v is not None]
    return round(sum(valores) / len(valores)) if valores else None


# ── Hallazgo y prioridad ──────────────────────────────────────────────────────

def hallazgos(lead: dict, lote: list) -> list:
    """Hallazgos verificables, del más fuerte al más débil. Cada uno: (peso, texto)."""
    busqueda = lead.get("query") or "su rubro"
    resenas = _num(lead.get("reviews_count"))
    rating = _num(lead.get("rating"))
    posicion = _num(lead.get("map_position"))
    prom = promedio_resenas(competidores(lead, lote))
    salida = []

    if resenas is not None and prom and resenas < prom * 0.5:
        salida.append((4, f"tiene {resenas} reseñas en Google y los primeros resultados al buscar «{busqueda}» tienen en promedio {prom}"))
    if not lead.get("site"):
        salida.append((3, "su ficha de Google no tiene un sitio web enlazado"))
    if posicion is not None and posicion > 3:
        salida.append((2, f"aparece en el puesto {posicion} al buscar «{busqueda}» en Google Maps"))
    if rating is not None and rating < 4.3:
        salida.append((2, f"su calificación en Google es de {rating:.1f} estrellas"))
    salida.sort(key=lambda h: -h[0])
    return salida


def puntaje(lead: dict, lote: list) -> int:
    """Prioridad de contacto: más oportunidades visibles y un celular = primero en la lista."""
    total = sum(peso for peso, _ in hallazgos(lead, lote))
    if movil_ecuador(lead.get("phone")):
        total += 2
    return total


def mensaje_whatsapp(lead: dict, lote: list) -> str:
    nombre = lead.get("name") or "su negocio"
    hs = hallazgos(lead, lote)
    if hs:
        dato = f"Revisé cómo aparece {nombre} en Google: {hs[0][1]}."
    else:
        dato = f"Revisé cómo aparece {nombre} en Google y vi algunas oportunidades para que más clientes lo encuentren y le escriban."
    return (
        "Hola, buen día. Soy Roberto Noboa, de Noboweb. "
        f"{dato} "
        "Le preparé un diagnóstico corto y sin costo con lo que encontré y cómo mejorarlo. "
        "¿Se lo envío por aquí?"
    )


def enlace_whatsapp(lead: dict, lote: list) -> str | None:
    movil = movil_ecuador(lead.get("phone"))
    if not movil:
        return None
    return f"https://wa.me/{movil}?text={urllib.parse.quote(mensaje_whatsapp(lead, lote))}"


def lista_del_dia(lote: list, limite: int = 20) -> list:
    """Prospectos del lote ordenados por prioridad, listos para contactar."""
    filas = []
    for lead in lote:
        hs = hallazgos(lead, lote)
        filas.append({
            "place_id": lead.get("place_id"),
            "negocio": lead.get("name"),
            "telefono": lead.get("phone"),
            "posicion_mapa": lead.get("map_position"),
            "calificacion": lead.get("rating"),
            "resenas": lead.get("reviews_count"),
            "web": lead.get("site"),
            "hallazgo": hs[0][1] if hs else "",
            "puntaje": puntaje(lead, lote),
            "mensaje": mensaje_whatsapp(lead, lote),
            "whatsapp": enlace_whatsapp(lead, lote),
            "canal": "WhatsApp" if movil_ecuador(lead.get("phone")) else ("Llamar" if lead.get("phone") else "Sin teléfono"),
        })
    filas.sort(key=lambda f: -f["puntaje"])
    return filas[:limite]


# ── Auditoría ─────────────────────────────────────────────────────────────────

def _o_pendiente(valor):
    return PENDIENTE if valor is None else valor


def auditoria_json(lead: dict, lote: list) -> dict:
    """Entrada para `npm run auditoria` en noboweb-landing, con lo que P1 midió."""
    comps = competidores(lead, lote)
    return {
        "fecha": date.today().isoformat(),
        "negocio": {
            "nombre": lead.get("name") or PENDIENTE,
            "tipo": PENDIENTE,
            "sector": lead.get("full_address") or PENDIENTE,
        },
        "whatsapp": {
            "hora_prueba": PENDIENTE,
            "pregunta": PENDIENTE,
            "minutos_respuesta": PENDIENTE,
            "respondio_pregunta": PENDIENTE,
            "ofrecio_cita": PENDIENTE,
            "mensaje_bienvenida": PENDIENTE,
        },
        "google": {
            "busqueda": lead.get("query") or PENDIENTE,
            "posicion_mapa": _o_pendiente(_num(lead.get("map_position"))),
            "perfil_verificado": PENDIENTE,
            "fotos": PENDIENTE,
            "horario_completo": PENDIENTE,
            "descripcion_servicios": PENDIENTE,
            "web_enlazada": bool(lead.get("site")),
            "calificacion": _o_pendiente(_num(lead.get("rating"))),
            "resenas": _o_pendiente(_num(lead.get("reviews_count"))),
            "resenas_90_dias": PENDIENTE,
            "pct_respondidas": PENDIENTE,
        },
        "competidores": [
            {
                "nombre": c.get("name") or PENDIENTE,
                "posicion_mapa": _o_pendiente(_num(c.get("map_position"))),
                "resenas": _o_pendiente(_num(c.get("reviews_count"))),
                "calificacion": _o_pendiente(_num(c.get("rating"))),
            }
            for c in comps
        ] or PENDIENTE,
        "retencion": None,
        "observaciones": [],
    }
