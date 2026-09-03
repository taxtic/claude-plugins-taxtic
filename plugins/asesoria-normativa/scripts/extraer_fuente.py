"""Extracción determinista del documento normativo a fuente.json.

Escribe el texto por página y sus dos normalizaciones. Ningún valor de este
archivo lo teclea el modelo: es la fuente de verdad contra la que se verifican
las citas, y editarlo a mano invalida esa verificación.
"""
import re

_COMILLAS = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"}
_GUIONES = {"\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-"}
_RE_CORTE_DE_LINEA = re.compile(r"(?<=[^\W\d_])-\s*\n\s*(?=[^\W\d_])")
_RE_ESPACIOS = re.compile(r"\s+")


def normalizar_lectura(texto):
    """N1: para leer y para detectar cantidades. Conserva un espacio entre palabras."""
    for original, reemplazo in {**_COMILLAS, **_GUIONES}.items():
        texto = texto.replace(original, reemplazo)
    # une la palabra que el maquetado partió al final del renglón
    texto = _RE_CORTE_DE_LINEA.sub("", texto)
    texto = _RE_ESPACIOS.sub(" ", texto)
    return texto.strip().casefold()


def normalizar_matching(texto):
    """N2: para comparar citas. Sin espacios y sin guiones.

    Se eliminan todos los guiones, no solo los que cortan renglón: la fuente
    puede traer "jurídico-\\ntributario" y la cita "jurídico-tributario", y sin
    esto los dos lados no convergen.
    """
    texto = normalizar_lectura(texto)
    return texto.replace(" ", "").replace("-", "")


# El año NO está acá: no se detecta ni se pide, se deriva de fecha_documento.
# Así el estado "fecha de 2025 con año 2026" no es representable, en vez de
# depender de una validación de consistencia posterior.
CAMPOS_DE_IDENTIDAD = ("tipo", "numero", "fecha_documento")

_MESES_A_NUMERO = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_NOMBRES_DE_MES = (None, "enero", "febrero", "marzo", "abril", "mayo", "junio",
                   "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
TIPOS_VALIDOS = ("circular", "resolucion", "oficio")

_PATRONES_DE_TIPO = (
    ("resolucion", re.compile(r"resoluci[óo]n\s+exenta(?:\s+sii)?\s*n[°º]?\s*(\d+)", re.I)),
    ("oficio", re.compile(r"oficio\s*(?:ordinario\s*)?n[°º]?\s*(\d+)", re.I)),
    ("circular", re.compile(r"circular\s*n[°º]?\s*(\d+)", re.I)),
)
_RE_FECHA_EN_BLOQUE = re.compile(
    r"fecha\s*:?\s*(\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+(?:19|20)\d{2})", re.I)
_RE_FECHA_PALABRAS = re.compile(
    r"^\s*(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+((?:19|20)\d{2})\s*$", re.I)
_RE_FECHA_NUMERICA = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})\s*$")
_RE_NUMERO = re.compile(r"^\d{1,6}$")
_RE_MATERIA = re.compile(r"materia\s*:?\s*(.+?)(?:\n\s*\n|\Z)", re.I | re.S)


class IdentidadIncompleta(Exception):
    """Falta un campo de identidad y el usuario no lo aportó."""


def parsear_fecha(texto):
    """Única puerta de entrada de una fecha, venga del PDF o del usuario.

    Devuelve la forma canónica "31 de agosto de 2026", o None si el formato no
    se reconoce o la fecha no existe en el calendario. Que el PDF y el usuario
    pasen por la misma función es lo que impide que un string arbitrario llegue
    a fuente.json y que derivar_anio() le saque un año de adentro.
    """
    import datetime
    if not isinstance(texto, str):
        return None
    encontrado = _RE_FECHA_PALABRAS.match(texto)
    if encontrado:
        dia, mes, anio = encontrado.groups()
        numero_de_mes = _MESES_A_NUMERO.get(mes.lower())
    else:
        encontrado = _RE_FECHA_NUMERICA.match(texto)
        if not encontrado:
            return None
        dia, numero_de_mes, anio = encontrado.groups()
        numero_de_mes = int(numero_de_mes)
    if not numero_de_mes:
        return None
    try:
        fecha = datetime.date(int(anio), numero_de_mes, int(dia))
    except ValueError:
        return None  # 31 de febrero y compañía
    return f"{fecha.day} de {_NOMBRES_DE_MES[fecha.month]} de {fecha.year}"


def _validar_numero(valor):
    return valor if isinstance(valor, str) and _RE_NUMERO.match(valor) else None


