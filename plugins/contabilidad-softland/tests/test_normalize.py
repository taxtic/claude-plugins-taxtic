import hashlib
import importlib.util
import json
import os


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(__file__), "..", "scripts", name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


re = _load("read_excel")
nz = _load("normalize")

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "conciliacion_fixture.xlsx")


def _reglas():
    return nz._cargar_reglas()


def _pipeline():
    raw = re.leer_conciliacion(FIXTURE)
    return nz.normalizar(raw, _reglas())


def _mov(resultado, fila):
    return next(m for m in resultado["movimientos"] if m["fila_origen"] == fila)


def _candidato(fecha="2026-07-01T00:00:00", n_correlativo=1, cargo=0, abonos=100000,
                rut="76543210-1", proveedor="CLIENTE UNO SPA", cuenta="Ingresos por Plan Premium",
                detalle="MENSUALIDAD JULIO 26", bloques=None, fila=3, columnas_no_reconocidas=None):
    return {
        "fila_origen": fila,
        "hoja_origen": "Hoja1",
        "campos_fijos": {
            "fecha": fecha,
            "n_cheque_transferencia": "Transferencia recibida de Cliente",
            "n_correlativo": n_correlativo,
            "cargo": cargo,
            "abonos": abonos,
            "saldo_contable": 999999,
            "rut_banco_crudo": rut,
            "proveedor_cliente_banco_crudo": proveedor,
            "cc": None,
            "detalle_transaccion": detalle,
            "cuenta_categoria_ingreso": cuenta,
        },
        "bloques": bloques or [],
        "columnas_no_reconocidas": columnas_no_reconocidas or [],
    }


# --- unit tests sobre normalizar_movimiento con candidatos sinteticos ---

def test_fila_normal_una_factura():
    c = _candidato(bloques=[{"bloque_indice": 1, "factura": 1001, "monto": 100000, "centro_costo": "Ingresos por Plan Premium"}])
    m = nz.normalizar_movimiento(c, _reglas())
    assert m["fecha_pago"] == "2026-07-01"
    assert m["ruts_banco"] == ["765432101"]
    assert m["asignaciones"][0]["numero_documento"] == 1001
    assert m["asignaciones"][0]["tipo_documento"] == "FACTURA"
    assert m["asignaciones"][0]["requiere_revision"] is False
    assert m["diferencia"] == 0
    assert m["senales_revision"] == []
    assert m["errores_normalizacion"] == []
    assert m["respaldo_diferencia"] is None
    assert m["asignaciones"][0]["fuente_respaldo"] is None


def test_fila_normal_multifactura():
    c = _candidato(abonos=50000, bloques=[
        {"bloque_indice": 1, "factura": 2001, "monto": 30000, "centro_costo": "A"},
        {"bloque_indice": 2, "factura": 2002, "monto": 20000, "centro_costo": "B"},
    ])
    m = nz.normalizar_movimiento(c, _reglas())
    assert m["suma_asignaciones"] == 50000
    assert m["diferencia"] == 0
    assert [a["numero_documento"] for a in m["asignaciones"]] == [2001, 2002]


def test_sufijo_abono_extrae_folio_y_conserva_texto_original():
    c = _candidato(abonos=15000, bloques=[{"bloque_indice": 1, "factura": "33501 ABONO", "monto": 15000, "centro_costo": "A"}])
    m = nz.normalizar_movimiento(c, _reglas())
    a = m["asignaciones"][0]
    assert a["numero_documento"] == 33501
    assert a["tipo_documento"] == "FACTURA"
    assert a["requiere_revision"] is False
    assert a["texto_original_celda"] == "33501 ABONO"


def test_sufijo_abono_con_numero_extrae_folio_y_conserva_texto_original():
    """'34201 ABONO 1' debe comportarse igual que '33501 ABONO': el folio es
    solo el numero inicial, y 'ABONO 1' nunca se incorpora al numero_documento."""
    c = _candidato(abonos=15000, bloques=[{"bloque_indice": 1, "factura": "34201 ABONO 1", "monto": 15000, "centro_costo": "A"}])
    m = nz.normalizar_movimiento(c, _reglas())
    a = m["asignaciones"][0]
    assert a["numero_documento"] == 34201
    assert isinstance(a["numero_documento"], int)
    assert a["tipo_documento"] == "FACTURA"
    assert a["requiere_revision"] is False
    assert a["motivo_revision"] is None
    assert a["texto_original_celda"] == "34201 ABONO 1"


