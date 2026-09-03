"""Detector de datos verificables: plazos, fechas, montos y referencias normativas.

Opera sobre texto normalizado en nivel de lectura: espacios colapsados a uno,
palabras partidas por salto de línea ya reunidas. NO opera sobre el texto sin
espacios que se usa para el match de citas, porque el parser de cantidades
escritas necesita las palabras separadas.

Dos principios de diseño:

1. **Consume y enmascara.** El texto se recorre en orden de prioridad —fechas,
   cantidades temporales, referencias normativas, porcentajes, montos, años
   sueltos— y cada tramo reconocido se enmascara antes de la etapa siguiente.
   Sin esto, un mismo número se clasifica a la vez como plazo, monto y año: en
   "1.500 días" el separador de miles haría que se lea el plazo como 500 y que
   además aparezca un monto que nadie escribió.

2. **Una forma reconocible que no se resuelve emite centinela, no silencio.**
   Los centinelas empiezan con "?" y ninguna cita puede respaldarlos, así que
   fuerzan el rechazo de la afirmación. Es preferible rechazar un dato ambiguo
   a dejarlo pasar respaldado por otra cosa: si una fecha con formato no
   soportado se degradara a su año suelto, cualquier mención de ese año la
   respaldaría.
"""
import datetime
import re
import unicodedata

MARCA_IRRESOLUBLE = "?"
CANTIDAD_IRRESOLUBLE = MARCA_IRRESOLUBLE
FECHA_IRRESOLUBLE = MARCA_IRRESOLUBLE + "fecha"
RANGO_MAXIMO = 9999
_MAX_TOKENS_CANTIDAD = 12


def _sin_tildes(palabra):
    descompuesta = unicodedata.normalize("NFD", palabra)
    return "".join(c for c in descompuesta if unicodedata.category(c) != "Mn")


def _plegar(mapa):
    """Indexa un mapa por su forma sin tildes.

    Los PDF del SII y el texto tecleado a mano llegan con y sin acentos
    ("veintiun", "veintiún"), y una palabra de cantidad que no se reconoce no
    produce ni literal ni centinela: pasa en silencio. Plegar el vocabulario
    cierra esa clase completa en vez de parchar una entrada a la vez.
    """
    return {_sin_tildes(clave): valor for clave, valor in mapa.items()}


_PALABRAS_0_29 = _plegar({
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciséis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiún": 21, "veintiuno": 21, "veintiuna": 21,
    "veintidós": 22, "veintitrés": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiséis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
})
_DECENAS = _plegar({"treinta": 30, "cuarenta": 40, "cincuenta": 50,
                    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90})
_CENTENAS = _plegar({"cien": 100, "ciento": 100, "doscientos": 200,
                     "trescientos": 300, "cuatrocientos": 400, "quinientos": 500,
                     "seiscientos": 600, "setecientos": 700, "ochocientos": 800,
                     "novecientos": 900})

VOCABULARIO = set(_PALABRAS_0_29) | set(_DECENAS) | set(_CENTENAS) | {"y", "mil"}
# "o" y "a" separan cantidades alternativas ("treinta o sesenta días"); no son
# parte de un número, así que no entran al vocabulario del parser.
CONECTORES = {"o", "a"}

_UNIDADES_TEMPORALES = _plegar({
    "día": "d", "días": "d", "mes": "m", "meses": "m", "año": "a", "años": "a",
})
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
          "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
          "octubre": 10, "noviembre": 11, "diciembre": 12}

# Un número puede venir con separador de miles: se toma como un solo token.
_RE_TOKEN = re.compile(r"\d{1,3}(?:\.\d{3})+|\d+|[a-záéíóúñü]+")
_SUFIJOS_DE_ARTICULO = r"bis|ter|qu[áa]ter"

