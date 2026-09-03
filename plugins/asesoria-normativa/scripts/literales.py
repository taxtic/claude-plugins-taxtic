"""Detector de datos verificables (plazos, montos, referencias normativas, fechas).

Opera sobre texto normalizado en nivel de lectura: espacios colapsados a uno,
palabras partidas por salto de línea ya reunidas. NO opera sobre el texto sin
espacios que se usa para el match de citas: el parser de cantidades escritas
necesita las palabras separadas.
"""
import re

_PALABRAS_0_29 = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintiún": 21,
    "veintiuna": 21, "veintidos": 22, "veintidós": 22, "veintitres": 23,
    "veintitrés": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintiséis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
_DECENAS = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
            "setenta": 70, "ochenta": 80, "noventa": 90}
_CENTENAS = {"cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
             "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
             "setecientos": 700, "ochocientos": 800, "novecientos": 900}

VOCABULARIO = set(_PALABRAS_0_29) | set(_DECENAS) | set(_CENTENAS) | {"y", "mil"}


def _parsear_grupo(tokens):
    """Resuelve 0-999. Devuelve (valor, tokens_consumidos) o (None, 0)."""
    total, i, visto = 0, 0, False
    if i < len(tokens) and tokens[i] in _CENTENAS:
        total += _CENTENAS[tokens[i]]; i += 1; visto = True
    if i < len(tokens) and tokens[i] in _DECENAS:
        total += _DECENAS[tokens[i]]; i += 1; visto = True
        if (i + 1 < len(tokens) and tokens[i] == "y"
                and _PALABRAS_0_29.get(tokens[i + 1], 99) < 10):
            total += _PALABRAS_0_29[tokens[i + 1]]; i += 2
    elif i < len(tokens) and tokens[i] in _PALABRAS_0_29:
        total += _PALABRAS_0_29[tokens[i]]; i += 1; visto = True
    return (total, i) if visto else (None, 0)


RANGO_MAXIMO = 9999


def parsear_cardinal(tokens):
    """Resuelve una secuencia de palabras a un entero 0-9999, o None.

    Fuera de ese rango devuelve None en vez de un valor a medias: el contrato
    declara 0-9999 y resolver "diez mil" contradiría lo que promete el parser.
    """
    valor = _parsear_sin_rango(tokens)
    return valor if valor is not None and 0 <= valor <= RANGO_MAXIMO else None


def _parsear_sin_rango(tokens):
    tokens = [t for t in tokens if t]
    if not tokens:
        return None
    if "mil" in tokens:
        corte = tokens.index("mil")
        izquierda, derecha = tokens[:corte], tokens[corte + 1:]
        multiplicador = 1
        if izquierda:
            multiplicador, consumidos = _parsear_grupo(izquierda)
            if multiplicador is None or consumidos != len(izquierda):
                return None
        total = multiplicador * 1000
        if derecha:
            resto, consumidos = _parsear_grupo(derecha)
            if resto is None or consumidos != len(derecha):
                return None
            total += resto
        return total
    valor, consumidos = _parsear_grupo(tokens)
    return valor if valor is not None and consumidos == len(tokens) else None


_UNIDADES_TEMPORALES = {
    "día": "d", "dias": "d", "días": "d", "dia": "d",
    "mes": "m", "meses": "m",
    "año": "a", "años": "a", "ano": "a", "anos": "a",
}
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}

_RE_TOKEN = re.compile(r"[0-9]+|[a-záéíóúñü]+", re.IGNORECASE)
_RE_ARTICULO = re.compile(
    r"\b(?:art|arts|artículos?|articulos?)\.?\s*(\d+)\s*(bis|ter|quáter|quater)?\b")
_RE_NORMA = re.compile(
    r"\b(ley|dl|d\.l\.|circular|resolución|resolucion)\s*(?:exenta\s*)?"
    r"(?:n[°º]?\s*)?(\d+(?:\.\d{3})*)\b")
_RE_PORCENTAJE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%")
_RE_MONTO = re.compile(r"\$?\s*(\d{1,3}(?:\.\d{3})+)\b")
_RE_ANIO = re.compile(r"\b(?:19|20)\d{2}\b")
_RE_FECHA_EN_PALABRAS = re.compile(
    r"\b(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+((?:19|20)\d{2})\b")
_RE_FECHA_NUMERICA = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})\b")

