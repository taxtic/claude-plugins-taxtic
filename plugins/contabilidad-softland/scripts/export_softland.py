"""Exportador Softland por perfiles: serializa LineaSoftland[] ya aprobadas
(salida de transform.py) al formato fisico de un perfil de layout.

Pipeline: LineaSoftland semantica -> perfil_layout -> fila fisica -> CSV.

Perfiles (rules/softland-layouts.json):
- OFICIAL_61: perfil por defecto (Fase 8.8) y VALIDADO end-to-end en
  Softland real (Fase 8.16) para el escenario de un banco/cliente/SIMPLE/
  una factura/diferencia=0 -- ver conciliacion_bancaria_validada en el
  perfil para el alcance exacto (no cubre TRANSBANK, multiples
  facturas/clientes, otros bancos, proveedores ni cargos).
- OPERATIVO_62: respaldado originalmente por captura.csv (Fase 5.2/5.3),
  pero contradicho por evidencia mas fuerte y directa de Fase 8.8 (un
  archivo de carga real VIGENTE en Softland usa 61 columnas, ';' como
  delimitador y BOM, no 62/',' /sin BOM) -- ver advertencia en el perfil.
  Ya no es el perfil por defecto; se mantiene solo como referencia
  historica, sin evidencia real de exito (los 5 intentos V1-V5 fallaron).

Cada perfil declara su propio delimitador ('delimitador'), si usa BOM
('con_bom') y si termina en un delimitador extra tras la ultima columna
('trailing_delimitador') -- ningun valor esta hardcodeado en este script.

Este script NO decide cuentas, Debe/Haber, auxiliares, glosas, ni cambia
estado_motor/estado_humano -- todo eso ya viene resuelto en las
LineaSoftland que recibe. Solo transforma esa forma semantica en una fila
fisica y la serializa. No reconstruye ninguna logica de aprobacion.
"""
import argparse
import calendar
import json
import os
import sys
from pathlib import Path

RULES_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "rules" / "softland-layouts.json"

# Campos semanticos de LineaSoftland que este exportador sabe ubicar en un
# perfil. Todo lo que el perfil documenta pero que LineaSoftland no provee
# (ej. flujos de efectivo, detalle de libro, numero de agrupacion) queda en
# el valor de relleno del perfil (valor_relleno_no_utilizado -- '' o 0 segun
# perfil, ver rules/softland-layouts.json), nunca inventado aqui.
CAMPOS_SEMANTICOS = (
    "cuenta", "debe", "haber", "glosa", "auxiliar", "tipo_documento",
    "numero_documento", "fecha_emision", "fecha_vencimiento",
    "tipo_docto_conciliacion", "numero_docto_conciliacion",
    "numero_docto_referencia",
)

_CAMPOS_MONTO = ("debe", "haber")
_CAMPOS_FECHA = ("fecha_emision", "fecha_vencimiento")

_CAMPOS_LINEA_REQUERIDOS = (
    "movimiento_id", "tipo_linea", "cuenta", "debe", "haber", "glosa",
    "auxiliar", "tipo_documento", "numero_documento", "fecha_emision",
    "fecha_vencimiento", "tipo_docto_conciliacion", "numero_docto_conciliacion",
    "numero_docto_referencia",
)


class ExportError(ValueError):
    """Error explicito de exportacion, con codigo estable para tests."""
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        super().__init__(f"{codigo}: {mensaje}")


def _cargar_layouts(path=None):
    p = Path(path) if path else RULES_PATH_DEFAULT
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _obtener_perfil(layouts, nombre_perfil):
    perfiles = layouts.get("perfiles", {})
    perfil = perfiles.get(nombre_perfil)
    if perfil is None:
        raise ExportError(
            "PERFIL_LAYOUT_NO_CONFIGURADO",
            f"El perfil {nombre_perfil!r} no existe en rules/softland-layouts.json "
            f"(perfiles disponibles: {sorted(perfiles.keys())}).",
        )
    return {**perfil, "_nombre": nombre_perfil}