_RE_FECHA_ISO = re.compile(r"\b((?:19|20)\d{2})[/.\-](\d{1,2})[/.\-](\d{1,2})\b")
_RE_FECHA_NUMERICA = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-]((?:19|20)\d{2})\b")
_RE_FECHA_TEXTO = re.compile(
    r"\b(\d{1,2})\s*[°º]?\s+de\s+([a-záéíóúñ]+)\s+del?\s+((?:19|20)\d{2})\b")

_RE_ARTICULO = re.compile(
    r"\b(?:art|arts|art[íi]culos?)\.?\s*"
    r"(\d+(?:\s*(?:" + _SUFIJOS_DE_ARTICULO + r"))?"
    r"(?:\s*(?:y|,)\s*\d+(?:\s*(?:" + _SUFIJOS_DE_ARTICULO + r"))?)*)")
_RE_NUMERO_DE_ARTICULO = re.compile(
    r"(\d+)(?:\s*(" + _SUFIJOS_DE_ARTICULO + r"))?")
_RE_NORMA = re.compile(
    r"\b(decreto\s+ley|d\.?\s*l\.?|ley|circular|resoluci[óo]n)\s*"
    r"(?:exenta\s*)?(?:sii\s*)?(?:n[.°º]*\s*)?(\d{1,3}(?:\.\d{3})+|\d+)\b")
_PREFIJO_DE_NORMA = {"decreto ley": "dl", "dl": "dl", "d.l.": "dl", "d.l": "dl",
                     "dl.": "dl", "ley": "ley", "circular": "circular",
                     "resolucion": "resolucion", "resolución": "resolucion"}

_RE_PORCENTAJE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?\s*%")
_RE_UNIDAD_REAJUSTABLE = re.compile(
    r"\b(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?\s*(utm|uta|uf)\b")
_RE_MONTO = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})*|\d+)|\b(\d{1,3}(?:\.\d{3})+)\b")
_RE_ANIO = re.compile(r"\b(?:19|20)\d{2}\b")


def _a_entero(digitos):
    return int(digitos.replace(".", ""))


def _parsear_grupo(tokens):
    """Resuelve 0-999. Devuelve (valor, tokens_consumidos) o (None, 0)."""
    total, i, visto = 0, 0, False
    if i < len(tokens) and tokens[i] in _CENTENAS:
        # "cien" no admite nada a su derecha y "ciento" exige algo: "cien uno"
        # y "ciento" a secas no son español, y aceptarlos contradice que el
        # parser rechace lo que no puede resolver.
        cola = len(tokens) - 1
        if tokens[i] == "cien" and cola > 0:
            return None, 0
        if tokens[i] == "ciento" and cola == 0:
            return None, 0
        total += _CENTENAS[tokens[i]]; i += 1; visto = True
    if i < len(tokens) and tokens[i] in _DECENAS:
        total += _DECENAS[tokens[i]]; i += 1; visto = True
        if (i + 1 < len(tokens) and tokens[i] == "y"
                and _PALABRAS_0_29.get(tokens[i + 1], 99) < 10):
            total += _PALABRAS_0_29[tokens[i + 1]]; i += 2
    elif i < len(tokens) and tokens[i] in _PALABRAS_0_29:
        total += _PALABRAS_0_29[tokens[i]]; i += 1; visto = True
    return (total, i) if visto else (None, 0)


def _parsear_sin_rango(tokens):
    tokens = [t for t in tokens if t]
    if not tokens:
        return None
    if "mil" in tokens:
        corte = tokens.index("mil")
        izquierda, derecha = tokens[:corte], tokens[corte + 1:]
        multiplicador = 1
        if izquierda:
            if izquierda == ["un"]:
                return None  # "un mil" no es español; "mil" va solo
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


def parsear_cardinal(tokens):
    """Resuelve una secuencia de palabras a un entero 0-9999, o None.

    Fuera de ese rango devuelve None en vez de un valor a medias: el contrato
    declara 0-9999 y resolver "diez mil" contradiría lo que promete el parser.
    """
    tokens = [_sin_tildes(t) for t in tokens if t]
    valor = _parsear_sin_rango(tokens)
    return valor if valor is not None and 0 <= valor <= RANGO_MAXIMO else None