# "nueve mil novecientos noventa y nueve" son seis tokens; la ventana los cubre
# con margen, en línea con el rango 0-9999 que resuelve el parser.
_MAX_TOKENS_CANTIDAD = 8
CANTIDAD_IRRESOLUBLE = "?"


def _cantidad_previa(tokens, indice):
    """Resuelve la cantidad que antecede a la unidad temporal en `indice`.

    Devuelve el entero, o CANTIDAD_IRRESOLUBLE si había palabras de cantidad que
    no forman un número válido, o None si sencillamente no había cantidad.

    Un dígito inmediatamente anterior gana sobre las palabras: la normativa
    escribe formas mixtas como "noventa (90) días", y el dígito es el dato.
    """
    if indice == 0:
        return None
    if tokens[indice - 1].isdigit():
        return int(tokens[indice - 1])
    palabras, i = [], indice - 1
    while i >= 0 and len(palabras) < _MAX_TOKENS_CANTIDAD and tokens[i] in VOCABULARIO:
        palabras.insert(0, tokens[i]); i -= 1
    while palabras and palabras[0] == "y":
        palabras.pop(0)
    if not palabras:
        return None
    valor = parsear_cardinal(palabras)
    # Falla cerrado: si parecía una cantidad y no se pudo resolver, se emite un
    # token que ninguna cita puede respaldar, en vez de callar el dato.
    return valor if valor is not None else CANTIDAD_IRRESOLUBLE


def _canonizar_porcentaje(valor):
    """Normaliza la coma decimal y recorta ceros SOLO de la parte decimal.

    Recortarlos de la parte entera convertiría 10% en 1% y 100% en 1%.
    """
    valor = valor.replace(",", ".")
    if "." not in valor:
        return valor
    entero, decimal = valor.split(".", 1)
    decimal = decimal.rstrip("0")
    return f"{entero}.{decimal}" if decimal else entero


def _extraer_fechas(bajo):
    """Fechas completas como un solo token, y los tramos que ocupan en el texto.

    La fecha es atómica a propósito: emitir día, mes y año por separado dejaría
    que una cita con esos tres valores en contextos distintos respaldara una
    fecha que no aparece en ninguna parte.
    """
    tokens, tramos = set(), []
    for encontrado in _RE_FECHA_EN_PALABRAS.finditer(bajo):
        dia, mes, anio = encontrado.groups()
        if mes in _MESES:
            tokens.add(f"fecha:{anio}-{_MESES[mes]:02d}-{int(dia):02d}")
            tramos.append(encontrado.span())
    for encontrado in _RE_FECHA_NUMERICA.finditer(bajo):
        dia, mes, anio = encontrado.groups()
        if 1 <= int(mes) <= 12:
            tokens.add(f"fecha:{anio}-{int(mes):02d}-{int(dia):02d}")
            tramos.append(encontrado.span())
    return tokens, tramos


def extraer(texto):
    """Tokens canónicos de los datos verificables presentes en `texto`."""
    bajo = texto.lower()
    encontrados, tramos_de_fecha = _extraer_fechas(bajo)

    # el texto sin las fechas ya consumidas: evita emitir su año como dato suelto
    sin_fechas = bajo
    for inicio, fin in sorted(tramos_de_fecha, reverse=True):
        sin_fechas = sin_fechas[:inicio] + " " * (fin - inicio) + sin_fechas[fin:]

    for numero, sufijo in _RE_ARTICULO.findall(bajo):
        encontrados.add("art" + numero + (sufijo.replace("á", "a") if sufijo else ""))
    for norma, numero in _RE_NORMA.findall(bajo):
        clave = {"d.l.": "dl", "resolución": "resolucion"}.get(norma, norma)
        encontrados.add(clave + numero.replace(".", ""))
    for valor in _RE_PORCENTAJE.findall(bajo):
        encontrados.add(_canonizar_porcentaje(valor) + "pct")
    for monto in _RE_MONTO.findall(bajo):
        encontrados.add(monto.replace(".", "") + "clp")
    for anio in _RE_ANIO.findall(sin_fechas):
        encontrados.add(anio)

    tokens = _RE_TOKEN.findall(sin_fechas)
    for i, token in enumerate(tokens):
        if token in _UNIDADES_TEMPORALES:
            valor = _cantidad_previa(tokens, i)
            if valor is not None:
                encontrados.add(f"{valor}{_UNIDADES_TEMPORALES[token]}")
    return encontrados
