"""Catálogo cerrado de secciones, perfiles por tipo de documento y rótulos.

Los títulos de sección y los subtítulos salen de acá y no del modelo: es lo que
hace que ese texto tenga procedencia garantizada y no necesite respaldo de cita.
"""

SECCIONES = {
    "deroga": {"bloques": ("parrafo", "lista"),
               "titulo": {"circular": "Qué reemplaza esta circular",
                          "resolucion": "Normativa que reemplaza",
                          "oficio": "Normativa que reemplaza"}},
    "tema": {"bloques": ("parrafo",), "titulo": "Tema central"},
    "alcance": {"bloques": ("parrafo", "lista"), "titulo": "A quién aplica"},
    "comparacion": {"bloques": ("tabla", "nota"), "titulo": "Cuadro comparativo"},
    "materia": {"bloques": ("subtitulo", "parrafo", "lista", "tabla", "callout"),
                "titulo": None},
    "reglas_comunes": {"bloques": ("lista",), "titulo": "Reglas comunes relevantes"},
    "novedades": {"bloques": ("lista", "callout"),
                  "titulo": "Qué cambia respecto de lo anterior"},
    "plazos": {"bloques": ("tabla",), "titulo": "Plazos clave"},
    "procedimiento": {"bloques": ("lista", "tabla"), "titulo": "Cómo se cumple"},
    "caso_consultado": {"bloques": ("parrafo",),
                        "titulo": "Caso consultado y criterio del SII"},
    "vigencia": {"bloques": ("parrafo",), "titulo": "Vigencia"},
    "sanciones": {"bloques": ("parrafo", "lista"), "titulo": "Sanciones e infracciones"},
    "gestiones": {"bloques": ("lista",), "titulo": "Gestiones a considerar"},
    "a_verificar": {"bloques": ("lista",), "titulo": "Puntos a confirmar"},
    "otra": {"bloques": ("parrafo", "lista"), "titulo": "Otras materias"},
}

# El orden de emisión lo fija el perfil; el modelo elige qué secciones usar, no
# en qué orden van. gestiones y a_verificar cierran siempre, en ese orden.
_ORDEN_BASE = ("deroga", "tema", "alcance", "comparacion", "materia",
               "caso_consultado", "procedimiento", "reglas_comunes", "novedades",
               "plazos", "sanciones", "vigencia", "otra", "gestiones", "a_verificar")

PERFILES = {
    "circular": {
        "obligatorias": ("tema", "gestiones", "a_verificar"),
        "sugeridas": ("deroga", "alcance", "materia", "comparacion",
                      "reglas_comunes", "novedades", "vigencia", "plazos",
                      "sanciones", "otra"),
        "prohibidas": ("caso_consultado", "procedimiento"),
    },
    "resolucion": {
        "obligatorias": ("tema", "alcance", "procedimiento", "vigencia",
                         "gestiones", "a_verificar"),
        "sugeridas": ("plazos", "sanciones", "deroga", "novedades", "materia",
                      "comparacion", "reglas_comunes", "otra"),
        "prohibidas": ("caso_consultado",),
    },
    "oficio": {
        "obligatorias": ("caso_consultado", "tema", "gestiones", "a_verificar"),
        "sugeridas": ("alcance", "novedades", "materia", "otra"),
        "prohibidas": ("deroga", "procedimiento", "reglas_comunes"),
    },
}

SUBTITULOS = {
    "ambito": "Ámbito de aplicación",
    "procedimiento": "Procedimiento",
    "requisitos": "Requisitos",
    "admisibilidad": "Admisibilidad",
    "oportunidad": "Oportunidad y límites",
    "plazos": "Plazos",
    "resolucion": "Resolución",
    "silencio": "Resolución y silencio administrativo",
    "prueba": "Prueba",
    "efectos": "Efectos",
    "limitaciones": "Limitaciones",
    "recursos": "Recursos posteriores",
    "ejemplos": "Ejemplos",
}

VARIANTES_DE_CALLOUT = ("novedad", "critico", "proteccion")
SECCIONES_CON_DERIVADA = ("gestiones", "a_verificar")


def titulo_de(id_seccion, tipo):
    """Título de catálogo. Devuelve None para `materia`, cuyo título es libre y citado."""
    titulo = SECCIONES[id_seccion]["titulo"]
    return titulo.get(tipo) if isinstance(titulo, dict) else titulo


def bloques_permitidos(id_seccion):
    return SECCIONES[id_seccion]["bloques"]


def orden_de_emision(tipo):
    perfil = PERFILES[tipo]
    admitidas = set(perfil["obligatorias"]) | set(perfil["sugeridas"])
    return tuple(s for s in _ORDEN_BASE if s in admitidas)