def _enmascarar(texto, tramos):
    """Reemplaza los tramos por espacios, preservando los offsets del resto."""
    for inicio, fin in sorted(tramos, reverse=True):
        texto = texto[:inicio] + " " * (fin - inicio) + texto[fin:]
    return texto


def _token_de_fecha(anio, mes, dia):
    try:
        fecha = datetime.date(int(anio), int(mes), int(dia))
    except ValueError:
        return FECHA_IRRESOLUBLE
    return f"fecha:{fecha.year:04d}-{fecha.month:02d}-{fecha.day:02d}"


def _consumir_fechas(texto):
    """Fechas completas como un token único, y el texto con sus tramos borrados.

    La fecha es atómica a propósito: emitir día, mes y año por separado dejaría
    que una cita con esos tres valores en contextos distintos respalde una fecha
    que no aparece en ninguna parte. Y una forma con pinta de fecha que no se
    resuelve emite centinela en vez de dejar suelto su año, porque el año suelto
    lo respaldaría cualquier mención del mismo año.
    """
    tokens, tramos = set(), []
    for encontrado in _RE_FECHA_ISO.finditer(texto):
        anio, mes, dia = encontrado.groups()
        tokens.add(_token_de_fecha(anio, mes, dia)); tramos.append(encontrado.span())
    texto = _enmascarar(texto, tramos); tramos = []
    for encontrado in _RE_FECHA_NUMERICA.finditer(texto):
        dia, mes, anio = encontrado.groups()
        tokens.add(_token_de_fecha(anio, mes, dia)); tramos.append(encontrado.span())
    texto = _enmascarar(texto, tramos); tramos = []
    for encontrado in _RE_FECHA_TEXTO.finditer(texto):
        dia, mes, anio = encontrado.groups()
        numero_de_mes = _MESES.get(_sin_tildes(mes))
        tokens.add(_token_de_fecha(anio, numero_de_mes, dia)
                   if numero_de_mes else FECHA_IRRESOLUBLE)
        tramos.append(encontrado.span())
    return tokens, _enmascarar(texto, tramos)


def _segmentar_cantidades(corrida):
    """Parte la corrida en cantidades alternativas y resuelve cada una.

    Devuelve la lista de enteros, o None si alguna no se resuelve. "cuarenta y
    cinco" es una sola cantidad; "treinta o sesenta" son dos, y quedarse solo
    con la más cercana a la unidad haría pasar un plazo que la cita no dice.
    """
    segmentos, actual = [], []
    for token in corrida:
        if token in CONECTORES:
            if actual:
                segmentos.append(actual); actual = []
        else:
            actual.append(token)
    if actual:
        segmentos.append(actual)
    if not segmentos:
        return None

    valores = []
    for segmento in segmentos:
        digitos = [t for t in segmento if t[0].isdigit()]
        palabras = [t for t in segmento if not t[0].isdigit()]
        if len(digitos) > 1:
            return None  # dos cifras sin conector que las separe: ambiguo
        en_cifras = _a_entero(digitos[0]) if digitos else None
        en_palabras = parsear_cardinal(palabras) if palabras else None
        if en_cifras is not None and en_palabras is not None:
            # La normativa escribe la forma mixta "noventa (90) días". Si las dos
            # formas no coinciden el texto se contradice, y eso no se resuelve.
            if en_cifras != en_palabras:
                return None
            valores.append(en_cifras)
        elif en_cifras is not None:
            valores.append(en_cifras)
        elif en_palabras is not None:
            valores.append(en_palabras)
        else:
            return None
    return valores


