"""Validación estricta del contrato de resumen.json.

Contrato cerrado: cualquier propiedad no declarada es error, nunca se ignora en
silencio. Incluye las reglas de procedencia — qué posición admite texto libre y
cuál no— porque son estructurales: un resumen que las viola no describe un
documento emitible, y detectarlas acá evita que el builder produzca algo
incompleto sin avisar.
"""
import importlib.util as _il, os as _os

def _cargar_vecino(nombre):
    ruta = _os.path.join(_os.path.dirname(__file__), nombre + ".py")
    spec = _il.spec_from_file_location(nombre, ruta)
    modulo = _il.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

catalogo = _cargar_vecino("catalogo")

# El largo mínimo de cita NO se valida acá: el criterio son 40 caracteres
# normalizados, y la normalización vive en el gate. El esquema comprueba
# presencia y tipo; el gate comprueba el largo real.
MAXIMO_DE_CITAS_POR_CELDA = 4
LARGO_MAXIMO_DE_FIRMA = 120

# Prefijo estable del único motivo que el gate reetiqueta como falta de
# suplencia. Un 'suple_seccion' mal ubicado no entra acá: es error de contrato.
MOTIVO_OBLIGATORIA_AUSENTE = "faltan secciones obligatorias"

_CAMPOS_DE_META = {"elaborado_por"}
_CAMPOS_DE_SECCION = {"id", "titulo", "bloques"}
_CAMPOS_DE_CITA = {"texto", "pagina"}
# `citas` figura como campo permitido incluso donde la atomicidad lo prohíbe: así
# el error que ve quien redacta es "atomicidad", que dice qué hacer, y no
# "propiedad desconocida", que no.
_CAMPOS_POR_BLOQUE = {
    "parrafo": {"tipo", "afirmacion", "texto", "cita", "pagina", "citas"},
    "nota": {"tipo", "afirmacion", "texto", "cita", "pagina", "citas"},
    "subtitulo": {"tipo", "rotulo_id"},
    "lista": {"tipo", "afirmacion", "items"},
    "callout": {"tipo", "variante", "afirmacion", "texto", "cita", "pagina", "citas"},
    "tabla": {"tipo", "afirmacion", "encabezado", "filas"},
}
_CAMPOS_DE_ITEM = {"texto", "cita", "pagina", "citas", "suple_seccion"}
_CAMPOS_DE_CELDA = {"texto", "cita", "pagina", "citas"}

# Campos sin los cuales el bloque no describe nada emitible. El resto del
# pipeline asume que están: si faltaran, reventaría recién en el gate o en el
# builder, con un error que no dice qué corregir.
_REQUERIDOS_POR_BLOQUE = {
    "parrafo": {"tipo", "afirmacion", "texto"},
    "nota": {"tipo", "afirmacion", "texto"},
    "subtitulo": {"tipo", "rotulo_id"},
    "lista": {"tipo", "afirmacion", "items"},
    "callout": {"tipo", "variante", "afirmacion", "texto"},
    "tabla": {"tipo", "afirmacion", "encabezado", "filas"},
}


class EsquemaInvalido(Exception):
    def __init__(self, ruta, motivo):
        super().__init__(f"{ruta}: {motivo}")
        self.ruta = ruta
        self.motivo = motivo


def _exigir_campos(objeto, permitidos, ruta):
    desconocidos = set(objeto) - permitidos
    if desconocidos:
        raise EsquemaInvalido(ruta, "propiedad desconocida: " + ", ".join(sorted(desconocidos)))


def _validar_pagina(valor, paginas, ruta):
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise EsquemaInvalido(ruta, f"'pagina' debe ser entero, se recibió {valor!r}")
    if not 1 <= valor <= paginas:
        raise EsquemaInvalido(ruta, f"'pagina' {valor} fuera del rango 1-{paginas}")


