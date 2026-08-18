"""Motor de validacion: toma Movimiento[] ya normalizados (salida de
normalize.py) y produce un ResultadoValidacion por Movimiento.

No modifica el Movimiento de entrada. No genera cuentas Softland, Debe/Haber,
LineaSoftland, archivos finales ni aprobacion humana -- eso pertenece a
fases posteriores (transform.py / export_softland.py / aprobacion).

estado_motor admite exclusivamente APTO / REVISION / ERROR. No existe
APROBADO: la aprobacion humana es una fase distinta que compara su propia
decision contra este resultado, nunca al reves.

Precedencia: ERROR domina REVISION, REVISION domina APTO. Un Movimiento sin
ningun motivo de severidad ERROR o REVISION es APTO. Las advertencias nunca
cambian estado_motor por si solas.
"""
import argparse
import json
import sys
from pathlib import Path

RULES_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "rules" / "validation-rules.json"


def _cargar_reglas(path=None):
    p = Path(path) if path else RULES_PATH_DEFAULT
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _motivo(codigo, severidad, mensaje, campo=None):
    return {"codigo": codigo, "severidad": severidad, "mensaje": mensaje, "campo": campo}


def _es_numero_positivo(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor > 0


def _es_respaldo_transbank_valido(respaldo):
    """'Verificable' es puramente estructural: un objeto {tipo, referencia,
    verificado} que una fase anterior ya dejo marcado como resuelto.
    validate.py NUNCA abre ni comprueba ningun documento externo (email/PDF/
    reporte Transbank) -- solo confia en esta marca; la verificacion real es
    responsabilidad de una fase de ingesta/resolucion futura, aun no
    implementada. Un string suelto (contrato anterior a Fase 2.1) ya no
    cuenta como respaldo valido."""
    if not isinstance(respaldo, dict):
        return False
    if respaldo.get("tipo") != "TRANSBANK":
        return False
    if respaldo.get("verificado") is not True:
        return False
    referencia = respaldo.get("referencia")
    return isinstance(referencia, str) and referencia.strip() != ""


def _referencia_respaldo(respaldo):
    return respaldo.get("referencia") if isinstance(respaldo, dict) else None


def _mapear_error_normalizacion(err):
    campo = err.get("campo") or ""
    if campo == "fecha_pago":
        return "FECHA_INVALIDA"
    if campo == "monto_abono":
        return "MONTO_ABONO_INVALIDO"
    if campo == "ruts_banco":
        return "RUT_ASIGNACION_AUSENTE"
    if campo.startswith("asignaciones[") and campo.endswith(".monto_aplicado"):
        return "MONTO_ASIGNACION_INVALIDO"
    return "ERROR_NORMALIZACION"


def _determinar_tipo_pago(movimiento, diferencia):
    asignaciones = movimiento.get("asignaciones") or []
    if not asignaciones:
        return "DESCONOCIDO"
    if movimiento.get("origen_pago") == "TRANSBANK" and diferencia != 0:
        return "TRANSBANK"
    if len(asignaciones) == 1:
        return "SIMPLE"
    return "MULTIFACTURA"


def _precedencia(motivos):
    severidades = {m["severidad"] for m in motivos}
    if "ERROR" in severidades:
        return "ERROR"
    if "REVISION" in severidades:
        return "REVISION"
    return "APTO"


def validar_movimiento(movimiento, reglas=None):
    """Funcion pura: no muta `movimiento`, no depende de filesystem/red/reloj."""
    reglas = reglas or {}
    tolerancia = reglas.get("tolerancia_diferencia_clp", 0)

    motivos = []
    advertencias = list(movimiento.get("advertencias") or [])
    validaciones = {}

    errores_normalizacion = movimiento.get("errores_normalizacion") or []
    senales_revision = movimiento.get("senales_revision") or []
    asignaciones = movimiento.get("asignaciones") or []
    ruts_banco = movimiento.get("ruts_banco") or []
    monto_abono = movimiento.get("monto_abono")
    suma_asignaciones = movimiento.get("suma_asignaciones") or 0
    diferencia = movimiento.get("diferencia") or 0
    origen_pago = movimiento.get("origen_pago")
    respaldo_diferencia = movimiento.get("respaldo_diferencia")

    # I. errores_normalizacion -> ERROR directo (fecha/monto/estructura invalidos)
    for err in errores_normalizacion:
        codigo = _mapear_error_normalizacion(err)
        motivos.append(_motivo(codigo, "ERROR", err.get("mensaje", ""), err.get("campo")))

    # J. datos esenciales del Movimiento (defensivo: cubre casos que
    # errores_normalizacion no marca hoy, ej. monto_abono <= 0, banco ausente)
    validaciones["fecha_valida"] = movimiento.get("fecha_pago") is not None
    validaciones["monto_abono_valido"] = _es_numero_positivo(monto_abono)
    if not validaciones["monto_abono_valido"] and not any(
        m["codigo"] == "MONTO_ABONO_INVALIDO" for m in motivos
    ):
        motivos.append(_motivo(
            "MONTO_ABONO_INVALIDO", "ERROR",
            "monto_abono debe ser un numero mayor a 0", "monto_abono",
        ))
    if not movimiento.get("banco"):
        motivos.append(_motivo("ERROR_NORMALIZACION", "ERROR", "banco ausente", "banco"))

    # G. sin asignaciones -> REVISION (nunca ERROR, nunca se inventa factura)
    if not asignaciones:
        motivos.append(_motivo(
            "SIN_ASIGNACIONES", "REVISION",
            "El movimiento no trae ningun documento/asignacion asociado.", "asignaciones",
        ))
    else:
        for a in asignaciones:
            campo_base = f"asignaciones[{a.get('bloque_indice')}]"

            # E. multiples RUT sin atribucion explicita -> REVISION, no ERROR
            if a.get("rut_cliente") is None and len(ruts_banco) > 1:
                motivos.append(_motivo(
                    "MULTIPLES_RUT_SIN_ASOCIACION", "REVISION",
                    "Mas de un RUT en el movimiento; esta asignacion no tiene RUT atribuido explicitamente.",
                    f"{campo_base}.rut_cliente",
                ))

            # J. documento ausente en una asignacion que no fue senalizada por normalize.py
            if a.get("numero_documento") is None and not a.get("requiere_revision"):
                motivos.append(_motivo(
                    "DOCUMENTO_ASIGNACION_AUSENTE", "ERROR",
                    "La asignacion no tiene numero_documento y no fue marcada para revision.",
                    f"{campo_base}.numero_documento",
                ))

            # J. monto de la asignacion invalido
            if not _es_numero_positivo(a.get("monto_aplicado")):
                motivos.append(_motivo(
                    "MONTO_ASIGNACION_INVALIDO", "ERROR",
                    "monto_aplicado debe ser un numero mayor a 0.",
                    f"{campo_base}.monto_aplicado",
                ))

            # F. textos especiales / boletas -> REVISION, nunca ERROR ni factura normal
            if a.get("tipo_documento") == "BOLETA":
                motivos.append(_motivo(
                    "BOLETA_NO_SOPORTADA_MVP", "REVISION",
                    "Boleta detectada; el MVP no implementa tratamiento automatico de boletas.",
                    f"{campo_base}.tipo_documento",
                ))
            elif a.get("requiere_revision"):
                motivos.append(_motivo(
                    "DOCUMENTO_REQUIERE_REVISION", "REVISION",
                    "El texto de la asignacion no es un folio interpretable automaticamente.",
                    f"{campo_base}.texto_original_celda",
                ))

    # C/D/K/L. cuadratura y diferencia
    cuadra_exacto = abs(diferencia) <= tolerancia
    validaciones["cuadratura_exacta"] = cuadra_exacto
    respaldo_transbank_valido = None
    if not cuadra_exacto:
        respaldo_ok = _es_respaldo_transbank_valido(respaldo_diferencia)
        referencia = _referencia_respaldo(respaldo_diferencia)

        asignaciones_con_rut = bool(asignaciones) and all(
            a.get("rut_cliente") is not None for a in asignaciones
        )
        asignaciones_respaldadas = True
        if asignaciones and len(ruts_banco) > 1:
            # Multi-RUT: no basta con que rut_cliente este resuelto -- cada
            # asignacion resuelta por respaldo debe apuntar exactamente a la
            # misma referencia. Nunca se empareja por posicion/orden/monto.
            asignaciones_respaldadas = referencia is not None and all(
                a.get("fuente_respaldo") == referencia for a in asignaciones
            )
            if not asignaciones_respaldadas:
                motivos.append(_motivo(
                    "ASIGNACION_RESPALDO_NO_COINCIDE", "REVISION",
                    "Hay mas de un RUT en el movimiento y al menos una asignacion no tiene "
                    "fuente_respaldo igual a la referencia del respaldo del movimiento.",
                    "asignaciones",
                ))

        es_transbank_respaldado = (
            origen_pago == "TRANSBANK"
            and diferencia > 0
            and respaldo_ok
            and asignaciones_con_rut
            and asignaciones_respaldadas
            and (suma_asignaciones - (monto_abono or 0)) == diferencia
        )
        if es_transbank_respaldado:
            respaldo_transbank_valido = True
            motivos.append(_motivo(
                "DIFERENCIA_TRANSBANK_RESPALDADA", "INFO",
                "Diferencia Transbank con respaldo estructuralmente verificado y asignaciones resueltas explicitamente.",
                "diferencia",
            ))
        else:
            respaldo_transbank_valido = False
            motivos.append(_motivo(
                "DIFERENCIA_SIN_RESPALDO", "REVISION",
                "Existe una diferencia entre monto_abono y suma_asignaciones sin respaldo estructuralmente verificado.",
                "diferencia",
            ))
    validaciones["respaldo_transbank_valido"] = respaldo_transbank_valido

    # Cualquier otra senal de revision de normalize.py no cubierta explicitamente arriba
    # (ej. COLUMNA_NO_RECONOCIDA_CON_DATOS) escala a REVISION generica -- nunca se descarta.
    codigos_ya_cubiertos = {
        "SIN_ASIGNACIONES", "TEXTO_NO_FACTURA", "BOLETA_DETECTADA",
        "MULTIPLES_RUT_SIN_ASOCIACION_EXPLICITA",
    }
    for s in senales_revision:
        if s.get("codigo") in codigos_ya_cubiertos:
            continue
        motivos.append(_motivo(s["codigo"], "REVISION", s.get("mensaje", ""), s.get("campo")))

    estado_motor = _precedencia(motivos)
    tipo_pago = _determinar_tipo_pago(movimiento, diferencia)

    return {
        "movimiento_id": movimiento["movimiento_id"],
        "estado_motor": estado_motor,
        "tipo_pago": tipo_pago,
        "motivos": motivos,
        "advertencias": advertencias,
        "validaciones": validaciones,
        "montos": {
            "monto_abono": monto_abono,
            "suma_asignaciones": suma_asignaciones,
            "diferencia": diferencia,
            "diferencia_respaldada": respaldo_transbank_valido is True,
        },
    }


def validar(movimientos, reglas=None):
    reglas = reglas or {}
    return [validar_movimiento(m, reglas) for m in movimientos]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("movimientos_json", help="Salida de normalize.py")
    parser.add_argument("--reglas", default=None, help="Ruta a validation-rules.json (default: rules/validation-rules.json del plugin)")
    parser.add_argument("--out", default=None, help="Ruta de salida JSON (default: stdout)")
    args = parser.parse_args(argv)

    with open(args.movimientos_json, encoding="utf-8") as f:
        entrada = json.load(f)
    reglas = _cargar_reglas(args.reglas)

    resultados = validar(entrada.get("movimientos", []), reglas)
    salida = json.dumps({"resultados": resultados}, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(salida, encoding="utf-8")
        conteo = {"APTO": 0, "REVISION": 0, "ERROR": 0}
        for r in resultados:
            conteo[r["estado_motor"]] += 1
        print(f"Movimientos validados: {len(resultados)}")
        print(f"APTO={conteo['APTO']} REVISION={conteo['REVISION']} ERROR={conteo['ERROR']}")
    else:
        print(salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
