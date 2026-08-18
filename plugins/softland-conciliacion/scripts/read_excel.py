"""Lectura estructural del Excel de conciliacion bancaria BCI.

No interpreta significado de negocio: solo extrae celdas, agrupa los bloques
repetidos de factura/monto/centro de costo por su encabezado, y separa filas
fuera de alcance (CARGO, fila Total, filas de control/saldo, filas vacias) de
los movimientos candidatos que pasaran a normalize.py.

El archivo de entrada se abre siempre en modo lectura y nunca se modifica.
"""
import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

FILA_ENCABEZADO_DEFAULT = 2
HOJA_DEFAULT = "Hoja1"

# columnas fijas 1..11 (A..K), posicion confirmada en el Excel productivo auditado
CAMPOS_FIJOS = [
    (1, "fecha"),
    (2, "n_cheque_transferencia"),
    (3, "n_correlativo"),
    (4, "cargo"),
    (5, "abonos"),
    (6, "saldo_contable"),
    (7, "rut_banco_crudo"),
    (8, "proveedor_cliente_banco_crudo"),
    (9, "cc"),
    (10, "detalle_transaccion"),
    (11, "cuenta_categoria_ingreso"),
]
PRIMERA_COLUMNA_BLOQUES = 12  # columna L


def _serializar(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def _detectar_bloques(headers):
    """Detecta bloques (factura, monto, centro) a partir del texto de encabezado,
    no de la letra de columna: el orden FACTURAS->MONTOS->CENTRO se repite pero
    el sufijo numerico de cada nombre varia (duplicados de Excel)."""
    bloques = []
    max_col = max(headers) if headers else 0
    c = PRIMERA_COLUMNA_BLOQUES
    while c <= max_col:
        h = (headers.get(c) or "").strip().upper()
        if h.startswith("FACTURAS"):
            factura_col = c
            monto_col = None
            centro_col = None
            h_next = (headers.get(c + 1) or "").strip().upper()
            if h_next.startswith("MONTOS"):
                monto_col = c + 1
                h_next2 = (headers.get(c + 2) or "").strip().upper()
                if h_next2.startswith("CENTRO"):
                    centro_col = c + 2
            bloques.append({"factura_col": factura_col, "monto_col": monto_col, "centro_col": centro_col})
            c += 3 if centro_col else (2 if monto_col else 1)
        else:
            c += 1
    return bloques


def _columnas_reconocidas(bloques):
    reconocidas = {col for col, _ in CAMPOS_FIJOS}
    for b in bloques:
        for k in ("factura_col", "monto_col", "centro_col"):
            if b[k]:
                reconocidas.add(b[k])
    return reconocidas


def _clasificar_fila(campos_fijos, tiene_bloques_con_datos):
    """Devuelve el motivo de exclusion (str) si la fila esta fuera de alcance
    para convertirse en Movimiento, o None si es candidata."""
    fecha = campos_fijos.get("fecha")
    cargo = campos_fijos.get("cargo")
    abonos = campos_fijos.get("abonos")
    rut = campos_fijos.get("rut_banco_crudo")
    proveedor = campos_fijos.get("proveedor_cliente_banco_crudo")
    col_a_texto = str(fecha).strip().upper() if isinstance(fecha, str) else None

    if col_a_texto == "TOTAL":
        return "FILA_TOTAL"

    todo_vacio = all(
        campos_fijos.get(nombre) in (None, "")
        for _, nombre in CAMPOS_FIJOS
    ) and not tiene_bloques_con_datos
    if todo_vacio:
        return "FILA_VACIA"

    if fecha is None and rut in (None, "") and proveedor in (None, ""):
        # sin fecha ni identificacion de cliente, pero con algun valor numerico
        # remanente (saldo/checksum) -> fila de control, no un movimiento real
        if any(campos_fijos.get(nombre) not in (None, "") for nombre in ("cargo", "abonos", "saldo_contable")):
            return "FILA_CONTROL_SALDO"
        if not tiene_bloques_con_datos:
            return "FILA_VACIA"

    if cargo not in (None, 0):
        return "CARGO_FUERA_DE_ALCANCE"

    return None


def leer_conciliacion(path, hoja=None, fila_encabezado=FILA_ENCABEZADO_DEFAULT):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    nombre_hoja = hoja if hoja and hoja in wb.sheetnames else (
        HOJA_DEFAULT if HOJA_DEFAULT in wb.sheetnames else wb.sheetnames[0]
    )
    ws = wb[nombre_hoja]

    headers = {}
    for row in ws.iter_rows(min_row=fila_encabezado, max_row=fila_encabezado):
        for idx, cell in enumerate(row, start=1):
            headers[idx] = getattr(cell, "value", None)

    bloques_def = _detectar_bloques(headers)
    reconocidas = _columnas_reconocidas(bloques_def)
    max_col = max(headers) if headers else 0
    columnas_no_reconocidas_headers = {
        get_column_letter(c): headers.get(c)
        for c in range(PRIMERA_COLUMNA_BLOQUES, max_col + 1)
        if c not in reconocidas and headers.get(c) not in (None, "")
    }

    movimientos_candidatos = []
    omitidos = []
    columnas_no_reconocidas_con_datos = set()

    fila_actual = fila_encabezado
    for row in ws.iter_rows(min_row=fila_encabezado + 1):
        fila_actual += 1
        celdas = {idx: getattr(cell, "value", None) for idx, cell in enumerate(row, start=1)}

        campos_fijos = {}
        for col, nombre in CAMPOS_FIJOS:
            campos_fijos[nombre] = _serializar(celdas.get(col))

        bloques = []
        for idx, b in enumerate(bloques_def, start=1):
            factura = _serializar(celdas.get(b["factura_col"]))
            monto = _serializar(celdas.get(b["monto_col"])) if b["monto_col"] else None
            centro = _serializar(celdas.get(b["centro_col"])) if b["centro_col"] else None
            if factura in (None, "") and monto in (None, "") and centro in (None, ""):
                continue
            bloques.append({
                "bloque_indice": idx,
                "factura": factura,
                "monto": monto,
                "centro_costo": centro,
            })

        columnas_no_reconocidas_fila = []
        for c, v in celdas.items():
            if c >= PRIMERA_COLUMNA_BLOQUES and c not in reconocidas and v not in (None, ""):
                letra = get_column_letter(c)
                columnas_no_reconocidas_con_datos.add(letra)
                columnas_no_reconocidas_fila.append({"columna": letra, "valor": _serializar(v)})

        motivo = _clasificar_fila(campos_fijos, tiene_bloques_con_datos=bool(bloques))
        registro = {
            "fila_origen": fila_actual,
            "hoja_origen": nombre_hoja,
            "campos_fijos": campos_fijos,
            "bloques": bloques,
            "columnas_no_reconocidas": columnas_no_reconocidas_fila,
        }
        if motivo:
            registro["motivo"] = motivo
            omitidos.append(registro)
        else:
            movimientos_candidatos.append(registro)

    return {
        "archivo_origen": str(path),
        "hoja_origen": nombre_hoja,
        "fila_encabezado": fila_encabezado,
        "movimientos_candidatos": movimientos_candidatos,
        "omitidos": omitidos,
        "columnas_no_reconocidas_headers": columnas_no_reconocidas_headers,
        "columnas_no_reconocidas_con_datos": sorted(columnas_no_reconocidas_con_datos),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", help="Ruta al Excel de conciliacion (.xlsx)")
    parser.add_argument("--hoja", default=None, help="Nombre de hoja (default: Hoja1 o la primera disponible)")
    parser.add_argument("--fila-encabezado", type=int, default=FILA_ENCABEZADO_DEFAULT)
    parser.add_argument("--out", default=None, help="Ruta de salida JSON (default: stdout)")
    args = parser.parse_args(argv)

    resultado = leer_conciliacion(Path(args.excel), hoja=args.hoja, fila_encabezado=args.fila_encabezado)
    salida = json.dumps(resultado, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(salida, encoding="utf-8")
        print(f"Movimientos candidatos: {len(resultado['movimientos_candidatos'])}")
        print(f"Omitidos: {len(resultado['omitidos'])}")
        if resultado["columnas_no_reconocidas_con_datos"]:
            print(f"AVISO: columnas no reconocidas con datos: {resultado['columnas_no_reconocidas_con_datos']}")
    else:
        print(salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