def test_devolver_al_cliente_no_es_factura_normal():
    c = _candidato(abonos=5000, bloques=[{"bloque_indice": 1, "factura": "DEVOLVER AL CLIENTE", "monto": 5000, "centro_costo": "A"}])
    m = nz.normalizar_movimiento(c, _reglas())
    a = m["asignaciones"][0]
    assert a["tipo_documento"] == "DESCONOCIDO"
    assert a["numero_documento"] is None
    assert a["requiere_revision"] is True
    assert a["motivo_revision"] == "TEXTO_NO_FACTURA"
    assert a["texto_original_celda"] == "DEVOLVER AL CLIENTE"
    assert a["fuente_respaldo"] is None
    assert any(s["codigo"] == "TEXTO_NO_FACTURA" for s in m["senales_revision"])


def test_ajustar_no_es_factura_normal():
    c = _candidato(abonos=1000, bloques=[{"bloque_indice": 1, "factura": "AJUSTAR", "monto": 1000, "centro_costo": "A"}])
    m = nz.normalizar_movimiento(c, _reglas())
    a = m["asignaciones"][0]
    assert a["tipo_documento"] == "DESCONOCIDO"
    assert a["requiere_revision"] is True
    assert a["motivo_revision"] == "TEXTO_NO_FACTURA"


def test_boleta_se_detecta_y_marca_revision_sin_convertirse_en_factura():
    c = _candidato(abonos=8100, bloques=[{"bloque_indice": 1, "factura": "BOLETA 81", "monto": 8100, "centro_costo": "A"}])
    m = nz.normalizar_movimiento(c, _reglas())
    a = m["asignaciones"][0]
    assert a["tipo_documento"] == "BOLETA"
    assert a["numero_documento"] == 81
    assert a["requiere_revision"] is True
    assert a["motivo_revision"] == "BOLETA_DETECTADA"
    assert a["fuente_respaldo"] is None


def test_na_en_proveedor_y_categoria_genera_advertencia_no_error():
    c = _candidato(proveedor="#N/A", cuenta="#N/A", rut="83777777-7",
                    bloques=[{"bloque_indice": 1, "factura": 5001, "monto": 12000, "centro_costo": "#N/A"}],
                    abonos=12000)
    m = nz.normalizar_movimiento(c, _reglas())
    codigos_advertencia = {a["codigo"] for a in m["advertencias"]}
    assert "PROVEEDOR_NO_RESUELTO" in codigos_advertencia
    assert "CATEGORIA_INGRESO_NO_RESUELTA" in codigos_advertencia
    assert m["errores_normalizacion"] == []
    assert m["ruts_banco"] == ["837777777"]
    assert m["asignaciones"][0]["rut_cliente"] == "837777777"


def test_multiples_rut_sin_asociacion_explicita_no_asigna_por_heuristica():
    c = _candidato(
        rut="84888888-8 / 85999999-9",
        proveedor="CLIENTE NUEVE SPA / CLIENTE DIEZ SPA",
        abonos=7000,
        bloques=[
            {"bloque_indice": 1, "factura": 6001, "monto": 3000, "centro_costo": "A"},
            {"bloque_indice": 2, "factura": 6002, "monto": 4000, "centro_costo": "B"},
        ],
    )
    m = nz.normalizar_movimiento(c, _reglas())
    assert m["ruts_banco"] == ["848888888", "859999999"]
    assert all(a["rut_cliente"] is None for a in m["asignaciones"])
    assert any(s["codigo"] == "MULTIPLES_RUT_SIN_ASOCIACION_EXPLICITA" for s in m["senales_revision"])
    # sin respaldo externo, fuente_respaldo se mantiene null: no se inventa relacion RUT-factura
    assert all(a["fuente_respaldo"] is None for a in m["asignaciones"])
    assert m["respaldo_diferencia"] is None


