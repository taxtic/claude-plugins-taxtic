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


class RevisionError(ValueError):
    """Error explicito de armado de revision humana, con codigo estable para
    tests (mismo patron que TransformError/ExportError/ConsistenciaError)."""
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        super().__init__(f"{codigo}: {mensaje}")


def _cargar_lineas_previstas(preview_path, movimiento_id):
    """Carga previstos[movimiento_id] desde un JSON de 'transform.py
    --preview' para complementar el objeto de revision con las lineas
    contables reales. Falla duro (RevisionError) -- nunca cae a null ni
    permite continuar sin lineas reales -- si el archivo no tiene la
    estructura esperada, si el movimiento no esta en 'previstos', o si
    tiene cero lineas."""
    with open(preview_path, encoding="utf-8") as f:
        datos = json.load(f)
    if not isinstance(datos, dict) or "previstos" not in datos:
        raise RevisionError(
            "PREVIEW_INVALIDO",
            f"El archivo {preview_path!r} no tiene la clave 'previstos' esperada "
            "de 'transform.py --preview'.",
        )
    previstos = datos["previstos"]
    if movimiento_id not in previstos:
        raise RevisionError(
            "MOVIMIENTO_NO_ENCONTRADO_EN_PREVIEW",
            f"movimiento_id={movimiento_id!r} no existe en 'previstos' de {preview_path!r}.",
        )
    lineas = previstos[movimiento_id]
    if not lineas:
        raise RevisionError(
            "SIN_LINEAS_PREVISTAS",
            f"movimiento_id={movimiento_id!r} tiene 0 lineas en 'previstos' -- no se puede "
            "armar la revision sin lineas contables reales.",
        )
    return lineas


def _clientes(movimiento):
    """Empareja ruts_banco/nombres_banco tal cual vienen en el Movimiento,
    sin inventar ni deducir asociaciones adicionales."""
    ruts = movimiento.get("ruts_banco") or []
    nombres = movimiento.get("nombres_banco") or []
    return [{"rut": r, "nombre": n} for r, n in zip_longest(ruts, nombres)]


def preparar_revision(movimiento, resultado_validacion, lineas_previstas=None):
    """Funcion pura. No modifica movimiento ni resultado_validacion, no
    recalcula reglas contables, no reinterpreta motivos, no cambia
    REVISION->APTO. Solo reempaqueta datos ya producidos por normalize.py
    y validate.py para que una futura Skill los presente al usuario.

    lineas_previstas (opcional): LineaSoftland[] ya calculadas por
    'transform.py --preview' (ver _cargar_lineas_previstas). Si se entrega,
    se copian TAL CUAL (sin recalcular, reformatear ni normalizar ningun
    valor) bajo la clave 'lineas_previstas', complementando este objeto en
    vez de duplicar un segundo artefacto -- este script sigue sin generar
    ni una sola cuenta, glosa, auxiliar o Debe/Haber por su cuenta.

    Incluye ademas 'banco', 'descripcion_banco', 'tipo_pago' y
    'cuadratura_exacta' -- datos que ya recibe como argumento (de
    `movimiento`/`resultado_validacion`) pero que antes no se reempaquetaban
    aqui, obligando a la Skill a abrir 02_normalizado.json/03_validado.json
    por separado solo para mostrarlos en la revision humana. No se agrega
    'numero_conciliacion': ya viaja dentro de cada linea de
    'lineas_previstas' (campo 'numero_docto_conciliacion' de la linea
    BANCO), duplicarlo aqui no aportaria nada nuevo."""
    if movimiento.get("movimiento_id") != resultado_validacion.get("movimiento_id"):
        raise ValueError(
            "movimiento y resultado_validacion no corresponden al mismo "
            f"movimiento_id ({movimiento.get('movimiento_id')!r} != "
            f"{resultado_validacion.get('movimiento_id')!r})."
        )

    resultado = {
        "movimiento_id": movimiento["movimiento_id"],
        "fecha_pago": movimiento.get("fecha_pago"),
        "banco": movimiento.get("banco"),
        "monto_abono": movimiento.get("monto_abono"),
        "origen_pago": movimiento.get("origen_pago"),
        "descripcion_banco": movimiento.get("descripcion_banco"),
        "clientes": _clientes(movimiento),
        "asignaciones": json.loads(json.dumps(movimiento.get("asignaciones") or [])),
        "suma_asignaciones": movimiento.get("suma_asignaciones"),
        "diferencia": movimiento.get("diferencia"),
        "estado_motor": resultado_validacion.get("estado_motor"),
        "tipo_pago": resultado_validacion.get("tipo_pago"),
        "cuadratura_exacta": (resultado_validacion.get("validaciones") or {}).get("cuadratura_exacta"),
        "motivos": json.loads(json.dumps(resultado_validacion.get("motivos") or [])),
        "advertencias": json.loads(json.dumps(resultado_validacion.get("advertencias") or [])),
        "puede_aprobar": resultado_validacion.get("estado_motor") == "APTO",
    }
    if lineas_previstas is not None:
        resultado["lineas_previstas"] = json.loads(json.dumps(lineas_previstas))
    return resultado