def _exigir_requeridos(objeto, requeridos, ruta):
    faltantes = requeridos - set(objeto)
    if faltantes:
        raise EsquemaInvalido(
            ruta, "faltan campos obligatorios: " + ", ".join(sorted(faltantes)))


def _exigir_cadena(objeto, campo, ruta, permitir_vacia=False):
    """Presencia y tipo. Sin esto, un `texto: 123` explota recién en el gate."""
    if campo not in objeto:
        raise EsquemaInvalido(ruta, f"falta el campo obligatorio '{campo}'")
    valor = objeto[campo]
    if not isinstance(valor, str):
        raise EsquemaInvalido(
            ruta, f"'{campo}' debe ser texto, se recibió {type(valor).__name__}")
    if not permitir_vacia and not valor.strip():
        raise EsquemaInvalido(ruta, f"'{campo}' no puede estar vacío")
    return valor


def _validar_cita_suelta(objeto, paginas, ruta):
    """Presencia, tipo y página del par cita+pagina. El largo lo mide el gate."""
    _exigir_cadena(objeto, "cita", ruta)
    _validar_pagina(objeto.get("pagina"), paginas, ruta)


def _validar_lista_de_citas(citas, paginas, ruta, maximo):
    if not isinstance(citas, list) or not 1 <= len(citas) <= maximo:
        raise EsquemaInvalido(ruta, f"'citas' debe tener entre 1 y {maximo} entradas")
    for i, cita in enumerate(citas):
        ruta_cita = f"{ruta}.citas[{i}]"
        if not isinstance(cita, dict):
            raise EsquemaInvalido(ruta_cita, "cada cita debe ser un objeto")
        _exigir_campos(cita, _CAMPOS_DE_CITA, ruta_cita)
        _exigir_cadena(cita, "texto", ruta_cita)
        _validar_pagina(cita.get("pagina"), paginas, ruta_cita)


def _validar_texto_con_respaldo(objeto, paginas, ruta, permite_multiples):
    """Un texto no vacío exige respaldo; cita y citas son mutuamente excluyentes."""
    tiene_una, tiene_varias = "cita" in objeto, "citas" in objeto
    if tiene_una and tiene_varias:
        raise EsquemaInvalido(ruta, "'cita' y 'citas' son mutuamente excluyentes")
    if tiene_varias:
        if not permite_multiples:
            raise EsquemaInvalido(
                ruta, "atomicidad: solo celdas de tabla y callouts admiten 'citas'")
        _validar_lista_de_citas(objeto["citas"], paginas, ruta, MAXIMO_DE_CITAS_POR_CELDA)
    elif tiene_una:
        _validar_cita_suelta(objeto, paginas, ruta)
    else:
        raise EsquemaInvalido(ruta, "texto no vacío sin 'cita' que lo respalde")


