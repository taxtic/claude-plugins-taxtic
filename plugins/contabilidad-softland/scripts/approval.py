"""Capa de aprobacion humana: vive entre validate.py y la transformacion
Softland (transform.py).

Responsabilidades exclusivas:
1. preparar_revision(movimiento, resultado_validacion) -- arma el objeto
   estructurado que una futura Skill mostrara al usuario, sin recalcular
   ninguna regla contable ni reinterpretar motivos.
2. registrar_decision(...) -- valida si una decision humana (APROBADO/
   RECHAZADO) esta permitida y devuelve una NUEVA lista de decisiones.
3. La CLI persiste esas decisiones en un JSON por lote/corrida.

estado_motor (APTO/REVISION/ERROR) y estado_humano (APROBADO/RECHAZADO)
son dos fuentes de datos completamente separadas. APTO no implica
APROBADO. La capa de decision humana SOLO aplica a movimientos APTO: un
movimiento en REVISION o ERROR nunca puede recibir ninguna decision
humana, ni APROBADO ni RECHAZADO -- esta capa lo rechaza explicitamente
con un error, no lo permite ni lo corrige. Un REVISION debe corregirse y
volver a validate.py; un ERROR debe resolverse y volver a pasar por el
pipeline.

Este script NUNCA crea cuentas Softland, no genera Debe/Haber, no genera
LineaSoftland, no genera el archivo Softland final, y no modifica ni el
Movimiento ni el ResultadoValidacion que recibe como entrada.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

ESTADOS_HUMANOS_VALIDOS = ("APROBADO", "RECHAZADO")


def _clientes(movimiento):
    """Empareja ruts_banco/nombres_banco tal cual vienen en el Movimiento,
    sin inventar ni deducir asociaciones adicionales."""
    ruts = movimiento.get("ruts_banco") or []
    nombres = movimiento.get("nombres_banco") or []
    return [{"rut": r, "nombre": n} for r, n in zip_longest(ruts, nombres)]


def preparar_revision(movimiento, resultado_validacion):
    """Funcion pura. No modifica movimiento ni resultado_validacion, no
    recalcula reglas contables, no reinterpreta motivos, no cambia
    REVISION->APTO. Solo reempaqueta datos ya producidos por normalize.py
    y validate.py para que una futura Skill los presente al usuario."""
    if movimiento.get("movimiento_id") != resultado_validacion.get("movimiento_id"):
        raise ValueError(
            "movimiento y resultado_validacion no corresponden al mismo "
            f"movimiento_id ({movimiento.get('movimiento_id')!r} != "
            f"{resultado_validacion.get('movimiento_id')!r})."
        )

    return {
        "movimiento_id": movimiento["movimiento_id"],
        "fecha_pago": movimiento.get("fecha_pago"),
        "monto_abono": movimiento.get("monto_abono"),
        "origen_pago": movimiento.get("origen_pago"),
        "clientes": _clientes(movimiento),
        "asignaciones": json.loads(json.dumps(movimiento.get("asignaciones") or [])),
        "suma_asignaciones": movimiento.get("suma_asignaciones"),
        "diferencia": movimiento.get("diferencia"),
        "estado_motor": resultado_validacion.get("estado_motor"),
        "motivos": json.loads(json.dumps(resultado_validacion.get("motivos") or [])),
        "advertencias": json.loads(json.dumps(resultado_validacion.get("advertencias") or [])),
        "puede_aprobar": resultado_validacion.get("estado_motor") == "APTO",
    }


def registrar_decision(resultado_validacion, decisiones_existentes, movimiento_id, decision,
                        revisor, fecha_decision, observacion=None):
    """Funcion pura. Devuelve una NUEVA lista de decisiones; nunca muta
    decisiones_existentes ni resultado_validacion.

    resultado_validacion: el ResultadoValidacion correspondiente a
    movimiento_id (o None si ese movimiento_id no existe en el lote que se
    esta procesando -- lo resuelve el llamador, ver
    registrar_decision_en_lote()).
    """
    if decision not in ESTADOS_HUMANOS_VALIDOS:
        raise ValueError(
            f"decision invalida: {decision!r}. Solo se admite {ESTADOS_HUMANOS_VALIDOS}."
        )

    if resultado_validacion is None or resultado_validacion.get("movimiento_id") != movimiento_id:
        raise ValueError(
            f"movimiento_id={movimiento_id!r} no existe en los resultados de "
            "validacion de este lote."
        )

    if resultado_validacion.get("estado_motor") != "APTO":
        raise ValueError(
            f"No se puede registrar una decision humana para movimiento_id={movimiento_id!r}: "
            f"estado_motor={resultado_validacion.get('estado_motor')!r}. La capa de decision "
            "humana solo aplica a movimientos APTO -- un REVISION debe corregirse y volver a "
            "validate.py; un ERROR debe resolverse y volver a pasar por el pipeline."
        )

    if any(d.get("movimiento_id") == movimiento_id for d in decisiones_existentes):
        raise ValueError(
            f"Ya existe una decision registrada para movimiento_id={movimiento_id!r}. "
            "El MVP no permite sobrescribir silenciosamente: se requiere una "
            "operacion explicita de reemplazo (no implementada)."
        )

    nueva_decision = {
        "movimiento_id": movimiento_id,
        "estado_humano": decision,
        "revisor": revisor,
        "fecha_decision": fecha_decision,
        "observacion": observacion,
    }
    return [*decisiones_existentes, nueva_decision]


def crear_lote(lote_id, decisiones=None):
    if not lote_id:
        raise ValueError("lote_id es obligatorio.")
    return {"lote_id": lote_id, "decisiones": list(decisiones or [])}


def registrar_decision_en_lote(lote, resultados_validacion, movimiento_id, decision,
                                revisor, fecha_decision, observacion=None):
    """Envoltorio puro sobre registrar_decision(): busca el
    ResultadoValidacion de movimiento_id dentro de resultados_validacion (la
    lista completa del lote) y devuelve un NUEVO lote -- nunca muta `lote`
    ni `resultados_validacion`."""
    if not lote.get("lote_id"):
        raise ValueError("lote_id es obligatorio.")

    resultado = next(
        (r for r in resultados_validacion if r.get("movimiento_id") == movimiento_id), None
    )
    nuevas_decisiones = registrar_decision(
        resultado, lote.get("decisiones") or [], movimiento_id, decision,
        revisor, fecha_decision, observacion,
    )
    return {"lote_id": lote["lote_id"], "decisiones": nuevas_decisiones}


def _archivo_lote(lote_id, directorio="."):
    return Path(directorio) / f"aprobaciones-{lote_id}.json"


def _cargar_lote(lote_id, directorio="."):
    ruta = _archivo_lote(lote_id, directorio)
    if ruta.exists():
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    return crear_lote(lote_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    p_prep = sub.add_parser("preparar", help="Prepara el objeto de revision para un movimiento")
    p_prep.add_argument("movimientos_json")
    p_prep.add_argument("resultados_json")
    p_prep.add_argument("movimiento_id")
    p_prep.add_argument("--out", default=None)

    p_dec = sub.add_parser("decidir", help="Registra una decision humana en un lote")
    p_dec.add_argument("movimientos_json")
    p_dec.add_argument("resultados_json")
    p_dec.add_argument("lote_id")
    p_dec.add_argument("movimiento_id")
    p_dec.add_argument("decision", choices=list(ESTADOS_HUMANOS_VALIDOS))
    p_dec.add_argument("revisor")
    p_dec.add_argument("--observacion", default=None)
    p_dec.add_argument("--directorio", default=".", help="Directorio donde vive aprobaciones-<lote_id>.json")

    args = parser.parse_args(argv)

    with open(args.resultados_json, encoding="utf-8") as f:
        resultados = json.load(f).get("resultados", [])

    if args.comando == "preparar":
        with open(args.movimientos_json, encoding="utf-8") as f:
            movimientos = json.load(f).get("movimientos", [])
        movimiento = next((m for m in movimientos if m.get("movimiento_id") == args.movimiento_id), None)
        resultado = next((r for r in resultados if r.get("movimiento_id") == args.movimiento_id), None)
        if movimiento is None or resultado is None:
            print(f"movimiento_id={args.movimiento_id!r} no encontrado", file=sys.stderr)
            return 1
        salida = json.dumps(preparar_revision(movimiento, resultado), ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(salida, encoding="utf-8")
        else:
            print(salida)
        return 0

    if args.comando == "decidir":
        lote = _cargar_lote(args.lote_id, args.directorio)
        fecha_decision = datetime.now(timezone.utc).isoformat()
        try:
            nuevo_lote = registrar_decision_en_lote(
                lote, resultados, args.movimiento_id, args.decision,
                args.revisor, fecha_decision, args.observacion,
            )
        except ValueError as e:
            print(f"Decision rechazada: {e}", file=sys.stderr)
            return 1
        ruta = _archivo_lote(args.lote_id, args.directorio)
        ruta.write_text(json.dumps(nuevo_lote, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Decision registrada: {args.movimiento_id} -> {args.decision} (lote {args.lote_id})")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
