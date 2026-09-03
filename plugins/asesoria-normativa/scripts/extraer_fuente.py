"""Extracción determinista del documento normativo a fuente.json.

Escribe el texto por página y sus dos normalizaciones. Ningún valor de este
archivo lo teclea el modelo: es la fuente de verdad contra la que se verifican
las citas, y editarlo a mano invalida esa verificación.
"""
import re
import unicodedata

_COMILLAS = {"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
             "\u00ab": '"', "\u00bb": '"', "\u2039": "'", "\u203a": "'",
             "\u201e": '"', "\u201f": '"', "\u2032": "'", "\u2033": '"'}
_GUIONES = {"\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-",
            "\u2212": "-", "\u00ad": "-", "\uff0d": "-", "\u2043": "-"}
# El ordinal masculino y el signo de grado conviven en un mismo documento:
# "Circular N\u00ba 35" junto a "art\u00edculo 6\u00b0".
_ORDINALES = {"\u00ba": "\u00b0"}
_CARACTERES_DE_COMILLA = ('"', "'", "`")
# El corte de maquetado es un guion de division pegado al salto de línea.
# Solo cuentan los guiones que parten palabras: la raya y el semiraya son
# puntuacion, y unir a traves de ellas pega dos palabras distintas y hace
# desaparecer la segunda para el detector de datos. Aceptar espacio
# arbitrario a ambos lados ademas empalmaria a traves de un quiebre de
# parrafo, que no es un corte de palabra sino dos frases.
_RE_CORTE_DE_LINEA = re.compile(
    r"(?<=[^\W\d_])[-\u2010\u2011\u00ad][ \t]*\n[ \t]*(?=[^\W\d_])")
_RE_ESPACIOS = re.compile(r"\s+")
# Un guion con cifras a ambos lados separa cantidades y se conserva; el resto
# es maquetado o puntuación y se elimina para que los dos lados converjan.
_RE_GUION_ENTRE_LETRAS = re.compile(r"(?<!\d)-|-(?!\d)")


def normalizar_lectura(texto):
    """N1: para leer y para detectar cantidades. Conserva un espacio entre palabras."""
    # NFC primero: un mismo carácter acentuado puede venir precompuesto o
    # descompuesto según el PDF, y sin unificarlo ninguna cita con tilde de
    # ese documento haría match.
    texto = unicodedata.normalize("NFC", texto)
    for original, reemplazo in {**_COMILLAS, **_ORDINALES}.items():
        texto = texto.replace(original, reemplazo)
    # une la palabra que el maquetado partió al final del renglón; va antes de
    # unificar los guiones para no confundir una raya de puntuación con un corte
    texto = _RE_CORTE_DE_LINEA.sub("", texto)
    for original, reemplazo in _GUIONES.items():
        texto = texto.replace(original, reemplazo)
    texto = _RE_ESPACIOS.sub(" ", texto)
    return unicodedata.normalize("NFC", texto.strip().casefold())


def normalizar_matching(texto):
    """N2: para comparar citas. Sin espacios y sin guiones.

    Se eliminan todos los guiones, no solo los que cortan renglón: la fuente
    puede traer "jurídico-\\ntributario" y la cita "jurídico-tributario", y sin
    esto los dos lados no convergen.
    """
    texto = normalizar_lectura(texto)
    # El guion entre dos cifras NO se elimina: "30-60 UTM" y "3060 UTM" son
    # cantidades distintas, y borrarlo dejaba que una cita reescribiera un rango
    # de la fuente como un número único que el documento afirmaba después.
    texto = _RE_GUION_ENTRE_LETRAS.sub("", texto)
    for caracter in (" ", *_CARACTERES_DE_COMILLA):
        texto = texto.replace(caracter, "")
    return texto


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
    r"fecha\s*:\s*(\d{1,2}\s+de\s+[a-záéíóú]+\s+de\s+(?:19|20)\d{2})", re.I)
_RE_FECHA_PALABRAS = re.compile(
    r"^\s*(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+((?:19|20)\d{2})\s*$", re.I)
