"""Transformacion de Movimiento + ResultadoValidacion + DecisionHumana en
LineaSoftland[].

Pipeline: Movimiento + ResultadoValidacion + DecisionHumana -> transform.py
-> LineaSoftland[]. Solo transforma movimientos con estado_motor == "APTO"
Y estado_humano == "APROBADO"; cualquier otra combinacion falla
explicitamente (defensa en profundidad, no exclusion silenciosa).

Este script NO:
- recalcula estado_motor (confia en el ResultadoValidacion recibido);
- modifica Movimiento, ResultadoValidacion ni DecisionHumana;
- serializa el archivo fisico final (delimitador/encoding/CSV/TXT);
- contiene logica de banco hardcodeada -- la cuenta Banco se resuelve
  siempre desde rules/taxtic.json; un banco no configurado produce el
  error explicito BANCO_NO_CONFIGURADO, nunca un fallback silencioso a BCI.
"""
import argparse
import json
import sys
from pathlib import Path

RULES_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "rules" / "taxtic.json"

# Posiciones oficiales de rules/softland-columns.json usadas por esta fase.
# Centralizadas aqui en un unico lugar (no dispersas como numeros magicos).
POS_CUENTA = 1
POS_DEBE = 2
POS_HABER = 3
POS_GLOSA = 4
POS_TIPO_DOCTO_CONCILIACION_BANCO = 17
POS_NRO_DOCTO_CONCILIACION_BANCO = 18
POS_AUXILIAR = 19
# Confirmado por Contabilidad (Fase 7.3): en una linea CLIENTE la posicion 20
# lleva 'TB' (marcador de conciliacion, igual significado que en Banco, solo
# que en otra columna fisica), NO el tipo de documento de la factura -- ese
# se desplaza a la posicion 24. El folio se repite en la posicion 25.
POS_TIPO_DOCTO_CONCILIACION_CLIENTE = 20
POS_NRO_DOCUMENTO = 21
POS_FECHA_EMISION = 22
POS_FECHA_VENCIMIENTO = 23
POS_TIPO_DOCUMENTO_CLIENTE = 24
POS_NRO_DOCTO_REFERENCIA_CLIENTE = 25
TOTAL_COLUMNAS_SOFTLAND = 61


class TransformError(ValueError):
    """Error explicito de transformacion, con codigo estable para tests."""
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        super().__init__(f"{codigo}: {mensaje}")


def _cargar_reglas(path=None):
    p = Path(path) if path else RULES_PATH_DEFAULT
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _validar_consistencia_ids(movimiento, resultado_validacion, decision_humana):
    movimiento_id = movimiento.get("movimiento_id")
    if resultado_validacion.get("movimiento_id") != movimiento_id:
        raise TransformError(
            "MOVIMIENTO_ID_INCONSISTENTE",
            f"ResultadoValidacion.movimiento_id={resultado_validacion.get('movimiento_id')!r} "
            f"no coincide con Movimiento.movimiento_id={movimiento_id!r}.",
        )
    if decision_humana is not None and decision_humana.get("movimiento_id") != movimiento_id:
        raise TransformError(
            "MOVIMIENTO_ID_INCONSISTENTE",
            f"DecisionHumana.movimiento_id={decision_humana.get('movimiento_id')!r} "
            f"no coincide con Movimiento.movimiento_id={movimiento_id!r}.",
        )


def _obtener_cuenta_banco(reglas, banco_codigo):
    """Resuelve la cuenta Banco EXCLUSIVAMENTE desde configuracion. Nunca
    asume BCI por fallback silencioso: si el banco del Movimiento no
    coincide con el banco configurado, falla explicitamente."""
    banco_cfg = reglas.get("banco") or {}
    if not banco_codigo or banco_codigo != banco_cfg.get("codigo"):
        raise TransformError(
            "BANCO_NO_CONFIGURADO",
            f"Movimiento.banco={banco_codigo!r} no esta configurado en rules/taxtic.json "
            f"(banco soportado en este MVP: {banco_cfg.get('codigo')!r}).",
        )
    return banco_cfg["cuenta"]


