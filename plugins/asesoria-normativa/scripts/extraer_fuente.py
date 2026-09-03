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