def _validar_bloque(bloque, id_seccion, paginas, ruta):
    if not isinstance(bloque, dict):
        raise EsquemaInvalido(ruta, "cada bloque debe ser un objeto")
    tipo = bloque.get("tipo")
    if not isinstance(tipo, str) or tipo not in _CAMPOS_POR_BLOQUE:
        raise EsquemaInvalido(ruta, f"tipo de bloque desconocido: {tipo!r}")
    if tipo not in catalogo.bloques_permitidos(id_seccion):
        raise EsquemaInvalido(ruta, f"'{tipo}' no está permitido en '{id_seccion}'")
    _exigir_campos(bloque, _CAMPOS_POR_BLOQUE[tipo], ruta)
    _exigir_requeridos(bloque, _REQUERIDOS_POR_BLOQUE[tipo], ruta)
    if tipo in ("parrafo", "nota", "callout"):
        _exigir_cadena(bloque, "texto", ruta)

    if tipo == "subtitulo":
        rotulo = bloque.get("rotulo_id")
        if not isinstance(rotulo, str) or rotulo not in catalogo.SUBTITULOS:
            raise EsquemaInvalido(ruta, f"rotulo_id fuera del catálogo: {rotulo!r}")
        return

    afirmacion = bloque.get("afirmacion")
    if afirmacion not in ("citada", "derivada"):
        raise EsquemaInvalido(ruta, f"'afirmacion' inválida: {afirmacion!r}")
    if afirmacion == "derivada" and id_seccion not in catalogo.SECCIONES_CON_DERIVADA:
        raise EsquemaInvalido(
            ruta, "una 'derivada' solo puede aparecer en gestiones o a_verificar")
    if tipo == "callout" and bloque.get("variante") not in catalogo.VARIANTES_DE_CALLOUT:
        raise EsquemaInvalido(ruta, f"variante inválida: {bloque.get('variante')!r}")

    if tipo == "lista":
        _validar_items(bloque, afirmacion, id_seccion, paginas, ruta)
    elif tipo == "tabla":
        _validar_tabla(bloque, paginas, ruta)
    elif afirmacion == "citada":
        # Un callout es prosa y lleva UNA cita, como un párrafo. La unión de
        # varias citas respalda cada dato por separado pero no la relación
        # entre ellos: con dos citas de páginas distintas se puede afirmar
        # "el plazo del artículo 200 se reduce a 90 días" y que el gate lo
        # acepte, porque una cita trae el artículo y la otra el plazo. La
        # excepción son las celdas de tabla, donde la grilla impide partir el
        # contenido en dos.
        _validar_texto_con_respaldo(bloque, paginas, ruta, permite_multiples=False)
    else:
        if "cita" in bloque or "citas" in bloque:
            raise EsquemaInvalido(ruta, "una 'derivada' no lleva citas")


def _validar_items(bloque, afirmacion, id_seccion, paginas, ruta):
    items = bloque.get("items")
    if not isinstance(items, list) or not items:
        raise EsquemaInvalido(ruta, "'items' debe ser una lista no vacía")
    for i, item in enumerate(items):
        ruta_item = f"{ruta}.items[{i}]"
        if not isinstance(item, dict):
            raise EsquemaInvalido(ruta_item, "cada item debe ser un objeto")
        _exigir_campos(item, _CAMPOS_DE_ITEM, ruta_item)
        _exigir_cadena(item, "texto", ruta_item)
        # Fuera de a_verificar la suplencia no se comprueba nunca, así que
        # aceptarla ahí sería aceptar una declaración que nadie lee.
        if "suple_seccion" in item and (
                afirmacion != "derivada" or id_seccion != "a_verificar"):
            raise EsquemaInvalido(
                ruta_item, "'suple_seccion' solo es válido en un item 'derivada' "
                           "de la sección 'a_verificar'")
        if afirmacion == "derivada":
            sobrantes = {"cita", "citas", "pagina"} & set(item)
            if sobrantes:
                raise EsquemaInvalido(
                    ruta_item, "una 'derivada' no lleva aparato de cita: "
                               + ", ".join(sorted(sobrantes)))
        else:
            _validar_texto_con_respaldo(item, paginas, ruta_item, permite_multiples=False)


def _validar_tabla(bloque, paginas, ruta):
    encabezado, filas = bloque.get("encabezado"), bloque.get("filas")
    if not isinstance(encabezado, list) or not encabezado:
        raise EsquemaInvalido(ruta, "'encabezado' debe ser una lista no vacía")
    if not isinstance(filas, list) or not filas:
        raise EsquemaInvalido(ruta, "'filas' debe ser una lista no vacía")
    for i, celda in enumerate(encabezado):
        _validar_celda(celda, paginas, f"{ruta}.encabezado[{i}]")
    for f, fila in enumerate(filas):
        if not isinstance(fila, list) or len(fila) != len(encabezado):
            raise EsquemaInvalido(
                f"{ruta}.filas[{f}]",
                f"largo {len(fila) if isinstance(fila, list) else '?'} distinto "
                f"del encabezado ({len(encabezado)})")
        for c, celda in enumerate(fila):
            _validar_celda(celda, paginas, f"{ruta}.filas[{f}][{c}]")