def _rut_sin_dv(rut_normalizado):
    """Confirmado por Contabilidad (Fase 8.9), con evidencia real de
    Softland: el Codigo Auxiliar de un cliente en Softland esta configurado
    SIN digito verificador -- enviar el RUT completo (con DV pegado, tal
    como lo entrega normalize.py) produce 'El Auxiliar "..." NO existe o
    esta inactivo'. rut_normalizado siempre trae el DV como ultimo
    caracter (normalize.py._normalizar_rut, sin puntos ni guion); se quita
    aqui, exclusivamente para el campo Auxiliar de Softland -- no se toca
    el RUT en ningun otro lugar (glosas, Movimiento, Asignacion)."""
    if not rut_normalizado:
        return rut_normalizado
    return rut_normalizado[:-1]


def _fecha_ddmmaaaa(fecha_iso):
    """Convierte 'YYYY-MM-DD' a 'DD/MM/AAAA'. Devuelve 0 si no hay fecha
    (regla operacional para campos no utilizados)."""
    if not fecha_iso:
        return 0
    partes = str(fecha_iso).split("-")
    if len(partes) != 3:
        return 0
    anio, mes, dia = partes
    return f"{dia}/{mes}/{anio}"


def _construir_campos_1_a_61(valores):
    """valores: dict {numero_columna(int): valor} solo para las posiciones
    con contenido real; el resto se completa con 0 -- regla operacional
    confirmada por Contabilidad para este flujo (ver rules/taxtic.json).
    softland-columns.json sigue conservando el tipo oficial del PDF sin
    modificarse; la discrepancia (ej. columnas S/N completadas con 0)
    queda para validar en la primera carga real Softland."""
    campos = {str(n): 0 for n in range(1, TOTAL_COLUMNAS_SOFTLAND + 1)}
    for numero, valor in valores.items():
        campos[str(numero)] = valor
    return campos


def _construir_glosa_banco(reglas, asignaciones):
    """Regla confirmada por Contabilidad (Fase 4.1):

    - Un solo cliente (todas las Asignacion comparten el mismo rut_cliente):
      glosas.banco.un_cliente -> 'PAGO CLIENTE {NOMBRE_CLIENTE} F{FACTURAS}'.
    - Mas de un cliente distinto (ej. Transbank multi-RUT ya resuelto por
      respaldo): glosas.banco.multicliente -> 'PAGO CLIENTE F{FACTURAS}'.
      La glosa Banco NO lleva NINGUN nombre de cliente en este caso -- no
      se inventa ningun separador para combinar nombres.

    En ambos casos los folios se concatenan en el orden de las Asignacion,
    separados por '-'. Nunca se ordenan, deduplican ni se interpretan como
    rango numerico."""
    plantillas = reglas["glosas"]["banco"]
    folios = "-".join(
        str(a.get("numero_documento")) for a in asignaciones if a.get("numero_documento") is not None
    )

    ruts_distintos = list(dict.fromkeys(
        a.get("rut_cliente") for a in asignaciones if a.get("rut_cliente")
    ))
    if len(ruts_distintos) > 1:
        return plantillas["multicliente"].replace("{FACTURAS}", folios)

    nombres_distintos = list(dict.fromkeys(
        a.get("nombre_cliente") for a in asignaciones if a.get("nombre_cliente")
    ))
    nombre = nombres_distintos[0] if nombres_distintos else ""
    return plantillas["un_cliente"].replace("{NOMBRE_CLIENTE}", nombre).replace("{FACTURAS}", folios)


def _linea_banco(movimiento, cuenta_banco, glosa, orden):
    campos = _construir_campos_1_a_61({
        POS_CUENTA: cuenta_banco,
        POS_DEBE: movimiento["monto_abono"],
        POS_HABER: 0,
        POS_GLOSA: glosa,
        POS_TIPO_DOCTO_CONCILIACION_BANCO: "TB",
        POS_NRO_DOCTO_CONCILIACION_BANCO: movimiento.get("numero_conciliacion"),
    })
    return {
        "movimiento_id": movimiento["movimiento_id"],
        "tipo_linea": "BANCO",
        "orden": orden,
        "cuenta": cuenta_banco,
        "debe": movimiento["monto_abono"],
        "haber": 0,
        "glosa": glosa,
        "auxiliar": 0,
        "tipo_documento": 0,
        "numero_documento": 0,
        "fecha_emision": 0,
        "fecha_vencimiento": 0,
        "tipo_docto_conciliacion": "TB",
        "numero_docto_conciliacion": movimiento.get("numero_conciliacion"),
        "numero_docto_referencia": 0,
        "campos_1_a_61": campos,
        "filas_excel_origen": [movimiento["fila_origen"]],
    }