_RE_FECHA_NUMERICA = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})\s*$")
# El SII cierra el numero del recuadro con ".-".
_RE_CIERRE_IDENTIFICATORIO = re.compile(r"\s*\.\-")
_RE_NUMERO = re.compile(r"^\d{1,6}$")
# Los dos puntos son obligatorios: sin ellos engancha cualquier mención de
# la palabra en el cuerpo, y esa cadena termina siendo la bajada del documento.
# Corta en la línea en blanco o en la siguiente etiqueta del recuadro
# ("REF. LEGAL:"), que si no queda pegada a la bajada del documento. La etiqueta
# se compara con sensibilidad a mayúsculas: bajo re.I la clase [A-ZÁÉÍÓÚ]
# también acepta minúsculas y cortaría en cualquier frase con dos puntos.
_RE_MATERIA = re.compile(
    r"materia\s*:\s*(.+?)"
    r"(?:\n\s*\n|\n\s*(?-i:[A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚ\s.]{2,}:)|\Z)", re.I | re.S)


class IdentidadIncompleta(Exception):
    """Falta un campo de identidad y el usuario no lo aportó."""


def _elegir_identificatorio(texto_pagina_1):
    """Elige el tipo y número del recuadro identificatorio, no del cuerpo.

    La página cita normas anteriores antes de llegar al recuadro, y quedarse con
    la primera aparición fabrica una identidad completa y plausible a partir de
    una referencia ajena: una circular que menciona "Resolución Exenta SII N° 112"
    en su introducción se identificaría como esa resolución.

    La señal es que el SII cierra el número del recuadro con ".-", marca que una
    cita del cuerpo no lleva. **Solo cuentan los candidatos con esa marca.** Si
    ninguno la tiene se devuelve None y la skill le pregunta los datos al
    usuario: quedarse con una cita cualquiera del cuerpo produciría una
    identidad completa, plausible y falsa, que es peor que no detectar nada.
    """
    candidatos = [
        (encontrado.end(), tipo, encontrado.group(1))
        for tipo, patron in _PATRONES_DE_TIPO
        for encontrado in patron.finditer(texto_pagina_1)
        if _RE_CIERRE_IDENTIFICATORIO.match(texto_pagina_1, encontrado.end())
    ]
    if not candidatos:
        return None
    _, tipo, numero = max(candidatos, key=lambda c: c[0])
    return tipo, numero


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
    """Detecta tipo, número, fecha y materia escaneando la página completa.

    El bloque identificatorio del SII vive en un recuadro lateral y la extracción
    lo emite al final del texto de la página, después del cuerpo: por eso se
    escanea todo y no solo el encabezado.
    """
    identidad = {"tipo": None, "numero": None, "fecha_documento": None, "materia": None}

    elegido = _elegir_identificatorio(texto_pagina_1)
    if elegido:
        identidad["tipo"], identidad["numero"] = elegido

    # Se toma la última: el cuerpo suele citar fechas de normas anteriores
    # ("con fecha 15 de enero de 2018 este Servicio impartió...") y el recuadro
    # va después. Los dos puntos son obligatorios por la misma razón.
    fechas = list(_RE_FECHA_EN_BLOQUE.finditer(texto_pagina_1))
    if fechas:
        # misma validación que para la fecha aportada por el usuario
        identidad["fecha_documento"] = parsear_fecha(fechas[-1].group(1))

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
    """Incorpora lo que aportó el contador, marcando su procedencia.

    Lo que el usuario aporta **manda sobre lo detectado**. Si la detección se
    equivocó, corregirla es justamente para lo que existen los flags; descartar
    el valor del usuario en silencio dejaría el dato equivocado en el archivo y,
    peor, marcado como "detectado" — es decir, `procedencia_campos` afirmando
    que salió del documento.
    """
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


from urllib.parse import urlparse

DOMINIO_PERMITIDO = "sii.cl"
MAXIMO_DE_SALTOS = 3


