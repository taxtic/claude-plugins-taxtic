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


re = _load("read_excel")

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "conciliacion_fixture.xlsx")


def _leer():
    return re.leer_conciliacion(FIXTURE)


def _candidato_fila(resultado, fila):
    return next(c for c in resultado["movimientos_candidatos"] if c["fila_origen"] == fila)


def _omitido_fila(resultado, fila):
    return next(o for o in resultado["omitidos"] if o["fila_origen"] == fila)


def test_fila_normal_una_factura():
    resultado = _leer()
    c = _candidato_fila(resultado, 3)
    assert c["campos_fijos"]["abonos"] == 100000
    assert len(c["bloques"]) == 1
    assert c["bloques"][0]["factura"] == 1001
    assert c["bloques"][0]["monto"] == 100000


def test_fila_normal_multifactura():
    resultado = _leer()
    c = _candidato_fila(resultado, 4)
    assert len(c["bloques"]) == 2
    facturas = [b["factura"] for b in c["bloques"]]
    assert facturas == [2001, 2002]


def test_maximo_de_asignaciones_observado_en_fixture():
    resultado = _leer()
    max_bloques = max(len(c["bloques"]) for c in resultado["movimientos_candidatos"])
    assert max_bloques == 4
    c = _candidato_fila(resultado, 5)
    assert len(c["bloques"]) == 4


def test_fila_cargo_fuera_de_alcance():
    resultado = _leer()
    o = _omitido_fila(resultado, 12)
    assert o["motivo"] == "CARGO_FUERA_DE_ALCANCE"
    assert all(c["fila_origen"] != 12 for c in resultado["movimientos_candidatos"])


def test_fila_total_se_excluye():
    resultado = _leer()
    o = _omitido_fila(resultado, 13)
    assert o["motivo"] == "FILA_TOTAL"
    assert all(c["fila_origen"] != 13 for c in resultado["movimientos_candidatos"])


def test_fila_vacia_se_excluye():
    resultado = _leer()
    o = _omitido_fila(resultado, 14)
    assert o["motivo"] == "FILA_VACIA"
    assert all(c["fila_origen"] != 14 for c in resultado["movimientos_candidatos"])


def test_bloques_texto_no_factura_se_preservan_crudos():
    resultado = _leer()
    c = _candidato_fila(resultado, 7)
    assert c["bloques"][0]["factura"] == "DEVOLVER AL CLIENTE"
    c8 = _candidato_fila(resultado, 8)
    assert c8["bloques"][0]["factura"] == "AJUSTAR"
    c9 = _candidato_fila(resultado, 9)
    assert c9["bloques"][0]["factura"] == "BOLETA 81"


def test_na_en_proveedor_y_cuenta_no_excluye_la_fila():
    resultado = _leer()
    c = _candidato_fila(resultado, 10)
    assert c["campos_fijos"]["proveedor_cliente_banco_crudo"] == "#N/A"
    assert c["campos_fijos"]["cuenta_categoria_ingreso"] == "#N/A"
    assert c["campos_fijos"]["rut_banco_crudo"] == "83777777-7"


def test_multiples_rut_se_preservan_crudos_sin_dividir():
    resultado = _leer()
    c = _candidato_fila(resultado, 11)
    assert c["campos_fijos"]["rut_banco_crudo"] == "84888888-8 / 85999999-9"
    assert len(c["bloques"]) == 2


def test_no_modifica_el_excel_original():
    antes = hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest()
    re.leer_conciliacion(FIXTURE)
    despues = hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest()
    assert antes == despues


def test_deteccion_de_bloques_por_encabezado():
    resultado = _leer()
    # el fixture incluye una columna huerfana (X, "MONTOS999") equivalente a BD-BJ del Excel real
    assert resultado["columnas_no_reconocidas_headers"] == {"X": "MONTOS999"}
    assert resultado["columnas_no_reconocidas_con_datos"] == ["X"]


def test_columna_huerfana_no_se_convierte_en_bloque():
    """Equivalente estructural al hallazgo BD-BJ: una columna que empieza con
    'MONTOS' pero sin 'FACTURAS' precedente no debe agruparse en ningun bloque,
    y su dato no debe perderse silenciosamente."""
    resultado = _leer()
    c = _candidato_fila(resultado, 15)
    # el unico bloque reconocido en la fila es el de la factura 7001; la columna
    # huerfana X (valor 999) no genera un segundo bloque
    assert len(c["bloques"]) == 1
    assert c["bloques"][0]["factura"] == 7001
    # el valor de la columna huerfana se preserva con trazabilidad (columna + valor)
    assert c["columnas_no_reconocidas"] == [{"columna": "X", "valor": 999}]