def _linea_cliente(movimiento, asignacion, reglas, plantilla_glosa, orden):
    """Confirmado por Contabilidad (Fase 7.3): la linea CLIENTE lleva 'TB' en
    la posicion 20 (tipo_docto_conciliacion, mismo campo/significado que en
    Banco), el tipo de documento de la factura ('20') se desplaza a la
    posicion 24, y el folio de la factura se repite intencionalmente en la
    posicion 25 (numero_docto_referencia) ademas de la posicion 21
    (numero_documento). No es una reutilizacion de campo con significado
    falso: tipo_documento conserva su propio valor/posicion (24), y
    tipo_docto_conciliacion conserva su propio valor 'TB' (20)."""
    cuenta_cliente = reglas["cuentas"]["cliente"]
    tipo_documento = reglas["tipos_documento"]["cliente"]
    numero_documento = asignacion.get("numero_documento")
    auxiliar = _rut_sin_dv(asignacion.get("rut_cliente"))
    fecha = _fecha_ddmmaaaa(movimiento.get("fecha_pago"))
    glosa = plantilla_glosa.replace("{factura}", str(numero_documento))
    campos = _construir_campos_1_a_61({
        POS_CUENTA: cuenta_cliente,
        POS_DEBE: 0,
        POS_HABER: asignacion["monto_aplicado"],
        POS_GLOSA: glosa,
        POS_AUXILIAR: auxiliar,
        POS_TIPO_DOCTO_CONCILIACION_CLIENTE: "TB",
        POS_NRO_DOCUMENTO: numero_documento,
        POS_FECHA_EMISION: fecha,
        POS_FECHA_VENCIMIENTO: fecha,
        POS_TIPO_DOCUMENTO_CLIENTE: tipo_documento,
        POS_NRO_DOCTO_REFERENCIA_CLIENTE: numero_documento,
    })
    return {
        "movimiento_id": movimiento["movimiento_id"],
        "tipo_linea": "CLIENTE",
        "orden": orden,
        "cuenta": cuenta_cliente,
        "debe": 0,
        "haber": asignacion["monto_aplicado"],
        "glosa": glosa,
        "auxiliar": auxiliar,
        "tipo_documento": tipo_documento,
        "numero_documento": numero_documento,
        "fecha_emision": fecha,
        "fecha_vencimiento": fecha,
        "tipo_docto_conciliacion": "TB",
        "numero_docto_conciliacion": 0,
        "numero_docto_referencia": numero_documento,
        "campos_1_a_61": campos,
        "filas_excel_origen": [movimiento["fila_origen"]],
    }


def _linea_diferencia(movimiento, reglas, orden):
    cuenta = reglas["cuentas"]["diferencia_transbank"]
    auxiliar = reglas["auxiliares_fijos"]["diferencia_transbank"]
    glosa = reglas["glosas"]["diferencia_transbank"]
    diferencia = movimiento["diferencia"]
    campos = _construir_campos_1_a_61({
        POS_CUENTA: cuenta,
        POS_DEBE: diferencia,
        POS_HABER: 0,
        POS_GLOSA: glosa,
        POS_AUXILIAR: auxiliar,
    })
    return {
        "movimiento_id": movimiento["movimiento_id"],
        "tipo_linea": "DIFERENCIA_TRANSBANK",
        "orden": orden,
        "cuenta": cuenta,
        "debe": diferencia,
        "haber": 0,
        "glosa": glosa,
        "auxiliar": auxiliar,
        "tipo_documento": 0,
        "numero_documento": 0,
        "fecha_emision": 0,
        "fecha_vencimiento": 0,
        "tipo_docto_conciliacion": 0,
        "numero_docto_conciliacion": 0,
        "numero_docto_referencia": 0,
        "campos_1_a_61": campos,
        "filas_excel_origen": [movimiento["fila_origen"]],
    }


def _verificar_cuadratura(lineas, tolerancia=0):
    total_debe = sum(l["debe"] for l in lineas)
    total_haber = sum(l["haber"] for l in lineas)
    if abs(total_debe - total_haber) > tolerancia:
        raise TransformError(
            "DESCUADRE_INTERNO",
            f"sum(debe)={total_debe} != sum(haber)={total_haber} para movimiento_id="
            f"{lineas[0]['movimiento_id'] if lineas else '?'!r}.",
        )