def _validar_estructura_linea(linea):
    """Defensa contra estructuras mal formadas -- NO valida aprobacion
    humana ni estado_motor, eso ya lo resolvio approval.py/transform.py."""
    faltantes = [c for c in _CAMPOS_LINEA_REQUERIDOS if c not in linea]
    if faltantes:
        raise ExportError(
            "LINEA_MAL_FORMADA",
            f"LineaSoftland de movimiento_id={linea.get('movimiento_id')!r} no tiene "
            f"los campos requeridos: {faltantes}.",
        )


def _validar_texto_serializable(valor, movimiento_id, tipo_linea, campo, delimitador=","):
    """El delimitador es propio de cada perfil (Fase 8.8: OFICIAL_61 usa ';'
    real, evidenciado por un archivo de carga real vigente; OPERATIVO_62
    sigue en ','). Ningun valor puede contener el delimitador de SU perfil,
    ni CR ni LF. Nunca se limpia silenciosamente."""
    texto = str(valor)
    for caracter, nombre in ((delimitador, "delimitador"), ("\r", "CR"), ("\n", "LF")):
        if caracter in texto:
            raise ExportError(
                "VALOR_NO_SERIALIZABLE",
                f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r} "
                f"contiene un caracter no serializable ({nombre}).",
            )
    return texto


def _validar_glosa(valor, movimiento_id, tipo_linea, delimitador=","):
    texto = _validar_texto_serializable(valor, movimiento_id, tipo_linea, "glosa", delimitador)
    if len(texto) > 255:
        raise ExportError(
            "GLOSA_EXCEDE_LONGITUD_MAXIMA",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r}: la glosa mide "
            f"{len(texto)} caracteres (maximo documentado: 255). No se trunca silenciosamente.",
        )
    return texto


def _validar_texto_o_relleno(valor, movimiento_id, tipo_linea, campo, valor_relleno, delimitador=","):
    """Para auxiliar/tipo_documento/tipo_docto_conciliacion: pueden ser el
    valor de relleno del perfil (ej. 0, entero) cuando no se utilizan, o un
    texto real que debe pasar la misma validacion de serializacion."""
    if valor == valor_relleno:
        return valor
    return _validar_texto_serializable(valor, movimiento_id, tipo_linea, campo, delimitador)


