"""Gate de citas: valida el contrato y el respaldo textual antes de armar el .docx.

Dos etapas. La A valida el esquema, incluidas las reglas de procedencia. La B
comprueba que cada cita exista literalmente en la página declarada y que los
datos verificables del texto sean coherentes con su respaldo.

Garantiza procedencia y coherencia de literales, NO equivalencia semántica entre
la paráfrasis y la cita, ni fidelidad de la extracción del PDF. Por eso el
respaldo de citas es un paso de revisión obligatorio antes de enviar.
"""
import importlib.util as _il, os as _os

def _cargar_vecino(nombre):
    ruta = _os.path.join(_os.path.dirname(__file__), nombre + ".py")
    spec = _il.spec_from_file_location(nombre, ruta)
    modulo = _il.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

esquema = _cargar_vecino("esquema")
literales = _cargar_vecino("literales")
extraer_fuente = _cargar_vecino("extraer_fuente")
catalogo = _cargar_vecino("catalogo")


class GateRechazado(Exception):
    def __init__(self, ruta, motivo):
        super().__init__(f"{ruta}: {motivo}")
        self.ruta = ruta
        self.motivo = motivo


class CitaInexistente(GateRechazado): ...
class CitaAusente(GateRechazado): ...
class PaginaInvalida(GateRechazado): ...
class LiteralSinRespaldo(GateRechazado): ...
class DerivadaConDato(GateRechazado): ...
class SuplenciaFaltante(GateRechazado): ...


# El criterio son 40 caracteres NORMALIZADOS, así que vive acá y no en el
# esquema: la normalización es de esta capa.
LARGO_MINIMO_DE_CITA = 40


def _pagina_normalizada(fuente, numero):
    for pagina in fuente["paginas_normalizadas"]:
        if pagina["n"] == numero:
            return pagina["texto"]
    return ""


def _comprobar_una_cita(texto_cita, pagina, fuente, ruta):
    normalizada = extraer_fuente.normalizar_matching(texto_cita)
    if len(normalizada) < LARGO_MINIMO_DE_CITA:
        raise CitaAusente(
            ruta, f"cita de {len(normalizada)} caracteres normalizados; el mínimo "
                  f"es {LARGO_MINIMO_DE_CITA}")
    if normalizada not in fuente["texto_normalizado"]:
        raise CitaInexistente(ruta, "la cita no aparece literalmente en el documento")
    if normalizada not in _pagina_normalizada(fuente, pagina):
        raise PaginaInvalida(ruta, f"la cita no está en la página {pagina}")


def _citas_de(objeto):
    """Devuelve [(texto, pagina)] tanto para el caso de una cita como de varias."""
    if "citas" in objeto:
        return [(c["texto"], c["pagina"]) for c in objeto["citas"]]
    if "cita" in objeto:
        return [(objeto["cita"], objeto["pagina"])]
    return []


def _comprobar_afirmacion(objeto, fuente, ruta, filas):
    citas = _citas_de(objeto)
    for texto_cita, pagina in citas:
        _comprobar_una_cita(texto_cita, pagina, fuente, ruta)

    del_texto = literales.extraer(extraer_fuente.normalizar_lectura(objeto["texto"]))

    # Una cantidad que el parser no pudo resolver se rechaza antes de comparar:
    # el centinela no es un literal, y dejarlo entrar a la diferencia de
    # conjuntos permitiría que un texto ambiguo se respalde con una cita
    # igual de ambigua.
    irresolubles = {t for t in del_texto if t.startswith(literales.MARCA_IRRESOLUBLE)}
    if irresolubles:
        raise LiteralSinRespaldo(
            ruta, "hay una cantidad que no se pudo interpretar; reescribe la cifra de "
                  "forma inequívoca: " + ", ".join(sorted(irresolubles)))

    respaldo = set()
    for texto_cita, _ in citas:
        respaldo |= literales.extraer(extraer_fuente.normalizar_lectura(texto_cita))
    sin_respaldo = del_texto - respaldo
    if sin_respaldo:
        raise LiteralSinRespaldo(
            ruta, "datos del texto que no están en la cita: " + ", ".join(sorted(sin_respaldo)))

    for texto_cita, pagina in citas:
        filas.append({"texto": objeto["texto"], "cita": texto_cita, "pagina": pagina,
                      "ruta": ruta})


def _comprobar_derivada(objeto, ruta):
    encontrados = literales.extraer(extraer_fuente.normalizar_lectura(objeto["texto"]))
    if encontrados:
        raise DerivadaConDato(
            ruta, "una recomendación no puede introducir datos verificables ("
                  + ", ".join(sorted(encontrados))
                  + "); separa el hecho como afirmación citada")


