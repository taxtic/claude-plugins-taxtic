"""Normalizacion de movimientos candidatos (salida de read_excel.py) a
Movimiento + Asignacion canonicos.

No decide estado_motor (APTO/REVISION/ERROR): eso es responsabilidad de una
fase futura (validate.py, aun no implementada). Esta etapa solo normaliza
datos y deja evidencia estructurada (advertencias, senales_revision,
errores_normalizacion) para que esa fase futura decida.

No genera cuentas Softland, no genera Debe/Haber, y no asigna RUT a factura
por heuristica o posicion cuando una fila trae mas de un RUT sin forma
estructural de resolver la atribucion.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

RULES_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "rules" / "validation-rules.json"

_FOLIO_RE = re.compile(r"^\s*(\d+)\s*(.*)$")
_BOLETA_RE = re.compile(r"^\s*BOLETA\s+(\d+)\s*$", re.IGNORECASE)


def _cargar_reglas(path=None):
    p = Path(path) if path else RULES_PATH_DEFAULT
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _quitar_tildes(texto):
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalizar_texto_comparacion(texto):
    return _quitar_tildes(str(texto)).strip().upper()


def _normalizar_fecha(valor):
    """Devuelve (fecha_iso_o_none, error_o_none)."""
    if valor in (None, ""):
        return None, "FECHA_AUSENTE"
    if isinstance(valor, (datetime, date)):
        if isinstance(valor, datetime):
            return valor.date().isoformat(), None
        return valor.isoformat(), None
    if isinstance(valor, str):
        texto = valor.strip()
        try:
            return datetime.fromisoformat(texto).date().isoformat(), None
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto, fmt).date().isoformat(), None
            except ValueError:
                continue
        return None, "FECHA_NO_PARSEABLE"
    return None, "FECHA_NO_PARSEABLE"


def _normalizar_monto(valor):
    """Devuelve (monto_o_none, error_o_none)."""
    if valor in (None, ""):
        return None, "MONTO_AUSENTE"
    if isinstance(valor, (int, float)):
        return valor, None
    if isinstance(valor, str):
        texto = valor.strip().replace(".", "").replace(",", ".")
        try:
            return float(texto) if "." in texto else int(texto), None
        except ValueError:
            return None, "MONTO_NO_PARSEABLE"
    return None, "MONTO_NO_PARSEABLE"


def _normalizar_rut(rut_crudo):
    """Quita puntos, espacios y guion; conserva DV (incluye K/k -> K)."""
    if rut_crudo in (None, ""):
        return None
    texto = str(rut_crudo).strip().upper()
    texto = texto.replace(".", "").replace(" ", "").replace("-", "")
    return texto or None


def _dividir_multivalor(texto_crudo, separador):
    if texto_crudo in (None, ""):
        return []
    partes = [p.strip() for p in str(texto_crudo).split(separador)]
    return [p for p in partes if p != ""]


def _es_no_disponible(valor, valores_no_disponibles):
    return isinstance(valor, str) and valor.strip().upper() in {
        v.upper() for v in valores_no_disponibles
    }


def _clasificar_texto_factura(texto_crudo, patrones_no_factura):
    """Devuelve dict con tipo_documento, numero_documento,
    requiere_revision, motivo_revision -- sin decidir tratamiento contable."""
    if texto_crudo in (None, ""):
        return {
            "tipo_documento": "DESCONOCIDO",
            "numero_documento": None,
            "requiere_revision": True,
            "motivo_revision": "TEXTO_NO_FACTURA",
        }

    if isinstance(texto_crudo, (int, float)):
        return {
            "tipo_documento": "FACTURA",
            "numero_documento": int(texto_crudo),
            "requiere_revision": False,
            "motivo_revision": None,
        }

    texto = str(texto_crudo).strip()
    texto_norm = _normalizar_texto_comparacion(texto)

    for patron in patrones_no_factura:
        if _normalizar_texto_comparacion(patron) == texto_norm:
            return {
                "tipo_documento": "DESCONOCIDO",
                "numero_documento": None,
                "requiere_revision": True,
                "motivo_revision": "TEXTO_NO_FACTURA",
            }

    m_boleta = _BOLETA_RE.match(texto)
    if m_boleta:
        return {
            "tipo_documento": "BOLETA",
            "numero_documento": int(m_boleta.group(1)),
            "requiere_revision": True,
            "motivo_revision": "BOLETA_DETECTADA",
        }

    m_folio = _FOLIO_RE.match(texto)
    if m_folio:
        return {
            "tipo_documento": "FACTURA",
            "numero_documento": int(m_folio.group(1)),
            "requiere_revision": False,
            "motivo_revision": None,
        }

    return {
        "tipo_documento": "DESCONOCIDO",
        "numero_documento": None,
        "requiere_revision": True,
        "motivo_revision": "TEXTO_NO_FACTURA",
    }


def _detectar_origen_pago(texto_crudo):
    if texto_crudo in (None, ""):
        return "DESCONOCIDO"
    texto = _normalizar_texto_comparacion(texto_crudo)
    if "TRANSBANK" in texto:
        return "TRANSBANK"
    if "TRANSFERENCIA" in texto:
        return "TRANSFERENCIA"
    return "OTRO"


def normalizar_movimiento(candidato, reglas, banco_codigo="BCI"):
    campos = candidato["campos_fijos"]
    separador = reglas.get("separador_multivalor", "/")
    valores_na = reglas.get("valores_no_disponibles", ["#N/A"])
    patrones_no_factura = reglas.get("patrones_no_factura", [])

    advertencias = []
    senales_revision = []
    errores_normalizacion = []

    fecha_pago, err_fecha = _normalizar_fecha(campos.get("fecha"))
    if err_fecha:
        errores_normalizacion.append({"codigo": err_fecha, "campo": "fecha_pago", "mensaje": f"No fue posible normalizar la fecha: {campos.get('fecha')!r}"})

    monto_abono, err_monto = _normalizar_monto(campos.get("abonos"))
    if err_monto:
        errores_normalizacion.append({"codigo": err_monto, "campo": "monto_abono", "mensaje": f"No fue posible normalizar el monto de abono: {campos.get('abonos')!r}"})

    rut_crudo = campos.get("rut_banco_crudo")
    if _es_no_disponible(rut_crudo, valores_na):
        ruts_crudos = [rut_crudo]
    else:
        ruts_crudos = _dividir_multivalor(rut_crudo, separador)
    ruts_banco = [_normalizar_rut(r) for r in ruts_crudos]

    proveedor_crudo = campos.get("proveedor_cliente_banco_crudo")
    if _es_no_disponible(proveedor_crudo, valores_na):
        nombres_banco = [proveedor_crudo]
    else:
        nombres_banco = _dividir_multivalor(proveedor_crudo, separador)
    for idx, nombre in enumerate(nombres_banco):
        if _es_no_disponible(nombre, valores_na):
            advertencias.append({
                "codigo": "PROVEEDOR_NO_RESUELTO",
                "campo": f"nombres_banco[{idx}]",
                "mensaje": "PROVEEDOR/CLIENTE llego como #N/A (VLOOKUP externo no resuelto). No es un dato esencial para el movimiento.",
            })

    if len(ruts_banco) == 0:
        errores_normalizacion.append({"codigo": "RUT_AUSENTE", "campo": "ruts_banco", "mensaje": "La fila no trae ningun RUT en la columna R.U.T."})
    elif len(ruts_banco) > 1:
        senales_revision.append({
            "codigo": "MULTIPLES_RUT_SIN_ASOCIACION_EXPLICITA",
            "campo": "ruts_banco",
            "mensaje": f"La fila trae {len(ruts_banco)} RUT distintos y no existe forma estructural de atribuir cada asignacion a un RUT especifico sin un documento de respaldo externo.",
        })

    rut_unico = ruts_banco[0] if len(ruts_banco) == 1 else None
    nombre_unico = nombres_banco[0] if len(nombres_banco) == 1 else None
    nombre_unico = None if (nombre_unico is not None and _es_no_disponible(nombre_unico, valores_na)) else nombre_unico

    asignaciones = []
    suma_asignaciones = 0
    for bloque in candidato.get("bloques", []):
        texto_factura = bloque.get("factura")
        monto_aplicado, err_monto_asig = _normalizar_monto(bloque.get("monto"))
        clasificacion = _clasificar_texto_factura(texto_factura, patrones_no_factura)

        categoria = bloque.get("centro_costo")
        if _es_no_disponible(categoria, valores_na):
            advertencias.append({
                "codigo": "CATEGORIA_INGRESO_NO_RESUELTA",
                "campo": f"asignaciones[{bloque['bloque_indice']}].categoria_ingreso",
                "mensaje": "La categoria de ingreso (columna CENTRO DE COSTOS) llego como #N/A. No es un dato esencial para el movimiento.",
            })
            categoria = None

        if err_monto_asig:
            errores_normalizacion.append({
                "codigo": err_monto_asig,
                "campo": f"asignaciones[{bloque['bloque_indice']}].monto_aplicado",
                "mensaje": f"No fue posible normalizar el monto aplicado: {bloque.get('monto')!r}",
            })
            monto_aplicado = monto_aplicado or 0

        asignaciones.append({
            "bloque_indice": bloque["bloque_indice"],
            "rut_cliente": rut_unico,
            "nombre_cliente": nombre_unico,
            "categoria_ingreso": categoria,
            "tipo_documento": clasificacion["tipo_documento"],
            "numero_documento": clasificacion["numero_documento"],
            "monto_aplicado": monto_aplicado,
            "texto_original_celda": texto_factura,
            "requiere_revision": clasificacion["requiere_revision"],
            "motivo_revision": clasificacion["motivo_revision"],
            "fuente_respaldo": None,
        })
        suma_asignaciones += monto_aplicado or 0

        if clasificacion["requiere_revision"]:
            senales_revision.append({
                "codigo": clasificacion["motivo_revision"],
                "campo": f"asignaciones[{bloque['bloque_indice']}].texto_original_celda",
                "mensaje": f"Texto de factura requiere revision: {texto_factura!r}",
            })

    if not asignaciones:
        senales_revision.append({
            "codigo": "SIN_ASIGNACIONES",
            "campo": "asignaciones",
            "mensaje": "El movimiento tiene abono pero no trae ningun bloque de factura/monto.",
        })

    columnas_no_reconocidas = candidato.get("columnas_no_reconocidas", [])
    for entrada in columnas_no_reconocidas:
        senales_revision.append({
            "codigo": "COLUMNA_NO_RECONOCIDA_CON_DATOS",
            "campo": f"columnas_no_reconocidas[{entrada['columna']}]",
            "mensaje": (
                f"La columna {entrada['columna']} no corresponde a ningun campo fijo ni a "
                f"ningun bloque factura/monto/centro reconocido, pero trae un valor: "
                f"{entrada['valor']!r}. No se genero ninguna Asignacion a partir de este dato."
            ),
        })

    diferencia = suma_asignaciones - (monto_abono or 0)
    origen_pago = _detectar_origen_pago(campos.get("n_cheque_transferencia"))

    return {
        "movimiento_id": f"mov-{candidato['fila_origen']:06d}",
        "fila_origen": candidato["fila_origen"],
        "hoja_origen": candidato["hoja_origen"],
        "fecha_pago": fecha_pago,
        "numero_conciliacion": campos.get("n_correlativo"),
        "descripcion_banco": campos.get("detalle_transaccion"),
        "banco": banco_codigo,
        "origen_pago": origen_pago,
        "monto_abono": monto_abono,
        "ruts_banco": ruts_banco,
        "nombres_banco": nombres_banco,
        "asignaciones": asignaciones,
        "suma_asignaciones": suma_asignaciones,
        "diferencia": diferencia,
        "respaldo_diferencia": None,
        "advertencias": advertencias,
        "senales_revision": senales_revision,
        "errores_normalizacion": errores_normalizacion,
        "campos_originales": {
            **campos,
            "bloques_crudos": candidato.get("bloques", []),
            "columnas_no_reconocidas": columnas_no_reconocidas,
        },
    }


def normalizar(raw, reglas, banco_codigo="BCI"):
    movimientos = [
        normalizar_movimiento(c, reglas, banco_codigo=banco_codigo)
        for c in raw.get("movimientos_candidatos", [])
    ]
    return {
        "archivo_origen": raw.get("archivo_origen"),
        "hoja_origen": raw.get("hoja_origen"),
        "movimientos": movimientos,
        "omitidos": raw.get("omitidos", []),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_json", help="Salida de read_excel.py")
    parser.add_argument("--reglas", default=None, help="Ruta a validation-rules.json (default: rules/validation-rules.json del plugin)")
    parser.add_argument("--banco", default="BCI")
    parser.add_argument("--out", default=None, help="Ruta de salida JSON (default: stdout)")
    args = parser.parse_args(argv)

    with open(args.raw_json, encoding="utf-8") as f:
        raw = json.load(f)
    reglas = _cargar_reglas(args.reglas)

    resultado = normalizar(raw, reglas, banco_codigo=args.banco)
    salida = json.dumps(resultado, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(salida, encoding="utf-8")
        n_revision = sum(1 for m in resultado["movimientos"] if m["senales_revision"])
        n_errores = sum(1 for m in resultado["movimientos"] if m["errores_normalizacion"])
        print(f"Movimientos normalizados: {len(resultado['movimientos'])}")
        print(f"Con senales de revision: {n_revision}")
        print(f"Con errores de normalizacion: {n_errores}")
        print(f"Omitidos (fuera de alcance en lectura): {len(resultado['omitidos'])}")
    else:
        print(salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