def _validar_monto(valor, movimiento_id, tipo_linea, campo):
    """Debe/Haber: entero puro, sin decimales, sin signo negativo."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ExportError(
            "MONTO_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} no es un entero puro (sin decimales, sin separador de miles).",
        )
    if valor < 0:
        raise ExportError(
            "MONTO_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} es negativo.",
        )
    return valor


def _convertir_fecha(valor, perfil, movimiento_id, tipo_linea, campo):
    """Conversion deterministica de string, sin inferencia y sin usar la
    configuracion regional del sistema. LineaSoftland siempre entrega la
    fecha ya en 'DD/MM/AAAA' (construida por transform.py) o el entero 0
    cuando el campo no aplica a ese tipo_linea."""
    valor_relleno = perfil["valor_relleno_no_utilizado"]
    if valor == valor_relleno:
        return valor_relleno

    if not isinstance(valor, str):
        raise ExportError(
            "FECHA_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} no es una fecha string ni el valor de relleno.",
        )

    partes = valor.split("/")
    if len(partes) != 3:
        raise ExportError(
            "FECHA_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} no tiene el formato DD/MM/AAAA esperado desde LineaSoftland.",
        )
    dia, mes, anio = partes
    if not (dia.isdigit() and mes.isdigit() and anio.isdigit()
            and len(dia) == 2 and len(mes) == 2 and len(anio) == 4):
        raise ExportError(
            "FECHA_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} no cumple DD(2)/MM(2)/AAAA(4).",
        )
    dia_n, mes_n, anio_n = int(dia), int(mes), int(anio)
    if not (1 <= anio_n <= 9999):
        raise ExportError(
            "FECHA_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} tiene anio fuera de rango (1-9999).",
        )
    if not (1 <= mes_n <= 12):
        raise ExportError(
            "FECHA_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} tiene mes fuera de rango (1-12).",
        )
    # Validacion calendarica REAL (no solo 1-31): calendar.monthrange devuelve
    # el ultimo dia valido del mes considerando anios bisiestos, sin depender
    # de locale ni configuracion regional del sistema. Rechaza 31/02, 31/04,
    # 29/02 en anio no bisiesto, etc.
    _, ultimo_dia_del_mes = calendar.monthrange(anio_n, mes_n)
    if not (1 <= dia_n <= ultimo_dia_del_mes):
        raise ExportError(
            "FECHA_NO_SERIALIZABLE",
            f"movimiento_id={movimiento_id!r} tipo_linea={tipo_linea!r} campo={campo!r}: "
            f"{valor!r} no es una fecha calendarica real (el mes {mes_n:02d}/{anio_n} "
            f"tiene {ultimo_dia_del_mes} dias, dia recibido: {dia_n}).",
        )

    formato = perfil["formato_fecha"]
    if formato == "DD/MM/AAAA":
        return valor
    if formato == "DD-MM-AAAA":
        return f"{dia}-{mes}-{anio}"
    raise ExportError(
        "PERFIL_LAYOUT_NO_CONFIGURADO",
        f"Perfil {perfil['_nombre']!r} declara formato_fecha={formato!r} desconocido.",
    )


def construir_fila(linea, perfil):
    """Funcion pura: no modifica `linea`. Devuelve una lista de
    perfil['total_columnas'] valores fisicos ya validados. NO construye
    OPERATIVO_62 (ni ningun perfil) copiando campos_1_a_61 -- usa
    exclusivamente los campos semanticos de LineaSoftland."""
    _validar_estructura_linea(linea)

    movimiento_id = linea["movimiento_id"]
    tipo_linea = linea["tipo_linea"]
    total = perfil["total_columnas"]
    valor_relleno = perfil["valor_relleno_no_utilizado"]
    posiciones = perfil["posiciones"].get(tipo_linea)
    if posiciones is None:
        raise ExportError(
            "PERFIL_LAYOUT_NO_CONFIGURADO",
            f"Perfil {perfil['_nombre']!r} no tiene posiciones configuradas para "
            f"tipo_linea={tipo_linea!r} (movimiento_id={movimiento_id!r}).",
        )

    delimitador = perfil.get("delimitador", ",")
    fila = [valor_relleno] * total

    # Fase 8.1/8.2/8.8: evidencia productiva real sobre campos de catalogo
    # (S/N, codigos de flujo, etc.) obliga a que algunas posiciones lleven
    # un valor fisico LITERAL propio de este flujo, distinto del valor de
    # relleno generico. 'valores_catalogo' es semantico y por-campo (nunca
    # un booleano "vacio si/no"): permite expresar tanto "" como "N"/"S" sin
    # cambiar este mecanismo cuando cambie la evidencia. No depende de
    # ningun movimiento_id ni factura especifica.
    posiciones_catalogo = perfil.get("posiciones_catalogo") or {}
    for campo, valor_catalogo in (perfil.get("valores_catalogo") or {}).items():
        if campo == "_nota":
            continue
        pos = posiciones_catalogo.get(campo)
        if pos is not None:
            fila[pos - 1] = _validar_texto_serializable(valor_catalogo, movimiento_id, tipo_linea, campo, delimitador)

    # Fase 8.9: evidencia real de Softland (reporte del Capturador de
    # Transacciones) confirma que algunas posiciones NO cubiertas por
    # 'posiciones'/CAMPOS_SEMANTICOS para este tipo_linea necesitan de todas
    # formas un valor fisico literal fijo (ej. 'TB' en posiciones 20/24 para
    # BANCO, 17 para CLIENTE) -- distinto tanto del relleno generico como de
    # cualquier campo semantico de LineaSoftland. Por-tipo_linea y por
    # posicion, nunca depende de un movimiento_id ni factura especifica.
    valores_fijos = (perfil.get("valores_fijos_por_posicion") or {}).get(tipo_linea) or {}
    for pos_str, valor_fijo in valores_fijos.items():
        pos = int(pos_str)
        fila[pos - 1] = _validar_texto_serializable(valor_fijo, movimiento_id, tipo_linea, f"posicion_{pos}", delimitador)

    def _set(campo, calcular_valor):
        """Solo invoca calcular_valor() -- y por lo tanto solo valida --
        cuando este tipo_linea realmente declara una posicion fisica para
        `campo`. Evita validar campos que transform.py marca como 0 (no
        aplica a este tipo_linea) contra un perfil cuyo valor_relleno_no_utilizado
        ya no sea 0 (Fase 8.4): ese 0 es una convencion de LineaSoftland
        ('no aplica'), independiente del relleno fisico del perfil."""
        pos = posiciones.get(campo)
        if pos is None:
            return
        fila[pos - 1] = calcular_valor()

    _set("cuenta", lambda: _validar_texto_serializable(linea["cuenta"], movimiento_id, tipo_linea, "cuenta", delimitador))
    _set("debe", lambda: _validar_monto(linea["debe"], movimiento_id, tipo_linea, "debe"))
    _set("haber", lambda: _validar_monto(linea["haber"], movimiento_id, tipo_linea, "haber"))
    _set("glosa", lambda: _validar_glosa(linea["glosa"], movimiento_id, tipo_linea, delimitador))
    _set("auxiliar", lambda: _validar_texto_o_relleno(linea["auxiliar"], movimiento_id, tipo_linea, "auxiliar", valor_relleno, delimitador))
    _set("tipo_documento", lambda: _validar_texto_o_relleno(linea["tipo_documento"], movimiento_id, tipo_linea, "tipo_documento", valor_relleno, delimitador))
    _set("numero_documento", lambda: linea["numero_documento"])
    _set("fecha_emision", lambda: _convertir_fecha(linea["fecha_emision"], perfil, movimiento_id, tipo_linea, "fecha_emision"))
    _set("fecha_vencimiento", lambda: _convertir_fecha(linea["fecha_vencimiento"], perfil, movimiento_id, tipo_linea, "fecha_vencimiento"))
    _set("tipo_docto_conciliacion", lambda: _validar_texto_o_relleno(linea["tipo_docto_conciliacion"], movimiento_id, tipo_linea, "tipo_docto_conciliacion", valor_relleno, delimitador))
    _set("numero_docto_conciliacion", lambda: linea["numero_docto_conciliacion"])
    _set("numero_docto_referencia", lambda: linea["numero_docto_referencia"])

    return fila


def _celda_a_texto(valor):
    return str(valor)


def serializar_fila(fila_valores, perfil):
    """Delimitador y trailing_delimitador son propios de cada perfil (Fase
    8.8): OPERATIVO_62 usa ',' con coma final intencional (respaldada por
    captura.csv, Fase 5.2/5.3); OFICIAL_61 usa ';' sin delimitador final
    (respaldado por un archivo de carga real vigente, Fase 8.8) -- termina
    exactamente en la ultima columna, sin campo 62 vacio."""
    delimitador = perfil.get("delimitador", ",")
    texto = delimitador.join(_celda_a_texto(v) for v in fila_valores)
    if perfil.get("trailing_delimitador", True):
        texto += delimitador
    return texto


def _verificar_cuadratura_por_movimiento(lineas, tolerancia):
    """Defensa redundante e intencional: transform.py ya verifico esto por
    movimiento; aqui se vuelve a verificar antes de escribir el archivo
    fisico, agrupando por movimiento_id. Si algun movimiento no cuadra,
    aborta la exportacion COMPLETA -- nunca un archivo parcial."""
    totales = {}
    for linea in lineas:
        t = totales.setdefault(linea["movimiento_id"], {"debe": 0, "haber": 0})
        t["debe"] += linea["debe"]
        t["haber"] += linea["haber"]
    for movimiento_id, t in totales.items():
        if abs(t["debe"] - t["haber"]) > tolerancia:
            raise ExportError(
                "DESCUADRE_EXPORTACION",
                f"movimiento_id={movimiento_id!r}: sum(debe)={t['debe']} != sum(haber)={t['haber']}.",
            )


def serializar_lineas(lineas, perfil, tolerancia=0):
    """Funcion pura: construye y valida TODAS las lineas antes de devolver
    nada. Si cualquier linea o la cuadratura global falla, no se devuelve
    contenido parcial -- se propaga la excepcion."""
    _verificar_cuadratura_por_movimiento(lineas, tolerancia)
    filas = [construir_fila(linea, perfil) for linea in lineas]
    for fila in filas:
        if len(fila) != perfil["total_columnas"]:
            raise ExportError(
                "PERFIL_LAYOUT_NO_CONFIGURADO",
                f"Fila con {len(fila)} columnas, se esperaban {perfil['total_columnas']}.",
            )
    texto_filas = [serializar_fila(f, perfil) for f in filas]
    contenido = "\r\n".join(texto_filas) + "\r\n"
    if perfil.get("con_bom"):
        # BOM UTF-8 como caracter U+FEFF al inicio del string: al codificar
        # con .encode("utf-8") produce los 3 bytes EF BB BF esperados, sin
        # necesidad de una ruta de escritura especial. Respaldado por un
        # archivo de carga real vigente en Softland (Fase 8.8): usa BOM.
        contenido = "﻿" + contenido
    return contenido


def exportar(lineas, nombre_perfil=None, layouts=None):
    """API principal. Recibe SOLO lineas ya transformadas (salida de
    transform.py, que a su vez solo produce lineas para APTO+APROBADO) --
    no reconstruye ninguna logica de aprobacion humana aqui. Falla explicito
    si 'lineas' esta vacio: nunca genera un CSV vacio en silencio (ej. si
    por error se le pasa un JSON de --preview de transform.py, que usa la
    clave 'previstos' en vez de 'transformados', o un lote sin ningun
    movimiento aprobado)."""
    if not lineas:
        raise ExportError(
            "SIN_LINEAS_QUE_EXPORTAR",
            "No hay ninguna LineaSoftland para exportar. Un JSON de 'transform.py --preview' "
            "(clave 'previstos') no es una entrada valida para la exportacion final -- esta "
            "funcion solo exporta lineas ya transformadas y aprobadas (clave 'transformados').",
        )
    layouts = layouts if layouts is not None else _cargar_layouts()
    nombre_perfil = nombre_perfil or layouts.get("perfil_default")
    perfil = _obtener_perfil(layouts, nombre_perfil)
    tolerancia = layouts.get("tolerancia_diferencia_clp", 0)
    return serializar_lineas(lineas, perfil, tolerancia)


def escribir_archivo(ruta, contenido):
    """Escritura atomica: construye en memoria primero (ya validado por
    `exportar`), escribe a un archivo temporal, y solo reemplaza el destino
    si la escritura fue exitosa. Nunca deja un CSV parcial ante error."""
    ruta = Path(ruta)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_bytes(contenido.encode("utf-8"))
    os.replace(temporal, ruta)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lineas_json", help="Salida de transform.py (lote): {'transformados': {...}, 'excluidos': [...]}")
    parser.add_argument("--perfil", default=None, help="Nombre del perfil (default: perfil_default de softland-layouts.json)")
    parser.add_argument("--layouts", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.lineas_json, encoding="utf-8") as f:
        datos = json.load(f)
    lineas = [
        linea
        for lineas_del_movimiento in datos.get("transformados", {}).values()
        for linea in lineas_del_movimiento
    ]
    layouts = _cargar_layouts(args.layouts)

    try:
        contenido = exportar(lineas, args.perfil, layouts)
    except ExportError as e:
        print(f"Exportacion abortada: {e}", file=sys.stderr)
        return 1

    escribir_archivo(args.out, contenido)
    print(f"Archivo generado: {args.out} ({len(lineas)} lineas, perfil={args.perfil or layouts.get('perfil_default')!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