def _recorrer_bloque(bloque, id_seccion, fuente, ruta, filas):
    tipo = bloque["tipo"]
    if tipo == "subtitulo":
        return
    derivada = bloque.get("afirmacion") == "derivada"

    if tipo == "lista":
        for i, item in enumerate(bloque["items"]):
            ruta_item = f"{ruta}.items[{i}]"
            if derivada:
                _comprobar_derivada(item, ruta_item)
            else:
                _comprobar_afirmacion(item, fuente, ruta_item, filas)
        return

    if tipo == "tabla":
        for i, celda in enumerate(bloque["encabezado"]):
            if celda.get("texto", "").strip():
                _comprobar_afirmacion(celda, fuente, f"{ruta}.encabezado[{i}]", filas)
        for f, fila in enumerate(bloque["filas"]):
            for c, celda in enumerate(fila):
                if celda.get("texto", "").strip():
                    _comprobar_afirmacion(celda, fuente, f"{ruta}.filas[{f}][{c}]", filas)
        return

    if derivada:
        _comprobar_derivada(bloque, ruta)
    else:
        _comprobar_afirmacion(bloque, fuente, ruta, filas)


def verificar(resumen, fuente):
    """Etapa A + etapa B. Devuelve las filas del respaldo o levanta."""
    try:
        esquema.validar(resumen, fuente)
    except esquema.EsquemaInvalido as error:
        # Solo la obligatoria ausente se reetiqueta. Un 'suple_seccion' mal
        # ubicado es un error de contrato y debe seguir siendo EsquemaInvalido.
        if error.motivo.startswith(esquema.MOTIVO_OBLIGATORIA_AUSENTE):
            raise SuplenciaFaltante(error.ruta, error.motivo) from error
        raise

    filas = []
    for s, seccion in enumerate(resumen["secciones"]):
        ruta_seccion = f"secciones[{s}]"
        if seccion["id"] == "materia":
            titulo = seccion["titulo"]
            _comprobar_afirmacion(titulo, fuente, f"{ruta_seccion}.titulo", filas)
        for b, bloque in enumerate(seccion["bloques"]):
            _recorrer_bloque(bloque, seccion["id"], fuente,
                             f"{ruta_seccion}.bloques[{b}]", filas)
    return filas


def escribir_respaldo(filas, fuente, salida):
    """Emite el respaldo de citas que revisa el contador. No se entrega al cliente."""
    lineas = [
        "# Respaldo de citas",
        "",
        "Documento de trabajo interno: **no se entrega al cliente**.",
        "",
        "Revisa cada afirmación contra su cita antes de enviar el resumen. El gate "
        "garantiza que la cita existe y que sus datos coinciden, no que la paráfrasis "
        "sea fiel ni que la extracción del PDF esté libre de artefactos.",
        "",
        "## Procedencia de los campos de identidad",
        "",
        "| Campo | Origen |",
        "|---|---|",
    ]
    for campo, origen in sorted(fuente.get("procedencia_campos", {}).items()):
        marca = " ⚠️ aportado por el usuario" if origen == "usuario" else ""
        lineas.append(f"| `{campo}` | {origen}{marca} |")
    lineas += ["", "## Afirmaciones y respaldo", "",
               "| Ubicación | Afirmación | Cita | Página |", "|---|---|---|---|"]
    for fila in filas:
        texto = fila["texto"].replace("|", "\\|")
        cita = fila["cita"].replace("|", "\\|")
        lineas.append(f"| `{fila['ruta']}` | {texto} | {cita} | {fila['pagina']} |")
    with open(salida, "w", encoding="utf-8") as archivo:
        archivo.write("\n".join(lineas) + "\n")


def _main():
    import argparse, json, sys
    analizador = argparse.ArgumentParser(description="Valida resumen.json contra fuente.json")
    analizador.add_argument("fuente")
    analizador.add_argument("resumen")
    analizador.add_argument("--respaldo", default="respaldo-citas.md")
    argumentos = analizador.parse_args()

    with open(argumentos.fuente, encoding="utf-8") as archivo:
        fuente = json.load(archivo)
    with open(argumentos.resumen, encoding="utf-8") as archivo:
        resumen = json.load(archivo)

    try:
        filas = verificar(resumen, fuente)
    except (esquema.EsquemaInvalido, GateRechazado) as error:
        print(f"RECHAZADO [{type(error).__name__}] {error}")
        sys.exit(1)

    escribir_respaldo(filas, fuente, argumentos.respaldo)
    print(f"OK: {len(filas)} afirmaciones respaldadas. Respaldo en {argumentos.respaldo}")


if __name__ == "__main__":
    _main()