def _validar_celda(celda, paginas, ruta):
    if not isinstance(celda, dict):
        raise EsquemaInvalido(ruta, "cada celda debe ser un objeto")
    _exigir_campos(celda, _CAMPOS_DE_CELDA, ruta)
    # `texto` es obligatorio incluso en la celda vacía: el contrato pide
    # {"texto": ""} explícito, no una celda {} que se interprete como vacía.
    texto = _exigir_cadena(celda, "texto", ruta, permitir_vacia=True)
    if texto.strip() == "":
        if "cita" in celda or "citas" in celda:
            raise EsquemaInvalido(ruta, "una celda vacía no lleva cita")
        return
    _validar_texto_con_respaldo(celda, paginas, ruta, permite_multiples=True)


def validar(resumen, fuente):
    """Valida resumen.json contra el contrato. Levanta EsquemaInvalido al primer problema."""
    if not isinstance(fuente, dict):
        raise EsquemaInvalido("fuente", "fuente.json debe ser un objeto")
    tipo = fuente.get("tipo")
    if not isinstance(tipo, str) or tipo not in catalogo.PERFILES:
        raise EsquemaInvalido("fuente", f"tipo de documento desconocido: {tipo!r}")
    metricas = fuente.get("metricas")
    if not isinstance(metricas, dict):
        raise EsquemaInvalido("fuente", "falta el bloque 'metricas'")
    paginas = metricas.get("paginas")
    if not isinstance(paginas, int) or isinstance(paginas, bool) or paginas < 1:
        raise EsquemaInvalido(
            "fuente", f"'metricas.paginas' debe ser un entero positivo: {paginas!r}")
    perfil = catalogo.PERFILES[tipo]

    if not isinstance(resumen, dict):
        raise EsquemaInvalido("raiz", "resumen.json debe ser un objeto")
    _exigir_campos(resumen, {"meta", "secciones"}, "raiz")
    _exigir_requeridos(resumen, {"meta", "secciones"}, "raiz")

    meta = resumen["meta"]
    if not isinstance(meta, dict):
        raise EsquemaInvalido("meta", "'meta' debe ser un objeto")
    _exigir_campos(meta, _CAMPOS_DE_META, "meta")
    if "elaborado_por" in meta:
        firma = _exigir_cadena(meta, "elaborado_por", "meta")
        # Es el unico texto del documento que no pasa por el gate, porque lo
        # aporta el contador. Acotarlo evita que sea un hueco por donde entre
        # prosa sin respaldo a la linea de metadata.
        if len(firma) > LARGO_MAXIMO_DE_FIRMA:
            raise EsquemaInvalido(
                "meta", f"'elaborado_por' excede {LARGO_MAXIMO_DE_FIRMA} caracteres: "
                        "es el nombre de quien firma, no un campo de texto libre")

    secciones = resumen["secciones"]
    if not isinstance(secciones, list) or not secciones:
        raise EsquemaInvalido("secciones", "debe ser una lista no vacía")

    presentes = []
    for s, seccion in enumerate(secciones):
        ruta = f"secciones[{s}]"
        if not isinstance(seccion, dict):
            raise EsquemaInvalido(ruta, "cada sección debe ser un objeto")
        _exigir_campos(seccion, _CAMPOS_DE_SECCION, ruta)
        _exigir_requeridos(seccion, {"id", "bloques"}, ruta)
        id_seccion = seccion.get("id")
        if not isinstance(id_seccion, str) or id_seccion not in catalogo.SECCIONES:
            raise EsquemaInvalido(ruta, f"id de sección desconocido: {id_seccion!r}")
        # Falla cerrada: se exige que el perfil la admita, en vez de rechazar
        # solo lo prohibido. Con la regla al revés, una sección que el perfil no
        # clasifique pasa el gate y después desaparece del orden de emisión, y
        # el builder la emite después de las secciones de cierre.
        if id_seccion not in perfil["obligatorias"] and id_seccion not in perfil["sugeridas"]:
            raise EsquemaInvalido(
                ruta, f"'{id_seccion}' no está admitida en un documento de tipo '{tipo}'")
        if id_seccion != "materia" and id_seccion in presentes:
            # Solo `materia` es repetible; duplicar otra emite dos veces el mismo
            # encabezado, y con las de cierre parte el documento en dos.
            raise EsquemaInvalido(
                ruta, f"'{id_seccion}' está repetida y solo 'materia' es repetible")
        presentes.append(id_seccion)

        if id_seccion == "materia":
            titulo = seccion.get("titulo")
            if not isinstance(titulo, dict):
                raise EsquemaInvalido(ruta, "'materia' exige un titulo con cita")
            _exigir_campos(titulo, {"texto", "cita", "pagina"}, f"{ruta}.titulo")
            _exigir_cadena(titulo, "texto", f"{ruta}.titulo")
            _validar_cita_suelta(titulo, paginas, f"{ruta}.titulo")
        elif "titulo" in seccion:
            raise EsquemaInvalido(
                ruta, f"'titulo' solo se declara en 'materia'; '{id_seccion}' lo toma "
                      "del catálogo")

        bloques = seccion.get("bloques")
        if not isinstance(bloques, list) or not bloques:
            raise EsquemaInvalido(f"{ruta}.bloques", "debe ser una lista no vacía")
        for b, bloque in enumerate(bloques):
            _validar_bloque(bloque, id_seccion, paginas, f"{ruta}.bloques[{b}]")

    _validar_suplencias(resumen, presentes, perfil)