class UrlRechazada(Exception):
    """La URL no cumple las guardas de esquema, dominio o tipo de contenido."""


class PdfSinTexto(Exception):
    """El PDF no trae capa de texto: probablemente es un escaneo."""


def _host_permitido(host):
    host = (host or "").lower().split(":")[0]
    return host == DOMINIO_PERMITIDO or host.endswith("." + DOMINIO_PERMITIDO)


def validar_url(url):
    """Acepta solo https sobre sii.cl o un subdominio."""
    partes = urlparse(url)
    if partes.scheme != "https":
        raise UrlRechazada(f"solo se acepta https, se recibió '{partes.scheme}'")
    if not _host_permitido(partes.hostname):
        raise UrlRechazada(f"host fuera del dominio permitido: {partes.hostname}")
    return url


def validar_salto(url_origen, url_destino):
    """Revalida el host en cada redirect: un sii.cl que sale del dominio se rechaza."""
    partes = urlparse(url_destino)
    if partes.scheme != "https" or not _host_permitido(partes.hostname):
        raise UrlRechazada(
            f"el redirect desde {urlparse(url_origen).hostname} apunta a "
            f"{partes.hostname}, fuera del dominio permitido")
    return url_destino


def exigir_pdf(content_type):
    """Solo se procesa PDF. Un documento publicado en HTML se guarda a PDF primero.

    Se compara el media type, no la cabecera completa: buscar la subcadena
    aceptaría un `text/html; x=application/pdf`, y el archivo guardado sería
    HTML con extensión .pdf.
    """
    media_type = (content_type or "").split(";")[0].strip().lower()
    if media_type != "application/pdf":
        raise UrlRechazada(
            f"la URL respondió '{content_type}' y solo se acepta application/pdf")
    return True


def leer_pdf(ruta):
    """Texto por página. Aborta si el PDF no tiene capa de texto."""
    from pypdf import PdfReader
    lector = PdfReader(ruta)
    paginas = [(p.extract_text() or "") for p in lector.pages]
    if not any(p.strip() for p in paginas):
        raise PdfSinTexto(
            f"'{ruta}' no tiene texto extraíble; si es un escaneo, no se procesa")
    return paginas


def construir_abridor():
    """Abridor HTTP que NO sigue redirects por su cuenta.

    urlopen() los sigue solo: para cuando se puede mirar la URL final, la
    petición al host de destino ya se hizo. Acá cada 3xx vuelve como HTTPError,
    se valida el Location y recién entonces se hace la petición siguiente.
    """
    import urllib.request

    class _SinSeguirRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return urllib.request.build_opener(_SinSeguirRedirects)


CODIGOS_DE_REDIRECT = (301, 302, 303, 307, 308)


def descargar_pdf(url, destino, abridor=None):
    """Descarga validando cada salto ANTES de seguirlo."""
    import urllib.error
    from urllib.parse import urljoin
    abridor = abridor or construir_abridor()
    actual = validar_url(url)

    for _ in range(MAXIMO_DE_SALTOS + 1):
        try:
            respuesta = abridor.open(actual)
        except urllib.error.HTTPError as error:
            if error.code not in CODIGOS_DE_REDIRECT:
                raise
            ubicacion = error.headers.get("Location") if error.headers else None
            if not ubicacion:
                raise UrlRechazada(f"redirect {error.code} sin Location desde {actual}")
            # valida antes de tocar el destino; si no pasa, no se hace la petición
            actual = validar_salto(actual, urljoin(actual, ubicacion))
            continue
        with respuesta:
            exigir_pdf(respuesta.headers.get("Content-Type"))
            with open(destino, "wb") as archivo:
                archivo.write(respuesta.read())
        return destino

    raise UrlRechazada(
        f"más de {MAXIMO_DE_SALTOS} redirects desde {url}; se aborta la descarga")


_FLAG_DE_CAMPO = {"tipo": "--tipo", "numero": "--numero",
                  "fecha_documento": "--fecha-documento"}


