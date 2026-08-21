"""Fase 9: regresion de extremo a extremo de la CAPA DE LECTURA (read_excel.py)
contra la salida Softland ya validada y congelada (OFICIAL_61).

Estos tests codifican como pytest permanente lo que antes solo se habia
verificado manualmente en el scratchpad:

1. El fixture historico LEGACY_CON_ENCABEZADO, corrido por el pipeline
   completo (read_excel -> normalize -> validate -> transform ->
   export_softland, perfil OFICIAL_61), sigue produciendo exactamente el
   mismo CSV congelado en tests/expected/oficial_61_regresion_lectura.csv
   (mismo SHA-256), incluso despues de la reescritura de read_excel.py.
2. Un fixture equivalente en formato SIN_ENCABEZADO_ORIGINAL (misma
   informacion de negocio, distinto layout fisico de entrada) produce un
   modelo canonico equivalente y un CSV OFICIAL_61 identico byte a byte al
   del fixture LEGACY -- prueba de que el cambio de capa de entrada no
   altera la salida Softland.

Todos los datos de estos fixtures son completamente ficticios.
"""
import hashlib
import importlib.util
import os


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(__file__), "..", "scripts", name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


re_ = _load("read_excel")
no_ = _load("normalize")
val = _load("validate")
tr = _load("transform")
es = _load("export_softland")

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
EXPECTED_DIR = os.path.join(os.path.dirname(__file__), "expected")

FIXTURE_LEGACY = os.path.join(FIXTURES_DIR, "conciliacion_fixture_regresion.xlsx")
FIXTURE_ORIGINAL = os.path.join(FIXTURES_DIR, "conciliacion_fixture_regresion_sin_encabezado.xlsx")
FIXTURE_FECHA_SERIAL = os.path.join(FIXTURES_DIR, "conciliacion_fixture_fecha_serial.xlsx")
GOLDEN_PATH = os.path.join(EXPECTED_DIR, "oficial_61_regresion_lectura.csv")
GOLDEN_SHA256 = "e2f5eaac76d99c9ed61038c6ce37e1542b2325f05a9ba80373c6379702bf4503"

CAMPOS_CANONICOS_NO_COMPARABLES = {"movimiento_id", "fila_origen"}


def _decision(movimiento_id):
    return {
        "movimiento_id": movimiento_id,
        "estado_humano": "APROBADO",
        "revisor": "test-regresion@taxtic.com",
        "fecha_decision": "2026-01-01T00:00:00+00:00",
        "observacion": "Decision deterministica para regresion de lectura, Fase 9.",
    }


def _pipeline_completo(path_excel):
    """read_excel -> normalize -> validate -> transform -> export_softland (OFICIAL_61)."""
    raw = re_.leer_conciliacion(path_excel)
    normalizado = no_.normalizar(raw, no_._cargar_reglas())
    assert len(normalizado["movimientos"]) == 1, "el fixture de regresion debe producir exactamente 1 movimiento"
    movimiento = normalizado["movimientos"][0]
    resultado_validacion = val.validar_movimiento(movimiento, val._cargar_reglas())
    decision = _decision(movimiento["movimiento_id"])
    lineas = tr.transformar_movimiento(movimiento, resultado_validacion, decision, tr._cargar_reglas())
    contenido = es.exportar(lineas, "OFICIAL_61", es._cargar_layouts())
    return movimiento, contenido


def test_golden_regresion_lectura_oficial_61_sha256_congelado():
    """El golden congelado en disco (generado ANTES de la reescritura de
    read_excel.py) debe seguir teniendo el SHA-256 documentado."""
    with open(GOLDEN_PATH, "rb") as f:
        contenido_golden = f.read()
    assert hashlib.sha256(contenido_golden).hexdigest() == GOLDEN_SHA256


def test_legacy_con_encabezado_reproduce_el_golden_byte_a_byte():
    """Post-cambio: el mismo fixture LEGACY, por el pipeline completo, sigue
    produciendo el mismo CSV OFICIAL_61 (misma cadena de bytes, mismo
    SHA-256) que antes de reescribir read_excel.py."""
    _, contenido = _pipeline_completo(FIXTURE_LEGACY)
    contenido_bytes = contenido.encode("utf-8")
    with open(GOLDEN_PATH, "rb") as f:
        contenido_golden = f.read()
    assert contenido_bytes == contenido_golden
    assert hashlib.sha256(contenido_bytes).hexdigest() == GOLDEN_SHA256


def test_sin_encabezado_original_canonico_equivalente_a_legacy():
    """Mismo movimiento de negocio, distinto layout fisico de entrada -> el
    modelo canonico (normalize.py) debe ser equivalente en todos los campos
    funcionalmente relevantes (se excluyen unicamente movimiento_id/
    fila_origen, que se derivan de la posicion fisica de la fila en cada
    archivo, no del contenido de negocio -- verificado empiricamente que
    hoja_origen y campos_originales SI son iguales entre A y B, por lo que
    se exige su igualdad estricta en vez de excluirlos)."""
    raw_legacy = re_.leer_conciliacion(FIXTURE_LEGACY)
    raw_original = re_.leer_conciliacion(FIXTURE_ORIGINAL)
    mov_legacy = no_.normalizar(raw_legacy, no_._cargar_reglas())["movimientos"][0]
    mov_original = no_.normalizar(raw_original, no_._cargar_reglas())["movimientos"][0]

    claves = set(mov_legacy) | set(mov_original)
    for clave in claves - CAMPOS_CANONICOS_NO_COMPARABLES:
        assert mov_legacy[clave] == mov_original[clave], f"campo canonico '{clave}' difiere entre LEGACY y SIN_ENCABEZADO_ORIGINAL"


def test_sin_encabezado_original_produce_oficial_61_identico_byte_a_byte_a_legacy():
    """La prueba final de que el cambio de capa de entrada no afecta la
    salida Softland: el mismo movimiento leido desde un layout de entrada
    distinto produce el mismo CSV OFICIAL_61, byte a byte, y ese CSV
    tambien coincide con el golden congelado."""
    _, contenido_legacy = _pipeline_completo(FIXTURE_LEGACY)
    _, contenido_original = _pipeline_completo(FIXTURE_ORIGINAL)

    bytes_legacy = contenido_legacy.encode("utf-8")
    bytes_original = contenido_original.encode("utf-8")
    assert bytes_legacy == bytes_original

    with open(GOLDEN_PATH, "rb") as f:
        contenido_golden = f.read()
    assert bytes_legacy == contenido_golden
    assert bytes_original == contenido_golden


# --- fecha como serial Excel crudo (bug real encontrado en PRUEBA CLAUDIO.xlsx,
# celda con number_format "General") -- prueba de extremo a extremo:
# read_excel -> normalize -> validate, sin exportar (no hay evidencia real
# aun de que este caso siempre implique un movimiento exportable completo,
# solo se prueba aqui la cadena de interpretacion de fecha). ---

def test_fecha_serial_excel_crudo_llega_correcta_hasta_validate():
    raw = re_.leer_conciliacion(FIXTURE_FECHA_SERIAL)
    normalizado = no_.normalizar(raw, no_._cargar_reglas())
    assert len(normalizado["movimientos"]) == 1
    movimiento = normalizado["movimientos"][0]

    assert movimiento["fecha_pago"] == "2026-08-07"
    assert not any(e["codigo"] == "FECHA_NO_PARSEABLE" for e in movimiento["errores_normalizacion"])

    resultado_validacion = val.validar_movimiento(movimiento, val._cargar_reglas())
    assert not any(m["codigo"] == "FECHA_INVALIDA" for m in resultado_validacion["motivos"])