def transformar_movimiento(movimiento, resultado_validacion, decision_humana, reglas):
    """Funcion pura. No modifica movimiento, resultado_validacion ni
    decision_humana. Falla explicitamente (TransformError) ante cualquier
    guardia no satisfecha; nunca excluye silenciosamente ni devuelve
    lineas parciales."""
    _validar_consistencia_ids(movimiento, resultado_validacion, decision_humana)

    if resultado_validacion.get("estado_motor") != "APTO":
        raise TransformError(
            "ESTADO_MOTOR_NO_APTO",
            f"estado_motor={resultado_validacion.get('estado_motor')!r}; "
            "solo un movimiento APTO puede transformarse.",
        )

    if decision_humana is None:
        raise TransformError(
            "SIN_DECISION_HUMANA",
            "No existe DecisionHumana registrada para este movimiento_id.",
        )

    if decision_humana.get("estado_humano") != "APROBADO":
        raise TransformError(
            "NO_APROBADO",
            f"estado_humano={decision_humana.get('estado_humano')!r}; "
            "solo un movimiento APROBADO puede transformarse.",
        )

    cuenta_banco = _obtener_cuenta_banco(reglas, movimiento.get("banco"))
    asignaciones = movimiento.get("asignaciones") or []
    es_transbank = resultado_validacion.get("tipo_pago") == "TRANSBANK"

    lineas = []
    orden = 1

    glosa_banco = _construir_glosa_banco(reglas, asignaciones)
    lineas.append(_linea_banco(movimiento, cuenta_banco, glosa_banco, orden))
    orden += 1

    plantilla_cliente = (
        reglas["glosas"]["cliente_transbank"] if es_transbank else reglas["glosas"]["cliente_normal"]
    )
    for asignacion in asignaciones:
        lineas.append(_linea_cliente(movimiento, asignacion, reglas, plantilla_cliente, orden))
        orden += 1

    if es_transbank:
        lineas.append(_linea_diferencia(movimiento, reglas, orden))
        orden += 1

    _verificar_cuadratura(lineas, reglas.get("tolerancia_diferencia_clp", 0))

    return lineas


def transformar_lote(movimientos, resultados_validacion, decisiones, reglas):
    """Envoltorio de lote. Nunca produce lineas para movimientos no
    aprobados: cualquier TransformError se clasifica como excluido, nunca
    se propaga a `transformados` de forma parcial."""
    resultados_por_id = {r["movimiento_id"]: r for r in resultados_validacion}
    decisiones_por_id = {d["movimiento_id"]: d for d in decisiones}

    transformados = {}
    excluidos = []
    for movimiento in movimientos:
        movimiento_id = movimiento["movimiento_id"]
        resultado = resultados_por_id.get(movimiento_id)
        if resultado is None:
            excluidos.append({"movimiento_id": movimiento_id, "motivo": "SIN_RESULTADO_VALIDACION"})
            continue
        decision = decisiones_por_id.get(movimiento_id)
        try:
            lineas = transformar_movimiento(movimiento, resultado, decision, reglas)
        except TransformError as e:
            excluidos.append({"movimiento_id": movimiento_id, "motivo": e.codigo})
            continue
        transformados[movimiento_id] = lineas

    return {"transformados": transformados, "excluidos": excluidos}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("movimientos_json")
    parser.add_argument("resultados_json")
    parser.add_argument("lote_id")
    parser.add_argument("--directorio", default=".", help="Directorio con aprobaciones-<lote_id>.json")
    parser.add_argument("--reglas", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    with open(args.movimientos_json, encoding="utf-8") as f:
        movimientos = json.load(f).get("movimientos", [])
    with open(args.resultados_json, encoding="utf-8") as f:
        resultados = json.load(f).get("resultados", [])
    ruta_lote = Path(args.directorio) / f"aprobaciones-{args.lote_id}.json"
    decisiones = []
    if ruta_lote.exists():
        with open(ruta_lote, encoding="utf-8") as f:
            decisiones = json.load(f).get("decisiones", [])
    reglas = _cargar_reglas(args.reglas)

    resultado = transformar_lote(movimientos, resultados, decisiones, reglas)
    salida = json.dumps(resultado, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(salida, encoding="utf-8")
        print(f"Movimientos transformados: {len(resultado['transformados'])}")
        print(f"Excluidos: {len(resultado['excluidos'])}")
    else:
        print(salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