def _consumir_cantidades_temporales(texto):
    """Cantidades con unidad temporal, en cifras o en palabras."""
    tokens = [(m.group(0), m.start(), m.end()) for m in _RE_TOKEN.finditer(texto)]
    encontrados, tramos = set(), []
    for i, (palabra, _, fin_unidad) in enumerate(tokens):
        sufijo = _UNIDADES_TEMPORALES.get(_sin_tildes(palabra))
        if sufijo is None:
            continue
        corrida, inicio_corrida, j = [], None, i - 1
        while j >= 0 and len(corrida) < _MAX_TOKENS_CANTIDAD:
            candidato = _sin_tildes(tokens[j][0])
            if not (candidato[0].isdigit() or candidato in VOCABULARIO
                    or candidato in CONECTORES):
                break
            corrida.insert(0, candidato); inicio_corrida = tokens[j][1]; j -= 1
        while corrida and corrida[0] in CONECTORES:
            corrida.pop(0)
        if not corrida:
            continue
        valores = _segmentar_cantidades(corrida)
        if valores is None:
            encontrados.add(MARCA_IRRESOLUBLE + sufijo)
        else:
            encontrados.update(f"{valor}{sufijo}" for valor in valores)
        tramos.append((inicio_corrida, fin_unidad))
    return encontrados, _enmascarar(texto, tramos)


def _consumir_referencias(texto):
    """Artículos —incluidas enumeraciones— y normas con número."""
    encontrados, tramos = set(), []
    for encontrado in _RE_ARTICULO.finditer(texto):
        for numero, sufijo in _RE_NUMERO_DE_ARTICULO.findall(encontrado.group(1)):
            encontrados.add("art" + numero + (_sin_tildes(sufijo) if sufijo else ""))
        tramos.append(encontrado.span())
    texto = _enmascarar(texto, tramos); tramos = []
    for encontrado in _RE_NORMA.finditer(texto):
        prefijo = re.sub(r"\s+", " ", encontrado.group(1)).strip()
        clave = _PREFIJO_DE_NORMA.get(_sin_tildes(prefijo).replace(" .", "."))
        if clave:
            encontrados.add(clave + encontrado.group(2).replace(".", ""))
        tramos.append(encontrado.span())
    return encontrados, _enmascarar(texto, tramos)


def _consumir_porcentajes(texto):
    encontrados, tramos = set(), []
    for encontrado in _RE_PORCENTAJE.finditer(texto):
        entero, decimal = encontrado.groups()
        # Los ceros finales se recortan del decimal, nunca del entero: hacerlo
        # del entero convertiría 10% en 1% y 100% en 1%.
        valor = str(_a_entero(entero))
        if decimal and decimal.rstrip("0"):
            valor += "." + decimal.rstrip("0")
        encontrados.add(valor + "pct")
        tramos.append(encontrado.span())
    return encontrados, _enmascarar(texto, tramos)


def _consumir_montos(texto):
    """Montos en pesos y en unidades reajustables.

    Las multas de las circulares se expresan casi siempre en UTM o UTA con
    cifras de pocos dígitos, así que exigir separador de miles dejaría la regla
    inerte justo para la forma dominante.
    """
    encontrados, tramos = set(), []
    for encontrado in _RE_UNIDAD_REAJUSTABLE.finditer(texto):
        entero, decimal, unidad = encontrado.groups()
        valor = str(_a_entero(entero))
        if decimal and decimal.rstrip("0"):
            valor += "." + decimal.rstrip("0")
        encontrados.add(valor + unidad)
        tramos.append(encontrado.span())
    texto = _enmascarar(texto, tramos); tramos = []
    for encontrado in _RE_MONTO.finditer(texto):
        digitos = encontrado.group(1) or encontrado.group(2)
        encontrados.add(str(_a_entero(digitos)) + "clp")
        tramos.append(encontrado.span())
    return encontrados, _enmascarar(texto, tramos)


def extraer(texto):
    """Tokens canónicos de los datos verificables presentes en `texto`."""
    restante = texto.lower()
    encontrados = set()
    for consumir in (_consumir_fechas, _consumir_cantidades_temporales,
                     _consumir_referencias, _consumir_porcentajes,
                     _consumir_montos):
        nuevos, restante = consumir(restante)
        encontrados |= nuevos
    encontrados.update(_RE_ANIO.findall(restante))
    return encontrados