def _validar_tipo(valor):
    return valor if valor in TIPOS_VALIDOS else None


# Cada campo de identidad aportable pasa por su validador antes de entrar.
_VALIDADORES = {"tipo": _validar_tipo, "numero": _validar_numero,
                "fecha_documento": parsear_fecha}
_FORMATOS_ESPERADOS = {
    "tipo": " | ".join(TIPOS_VALIDOS),
    "numero": "solo dígitos, por ejemplo 35",
    "fecha_documento": '"31 de agosto de 2026" o "31/08/2026"',
}


def detectar_identidad(texto_pagina_1):
    """Detecta tipo, número, fecha, año y materia escaneando la página completa.

    El bloque identificatorio del SII vive en un recuadro lateral y la extracción
    lo emite al final del texto de la página, después del cuerpo: por eso se
    escanea todo y no solo el encabezado.
    """
    identidad = {"tipo": None, "numero": None, "fecha_documento": None, "materia": None}

    for tipo, patron in _PATRONES_DE_TIPO:
        encontrado = patron.search(texto_pagina_1)
        if encontrado:
            identidad["tipo"] = tipo
            identidad["numero"] = encontrado.group(1)
            break

    fecha = _RE_FECHA_EN_BLOQUE.search(texto_pagina_1)
    if fecha:
        # misma validación que para la fecha aportada por el usuario
        identidad["fecha_documento"] = parsear_fecha(fecha.group(1))

    materia = _RE_MATERIA.search(texto_pagina_1)
    if materia:
        identidad["materia"] = _RE_ESPACIOS.sub(" ", materia.group(1)).strip()

    return identidad


def derivar_anio(fecha_documento):
    """Única fuente del año. No hay otra vía para obtenerlo."""
    if not fecha_documento:
        return None
    encontrado = re.search(r"\b((?:19|20)\d{2})\b", fecha_documento)
    return int(encontrado.group(1)) if encontrado else None


def completar_identidad(identidad, aportado_por_usuario):
    """Rellena los campos ausentes con lo que aportó el contador, marcándolos."""
    if "anio" in aportado_por_usuario:
        raise ValueError(
            "'anio' no se aporta: se deriva de 'fecha_documento'. Pasa la fecha.")
    completada = dict(identidad)
    origen = {campo: "detectado" for campo in CAMPOS_DE_IDENTIDAD
              if identidad.get(campo) is not None}
    for campo, valor in aportado_por_usuario.items():
        if campo not in CAMPOS_DE_IDENTIDAD:
            raise ValueError(f"'{campo}' no es un campo de identidad aportable")
        canonico = _VALIDADORES[campo](valor)
        if canonico is None:
            raise ValueError(
                f"'{campo}' inválido: {valor!r}. Formato esperado: "
                f"{_FORMATOS_ESPERADOS[campo]}")
        if completada.get(campo) is None:
            completada[campo] = canonico
            origen[campo] = "usuario"
    completada["_origen"] = origen
    return completada


def exigir_identidad_completa(identidad):
    """Aborta si falta cualquier campo de identidad. No se adivina ninguno."""
    faltantes = [c for c in CAMPOS_DE_IDENTIDAD if identidad.get(c) is None]
    if faltantes:
        raise IdentidadIncompleta(
            "faltan campos de identidad y no se infieren del reloj, del nombre "
            "del archivo ni de la URL: " + ", ".join(faltantes))
    return identidad


def construir_fuente(paginas, origen, identidad):
    """Arma el diccionario que se serializa como fuente.json."""
    origen_de_campos = dict(identidad.get("_origen") or {
        campo: "detectado" for campo in CAMPOS_DE_IDENTIDAD
        if identidad.get(campo) is not None
    })
    origen_de_campos["anio"] = "derivado"
    completo = "\n".join(paginas)
    return {
        "tipo": identidad.get("tipo"),
        "numero": identidad.get("numero"),
        # siempre derivado, nunca leído de la identidad
        "anio": derivar_anio(identidad.get("fecha_documento")),
        "fecha_documento": identidad.get("fecha_documento"),
        "materia": identidad.get("materia"),
        "origen": origen,
        "procedencia_campos": origen_de_campos,
        "metricas": {"paginas": len(paginas), "caracteres": len(completo)},
        "paginas": [{"n": i, "texto": t} for i, t in enumerate(paginas, 1)],
        "texto_normalizado": normalizar_matching(completo),
        "paginas_normalizadas": [
            {"n": i, "texto": normalizar_matching(t)} for i, t in enumerate(paginas, 1)
        ],
    }