def _validar_suplencias(resumen, presentes, perfil):
    """Toda obligatoria ausente debe estar declarada en a_verificar."""
    suplidas = {}
    for s, seccion in enumerate(resumen["secciones"]):
        if seccion["id"] != "a_verificar":
            continue
        for b, bloque in enumerate(seccion["bloques"]):
            for i, item in enumerate(bloque.get("items", [])):
                if "suple_seccion" not in item:
                    continue
                objetivo = item["suple_seccion"]
                ruta = f"secciones[{s}].bloques[{b}].items[{i}]"
                if not isinstance(objetivo, str):
                    raise EsquemaInvalido(
                        ruta, f"'suple_seccion' debe nombrar una sección: {objetivo!r}")
                if objetivo not in perfil["obligatorias"]:
                    raise EsquemaInvalido(
                        ruta, f"'{objetivo}' no es obligatoria en este perfil: no se suple")
                if objetivo in presentes:
                    raise EsquemaInvalido(
                        ruta, f"'{objetivo}' está presente: no corresponde suplirla")
                if objetivo in suplidas:
                    raise EsquemaInvalido(
                        ruta, f"'{objetivo}' ya se declaró suplida en {suplidas[objetivo]}")
                suplidas[objetivo] = ruta

    faltantes = [s for s in perfil["obligatorias"] if s not in presentes and s not in suplidas]
    if not faltantes:
        return
    # `a_verificar` es donde se declara la suplencia: pedir que se declare su
    # propia ausencia ahí adentro es insatisfacible, y el gate lo reetiquetaría
    # como falta de suplencia cuando lo que falta es la sección entera.
    if "a_verificar" in faltantes:
        raise EsquemaInvalido(
            "secciones",
            MOTIVO_OBLIGATORIA_AUSENTE + " y 'a_verificar' es una de ellas, así que "
            "no hay dónde declarar las suplencias: " + ", ".join(faltantes))
    raise EsquemaInvalido(
        "secciones",
        MOTIVO_OBLIGATORIA_AUSENTE + ", y ningún item de a_verificar las declara "
        "en 'suple_seccion': " + ", ".join(faltantes))