def formatear_revision_humana(revision):
    """Funcion pura: convierte el objeto de preparar_revision() en UN bloque
    de texto plano, ya armado, listo para mostrarse verbatim al usuario.

    Este es el UNICO lugar que decide como se presenta la revision humana --
    ninguna Skill/agente debe reconstruir esta presentacion por su cuenta
    (ni con ConvertFrom-Json + Write-Host, ni recorriendo lineas_previstas a
    mano, ni con ninguna otra logica de formato en la conversacion). No
    recalcula, reformatea ni normaliza ningun valor: cada campo (incluida
    cada glosa, y cada campo de cada Asignacion) se imprime exactamente como
    viene en `revision` -- incluye una seccion 'Asignaciones:' con los
    campos reales de `revision['asignaciones']` (tipo_documento,
    numero_documento, monto_aplicado, rut_cliente, requiere_revision,
    motivo_revision, fuente_respaldo, entre otros), independiente de
    `lineas_previstas`."""
    filas = []
    filas.append(f"Movimiento: {revision.get('movimiento_id')}")
    filas.append(f"Fecha de pago: {revision.get('fecha_pago')}")
    filas.append(f"Banco: {revision.get('banco')}")
    filas.append(f"Monto abono: {revision.get('monto_abono')}")
    filas.append(f"Origen del pago: {revision.get('origen_pago')}")
    filas.append(f"Descripcion bancaria: {revision.get('descripcion_banco')}")
    filas.append(f"Estado motor: {revision.get('estado_motor')}")
    filas.append(f"Tipo de pago: {revision.get('tipo_pago')}")
    filas.append(f"Cuadratura exacta: {revision.get('cuadratura_exacta')}")
    filas.append(f"Suma asignaciones: {revision.get('suma_asignaciones')}")
    filas.append(f"Diferencia: {revision.get('diferencia')}")
    filas.append(f"Puede aprobar: {revision.get('puede_aprobar')}")

    filas.append("")
    clientes = revision.get("clientes") or []
    if not clientes:
        filas.append("Clientes: (ninguno)")
    else:
        filas.append("Clientes (RUT / nombre):")
        for cliente in clientes:
            nombre = cliente.get("nombre")
            if nombre is None:
                filas.append(
                    f"  - RUT {cliente.get('rut')}: nombre no informado en el Excel y no inferido."
                )
            else:
                filas.append(f"  - RUT {cliente.get('rut')}: {nombre}")

    filas.append("")
    asignaciones = revision.get("asignaciones") or []
    if not asignaciones:
        filas.append("Asignaciones: (ninguna)")
    else:
        filas.append("Asignaciones:")
        for asignacion in asignaciones:
            filas.append(f"  - bloque_indice={asignacion.get('bloque_indice')}")
            filas.append(f"    tipo_documento={asignacion.get('tipo_documento')}")
            filas.append(f"    numero_documento={asignacion.get('numero_documento')}")
            filas.append(f"    monto_aplicado={asignacion.get('monto_aplicado')}")
            filas.append(f"    rut_cliente={asignacion.get('rut_cliente')}")
            filas.append(f"    nombre_cliente={asignacion.get('nombre_cliente')}")
            filas.append(f"    categoria_ingreso={asignacion.get('categoria_ingreso')}")
            filas.append(f"    texto_original_celda={asignacion.get('texto_original_celda')}")
            filas.append(f"    requiere_revision={asignacion.get('requiere_revision')}")
            filas.append(f"    motivo_revision={asignacion.get('motivo_revision')}")
            filas.append(f"    fuente_respaldo={asignacion.get('fuente_respaldo')}")

    motivos = revision.get("motivos") or []
    if motivos:
        filas.append("")
        filas.append("Motivos:")
        for motivo in motivos:
            filas.append(f"  - [{motivo.get('severidad')}] {motivo.get('codigo')}: {motivo.get('mensaje')}")

    advertencias = revision.get("advertencias") or []
    if advertencias:
        filas.append("")
        filas.append("Advertencias:")
        for advertencia in advertencias:
            filas.append(f"  - {advertencia.get('codigo')}: {advertencia.get('mensaje')}")

    filas.append("")
    lineas_previstas = revision.get("lineas_previstas")
    if lineas_previstas is None:
        filas.append("Lineas contables previstas: (no disponibles -- no se entrego --preview)")
    else:
        filas.append("Lineas contables PREVISTAS (verbatim, sin recalcular):")
        for indice, linea in enumerate(lineas_previstas, start=1):
            filas.append(f"  Linea {indice} [{linea.get('tipo_linea')}]:")
            filas.append(f"    cuenta={linea.get('cuenta')}  debe={linea.get('debe')}  haber={linea.get('haber')}")
            filas.append(f"    glosa={linea.get('glosa')}")
            filas.append(
                f"    auxiliar={linea.get('auxiliar')}  tipo_documento={linea.get('tipo_documento')}  "
                f"numero_documento={linea.get('numero_documento')}"
            )
            filas.append(
                f"    fecha_emision={linea.get('fecha_emision')}  "
                f"fecha_vencimiento={linea.get('fecha_vencimiento')}"
            )
            filas.append(
                f"    tipo_docto_conciliacion={linea.get('tipo_docto_conciliacion')}  "
                f"numero_docto_conciliacion={linea.get('numero_docto_conciliacion')}  "
                f"numero_docto_referencia={linea.get('numero_docto_referencia')}"
            )

    return "\n".join(filas)


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
    p_prep.add_argument(
        "--preview", default=None,
        help="Salida de 'transform.py --preview' (04_preview.json). Si se entrega, "
             "agrega 'lineas_previstas' al objeto de revision, copiadas tal cual desde "
             "el preview. Falla duro (sin generar salida) si el archivo no tiene la "
             "estructura esperada, si el movimiento_id no esta en 'previstos', o si "
             "tiene cero lineas -- nunca cae a null.",
    )
    p_prep.add_argument("--out", default=None, help="Ruta de salida JSON (objeto de preparar_revision())")
    p_prep.add_argument(
        "--out-texto", default=None,
        help="Ruta de salida de TEXTO plano ya armado (formatear_revision_humana()), listo para "
             "mostrarse verbatim al usuario -- evita que la Skill tenga que interpretar el JSON "
             "para construir la presentacion (ConvertFrom-Json, Write-Host, loops, etc.).",
    )

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

        lineas_previstas = None
        if args.preview:
            try:
                lineas_previstas = _cargar_lineas_previstas(args.preview, args.movimiento_id)
            except RevisionError as e:
                print(f"Revision abortada: {e}", file=sys.stderr)
                return 1

        revision = preparar_revision(movimiento, resultado, lineas_previstas)
        salida = json.dumps(revision, ensure_ascii=False, indent=2)

        if args.out_texto:
            Path(args.out_texto).write_text(formatear_revision_humana(revision), encoding="utf-8")

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