def test_fecha_no_parseable_queda_como_error_de_normalizacion():
    c = _candidato(fecha="no-es-una-fecha")
    m = nz.normalizar_movimiento(c, _reglas())
    assert m["fecha_pago"] is None
    assert any(e["codigo"] == "FECHA_NO_PARSEABLE" for e in m["errores_normalizacion"])


def test_sin_asignaciones_genera_senal_revision():
    c = _candidato(bloques=[])
    m = nz.normalizar_movimiento(c, _reglas())
    assert any(s["codigo"] == "SIN_ASIGNACIONES" for s in m["senales_revision"])


def test_columna_no_reconocida_no_genera_asignacion_y_queda_senalizada():
    """Equivalente estructural al hallazgo BD-BJ: un valor en una columna que
    read_excel.py no pudo agrupar en ningun bloque no debe convertirse en una
    Asignacion, debe quedar senalizado, y debe conservarse para trazabilidad."""
    c = _candidato(
        abonos=6000,
        bloques=[{"bloque_indice": 1, "factura": 7001, "monto": 6000, "centro_costo": "A"}],
        columnas_no_reconocidas=[{"columna": "X", "valor": 999}],
    )
    m = nz.normalizar_movimiento(c, _reglas())
    # solo la asignacion real (factura 7001); el valor huerfano no se convierte en Asignacion
    assert len(m["asignaciones"]) == 1
    assert m["asignaciones"][0]["numero_documento"] == 7001
    # queda senalizado para revision, no se pierde silenciosamente
    assert any(s["codigo"] == "COLUMNA_NO_RECONOCIDA_CON_DATOS" and s["campo"] == "columnas_no_reconocidas[X]" for s in m["senales_revision"])
    # se conserva trazabilidad del dato crudo
    assert m["campos_originales"]["columnas_no_reconocidas"] == [{"columna": "X", "valor": 999}]


def test_no_decide_estado_motor():
    """normalize.py no debe producir ningun campo de estado final (APTO/REVISION/ERROR)."""
    c = _candidato(bloques=[{"bloque_indice": 1, "factura": "AJUSTAR", "monto": 1000, "centro_costo": "A"}])
    m = nz.normalizar_movimiento(c, _reglas())
    assert "estado_motor" not in m
    assert "cuenta" not in m
    assert "tipo_documento_detectado" not in m["asignaciones"][0]
    assert "debe" not in m and "haber" not in m


# --- integracion sobre el fixture real (via read_excel.py) ---

def test_pipeline_omitidos_no_generan_movimiento():
    resultado = _pipeline()
    filas_movimiento = {m["fila_origen"] for m in resultado["movimientos"]}
    assert 12 not in filas_movimiento  # CARGO fuera de alcance
    assert 13 not in filas_movimiento  # fila Total
    assert 14 not in filas_movimiento  # fila vacia
    motivos = {o["fila_origen"]: o["motivo"] for o in resultado["omitidos"]}
    assert motivos[12] == "CARGO_FUERA_DE_ALCANCE"
    assert motivos[13] == "FILA_TOTAL"
    assert motivos[14] == "FILA_VACIA"


def test_pipeline_maximo_de_asignaciones_observado():
    resultado = _pipeline()
    m = _mov(resultado, 5)
    assert len(m["asignaciones"]) == 4
    assert m["suma_asignaciones"] == 40000
    assert m["diferencia"] == 0


def test_no_modifica_el_excel_original_via_pipeline_completo():
    antes = hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest()
    _pipeline()
    despues = hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest()
    assert antes == despues


def test_pipeline_coincide_con_golden_file_esperado():
    """Regresion de extremo a extremo: read_excel + normalize sobre el fixture
    completo debe coincidir exactamente con tests/expected/movimientos_esperados.json
    (salvo la ruta de archivo_origen, que depende de como se invoco el pipeline)."""
    resultado = _pipeline()
    esperado_path = os.path.join(os.path.dirname(__file__), "expected", "movimientos_esperados.json")
    with open(esperado_path, encoding="utf-8") as f:
        esperado = json.load(f)

    resultado_comparable = json.loads(json.dumps(resultado, sort_keys=True))
    resultado_comparable.pop("archivo_origen", None)
    esperado_comparable = dict(esperado)
    esperado_comparable.pop("archivo_origen", None)

    assert resultado_comparable == esperado_comparable