def _main():
    import argparse, json, sys, tempfile, os
    analizador = argparse.ArgumentParser(
        description="Extrae un documento normativo del SII a fuente.json")
    analizador.add_argument("entrada", help="ruta a un PDF local o URL https de sii.cl")
    analizador.add_argument("--out", default="fuente.json")
    # Campos de identidad, solo para la segunda pasada cuando la detección falla.
    # No hay --anio: el año se deriva de la fecha.
    analizador.add_argument("--tipo", choices=("circular", "resolucion", "oficio"))
    analizador.add_argument("--numero")
    analizador.add_argument("--fecha-documento", dest="fecha_documento",
                            help='formato "31 de agosto de 2026"')
    argumentos = analizador.parse_args()

    # Quien usa esto es un contador sin experiencia de terminal: un traceback
    # de pypdf o de urllib no le dice qué hacer. Cada fallo previsible sale
    # como una línea que nombra la causa y, cuando la hay, la salida.
    try:
        if argumentos.entrada.lower().startswith(("http://", "https://")):
            ruta = os.path.join(tempfile.gettempdir(), "documento-sii.pdf")
            descargar_pdf(argumentos.entrada, ruta)
            origen = {"clase": "url", "url": argumentos.entrada}
        else:
            ruta = argumentos.entrada
            origen = {"clase": "pdf", "ruta": argumentos.entrada}
        paginas = leer_pdf(ruta)
    except UrlRechazada as error:
        print(f"URL RECHAZADA: {error}")
        print("Solo se acepta https sobre sii.cl y el documento debe ser un PDF. "
              "Si está publicado en HTML, guárdalo a PDF y pasa el archivo.")
        sys.exit(1)
    except PdfSinTexto as error:
        print(f"PDF SIN TEXTO: {error}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"NO SE ENCONTRÓ EL ARCHIVO: {argumentos.entrada}")
        sys.exit(1)
    except ModuleNotFoundError as error:
        print(f"FALTA UNA DEPENDENCIA: {error.name}")
        print("Instálalas con: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as error:
        print(f"NO SE PUDO LEER EL DOCUMENTO: {type(error).__name__}: {error}")
        print("Si el PDF está cifrado, protegido o dañado, ábrelo en un visor y "
              "vuelve a guardarlo antes de reintentar.")
        sys.exit(1)
    identidad = detectar_identidad(paginas[0])
    aportado = {campo: getattr(argumentos, campo)
                for campo in CAMPOS_DE_IDENTIDAD
                if getattr(argumentos, campo, None)}
    if aportado:
        try:
            identidad = completar_identidad(identidad, aportado)
        except ValueError as error:
            print(f"IDENTIDAD INVÁLIDA: {error}")
            sys.exit(2)

    # El archivo se escribe solo con la identidad completa. Escribirlo igual
    # dejaria un fuente.json a medias en disco, y una fase siguiente que no
    # mire el codigo de salida arrancaria sobre el.
    try:
        exigir_identidad_completa(identidad)
    except IdentidadIncompleta:
        faltantes = [c for c in CAMPOS_DE_IDENTIDAD if identidad.get(c) is None]
        print("CAMPOS DE IDENTIDAD SIN DETECTAR: " + ", ".join(faltantes))
        print("Preguntaselos al usuario y vuelve a correr agregando: "
              + " ".join(f'{_FLAG_DE_CAMPO[c]} "..."' for c in faltantes))
        print("No se infieren del reloj, del nombre del archivo ni de la URL.")
        print(f"No se escribio {argumentos.out}.")
        sys.exit(2)

    fuente = construir_fuente(paginas, origen, identidad)
    with open(argumentos.out, "w", encoding="utf-8") as archivo:
        json.dump(fuente, archivo, ensure_ascii=False, indent=2)
    print(f"{argumentos.out}: {fuente['metricas']['paginas']} paginas, "
          f"{fuente['metricas']['caracteres']} caracteres")


if __name__ == "__main__":
    _main()
