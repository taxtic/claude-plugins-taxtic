import copy
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


val = _load("validate")

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "conciliacion_fixture.xlsx")


def _reglas():
    return val._cargar_reglas()


def _asignacion(bloque_indice=1, rut_cliente="765432101", nombre_cliente="CLIENTE UNO SPA",
                 categoria_ingreso="Ingresos por Plan Premium", tipo_documento="FACTURA",
                 numero_documento=1001, monto_aplicado=100000, texto_original_celda=1001,
                 requiere_revision=False, motivo_revision=None, fuente_respaldo=None):
    return {
        "bloque_indice": bloque_indice,
        "rut_cliente": rut_cliente,
        "nombre_cliente": nombre_cliente,
        "categoria_ingreso": categoria_ingreso,
        "tipo_documento": tipo_documento,
        "numero_documento": numero_documento,
        "monto_aplicado": monto_aplicado,
        "texto_original_celda": texto_original_celda,
        "requiere_revision": requiere_revision,
        "motivo_revision": motivo_revision,
        "fuente_respaldo": fuente_respaldo,
    }


def _movimiento(fila_origen=3, monto_abono=100000, asignaciones=None, origen_pago="TRANSFERENCIA",
                 ruts_banco=None, diferencia=None, respaldo_diferencia=None,
                 errores_normalizacion=None, senales_revision=None, advertencias=None,
                 fecha_pago="2026-07-01", banco="BCI"):
    asignaciones = [_asignacion()] if asignaciones is None else asignaciones
    ruts_banco = ["765432101"] if ruts_banco is None else ruts_banco
    suma = sum(a.get("monto_aplicado") or 0 for a in asignaciones)
    if diferencia is None:
        diferencia = suma - (monto_abono or 0)
    return {
        "movimiento_id": f"mov-{fila_origen:06d}",
        "fila_origen": fila_origen,
        "hoja_origen": "Hoja1",
        "fecha_pago": fecha_pago,
        "numero_conciliacion": fila_origen - 2,
        "descripcion_banco": "MENSUALIDAD JULIO 26",
        "banco": banco,
        "origen_pago": origen_pago,
        "monto_abono": monto_abono,
        "ruts_banco": ruts_banco,
        "nombres_banco": ["CLIENTE UNO SPA"],
        "asignaciones": asignaciones,
        "suma_asignaciones": suma,
        "diferencia": diferencia,
        "respaldo_diferencia": respaldo_diferencia,
        "advertencias": advertencias or [],
        "senales_revision": senales_revision or [],
        "errores_normalizacion": errores_normalizacion or [],
        "campos_originales": {},
    }


def _codigos(resultado):
    return {m["codigo"] for m in resultado["motivos"]}


# 1-2. pagos normales exactos -> APTO

def test_pago_simple_exacto_apto():
    m = _movimiento()
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "APTO"
    assert r["tipo_pago"] == "SIMPLE"
    assert r["motivos"] == []


def test_multifactura_exacto_apto():
    asigs = [
        _asignacion(1, numero_documento=2001, monto_aplicado=30000, texto_original_celda=2001),
        _asignacion(2, numero_documento=2002, monto_aplicado=20000, texto_original_celda=2002),
    ]
    m = _movimiento(monto_abono=50000, asignaciones=asigs)
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "APTO"
    assert r["tipo_pago"] == "MULTIFACTURA"


# 3. diferencia normal sin respaldo -> REVISION

def test_diferencia_sin_respaldo_revision():
    m = _movimiento(monto_abono=99000)  # suma=100000, diferencia=1000
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)


# 4-5. Transbank Caso Oro (variante de un solo RUT -- ver Fase 2 seccion 8)

REFERENCIA_RESPALDO_TEST = "respaldo-test-transbank-001"


def _respaldo_valido(referencia=REFERENCIA_RESPALDO_TEST):
    return {"tipo": "TRANSBANK", "referencia": referencia, "verificado": True}


def _asignaciones_caso_oro(rut_cliente="765432101", fuente_respaldo=None):
    return [
        _asignacion(1, rut_cliente=rut_cliente, numero_documento=34053, monto_aplicado=71649,
                    texto_original_celda=34053, fuente_respaldo=fuente_respaldo),
        _asignacion(2, rut_cliente=rut_cliente, numero_documento=34052, monto_aplicado=71649,
                    texto_original_celda=34052, fuente_respaldo=fuente_respaldo),
        _asignacion(3, rut_cliente=rut_cliente, numero_documento=34008, monto_aplicado=102112,
                    texto_original_celda=34008, fuente_respaldo=fuente_respaldo),
    ]


def test_transbank_caso_oro_con_respaldo_apto():
    """Variante de un solo RUT: no requiere fuente_respaldo por asignacion
    porque len(ruts_banco) == 1 -- ya viene resuelto por normalize.py."""
    m = _movimiento(
        monto_abono=241615, asignaciones=_asignaciones_caso_oro(), origen_pago="TRANSBANK",
        respaldo_diferencia=_respaldo_valido(),
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["montos"]["diferencia"] == 3795
    assert r["estado_motor"] == "APTO"
    assert r["tipo_pago"] == "TRANSBANK"
    assert "DIFERENCIA_TRANSBANK_RESPALDADA" in _codigos(r)
    assert r["montos"]["diferencia_respaldada"] is True


def test_transbank_caso_oro_sin_respaldo_revision():
    m = _movimiento(
        monto_abono=241615, asignaciones=_asignaciones_caso_oro(), origen_pago="TRANSBANK",
        respaldo_diferencia=None,
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)
    assert r["montos"]["diferencia_respaldada"] is False


# --- Caso Oro Transbank MULTI-RUT (estructura fiel al hallazgo real de ejemplo.xlsx) ---

def _asignaciones_caso_oro_multi_rut(referencia=REFERENCIA_RESPALDO_TEST, fuente_por_asignacion=None):
    """3 RUT ficticios distintos, uno por factura -- igual a la estructura
    real auditada (nunca la usamos con RUT reales)."""
    ruts = ["111111111", "222222222", "333333333"]
    fuentes = fuente_por_asignacion if fuente_por_asignacion is not None else [referencia, referencia, referencia]
    datos = [
        (34053, 71649),
        (34052, 71649),
        (34008, 102112),
    ]
    return [
        _asignacion(i + 1, rut_cliente=ruts[i], numero_documento=doc, monto_aplicado=monto,
                    texto_original_celda=doc, fuente_respaldo=fuentes[i])
        for i, (doc, monto) in enumerate(datos)
    ]


def test_transbank_caso_oro_multi_rut_enriquecido_apto():
    """Demuestra que el modelo PUEDE representar el Caso Oro real (3 RUT
    distintos) llegando a APTO, siempre que una fase anterior ya haya
    resuelto cada rut_cliente y marcado fuente_respaldo == referencia."""
    m = _movimiento(
        monto_abono=241615,
        asignaciones=_asignaciones_caso_oro_multi_rut(),
        origen_pago="TRANSBANK",
        ruts_banco=["111111111", "222222222", "333333333"],
        respaldo_diferencia=_respaldo_valido(),
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["montos"]["diferencia"] == 3795
    assert r["estado_motor"] == "APTO"
    assert r["tipo_pago"] == "TRANSBANK"
    assert "DIFERENCIA_TRANSBANK_RESPALDADA" in _codigos(r)


def test_transbank_multi_rut_sin_asignaciones_resueltas_revision():
    """Mismo Caso Oro multi-RUT, pero SIN enriquecer (rut_cliente=None en
    todas las asignaciones, como produce normalize.py hoy). Incluso con
    respaldo estructuralmente valido, la Regla E domina -> REVISION."""
    asigs = [
        _asignacion(1, rut_cliente=None, numero_documento=34053, monto_aplicado=71649, texto_original_celda=34053),
        _asignacion(2, rut_cliente=None, numero_documento=34052, monto_aplicado=71649, texto_original_celda=34052),
        _asignacion(3, rut_cliente=None, numero_documento=34008, monto_aplicado=102112, texto_original_celda=34008),
    ]
    m = _movimiento(
        monto_abono=241615, asignaciones=asigs, origen_pago="TRANSBANK",
        ruts_banco=["111111111", "222222222", "333333333"],
        respaldo_diferencia=_respaldo_valido(),
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "MULTIPLES_RUT_SIN_ASOCIACION" in _codigos(r)


def test_transbank_multi_rut_referencia_no_coincide_revision():
    """1. referencia no coincide en una asignacion -> REVISION."""
    asigs = _asignaciones_caso_oro_multi_rut(fuente_por_asignacion=[REFERENCIA_RESPALDO_TEST, "otra-referencia-distinta", REFERENCIA_RESPALDO_TEST])
    m = _movimiento(
        monto_abono=241615, asignaciones=asigs, origen_pago="TRANSBANK",
        ruts_banco=["111111111", "222222222", "333333333"],
        respaldo_diferencia=_respaldo_valido(),
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "ASIGNACION_RESPALDO_NO_COINCIDE" in _codigos(r)


def test_transbank_multi_rut_fuente_respaldo_null_en_una_asignacion_revision():
    """2. fuente_respaldo null en una asignacion multi-RUT -> REVISION."""
    asigs = _asignaciones_caso_oro_multi_rut(fuente_por_asignacion=[REFERENCIA_RESPALDO_TEST, None, REFERENCIA_RESPALDO_TEST])
    m = _movimiento(
        monto_abono=241615, asignaciones=asigs, origen_pago="TRANSBANK",
        ruts_banco=["111111111", "222222222", "333333333"],
        respaldo_diferencia=_respaldo_valido(),
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "ASIGNACION_RESPALDO_NO_COINCIDE" in _codigos(r)


def test_transbank_respaldo_no_verificado_revision():
    """3. verificado = false -> REVISION."""
    respaldo = {"tipo": "TRANSBANK", "referencia": REFERENCIA_RESPALDO_TEST, "verificado": False}
    m = _movimiento(
        monto_abono=241615, asignaciones=_asignaciones_caso_oro(), origen_pago="TRANSBANK",
        respaldo_diferencia=respaldo,
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)


def test_transbank_respaldo_referencia_vacia_revision():
    """4. referencia = "" -> REVISION."""
    respaldo = {"tipo": "TRANSBANK", "referencia": "", "verificado": True}
    m = _movimiento(
        monto_abono=241615, asignaciones=_asignaciones_caso_oro(), origen_pago="TRANSBANK",
        respaldo_diferencia=respaldo,
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)


def test_transbank_respaldo_tipo_distinto_revision():
    """Respaldo con tipo diferente de TRANSBANK -> REVISION."""
    respaldo = {"tipo": "OTRO", "referencia": REFERENCIA_RESPALDO_TEST, "verificado": True}
    m = _movimiento(
        monto_abono=241615, asignaciones=_asignaciones_caso_oro(), origen_pago="TRANSBANK",
        respaldo_diferencia=respaldo,
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)


def test_transbank_respaldo_string_antiguo_no_valido():
    """5. respaldo como string antiguo (contrato pre-Fase-2.1) -> ya no es
    valido; se trata igual que ausencia de respaldo -> REVISION."""
    m = _movimiento(
        monto_abono=241615, asignaciones=_asignaciones_caso_oro(), origen_pago="TRANSBANK",
        respaldo_diferencia="respaldo-como-string-antiguo",
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)
    assert r["montos"]["diferencia_respaldada"] is False


def test_transbank_respaldo_null_revision():
    """6. respaldo null -> REVISION (variante multi-RUT enriquecida en todo
    lo demas, solo falta el respaldo)."""
    m = _movimiento(
        monto_abono=241615, asignaciones=_asignaciones_caso_oro_multi_rut(), origen_pago="TRANSBANK",
        ruts_banco=["111111111", "222222222", "333333333"],
        respaldo_diferencia=None,
    )
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)


# 6. multiples RUT sin asociacion -> REVISION (sin diferencia, para aislar la regla E)

def test_multiples_rut_sin_asociacion_revision():
    asigs = [
        _asignacion(1, rut_cliente=None, numero_documento=6001, monto_aplicado=3000, texto_original_celda=6001),
        _asignacion(2, rut_cliente=None, numero_documento=6002, monto_aplicado=4000, texto_original_celda=6002),
    ]
    m = _movimiento(monto_abono=7000, asignaciones=asigs, origen_pago="TRANSBANK", ruts_banco=["848888888", "859999999"])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "MULTIPLES_RUT_SIN_ASOCIACION" in _codigos(r)


# 7-9. textos especiales / boleta -> REVISION

def test_devolver_al_cliente_revision():
    a = _asignacion(numero_documento=None, monto_aplicado=5000, texto_original_celda="DEVOLVER AL CLIENTE",
                     tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m = _movimiento(monto_abono=5000, asignaciones=[a])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DOCUMENTO_REQUIERE_REVISION" in _codigos(r)


def test_ajustar_revision():
    a = _asignacion(numero_documento=None, monto_aplicado=1000, texto_original_celda="AJUSTAR",
                     tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m = _movimiento(monto_abono=1000, asignaciones=[a])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DOCUMENTO_REQUIERE_REVISION" in _codigos(r)


def test_boleta_revision():
    a = _asignacion(numero_documento=81, monto_aplicado=8100, texto_original_celda="BOLETA 81",
                     tipo_documento="BOLETA", requiere_revision=True, motivo_revision="BOLETA_DETECTADA")
    m = _movimiento(monto_abono=8100, asignaciones=[a])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "BOLETA_NO_SOPORTADA_MVP" in _codigos(r)


# 10. sin asignaciones -> REVISION

def test_sin_asignaciones_revision():
    m = _movimiento(monto_abono=5000, asignaciones=[])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "SIN_ASIGNACIONES" in _codigos(r)


# 11. #N/A en H/K con datos esenciales validos -> APTO + advertencia

def test_na_en_hk_con_datos_esenciales_validos_apto_con_advertencia():
    m = _movimiento(advertencias=[
        {"codigo": "PROVEEDOR_NO_RESUELTO", "campo": "nombres_banco[0]", "mensaje": "x"},
        {"codigo": "CATEGORIA_INGRESO_NO_RESUELTA", "campo": "asignaciones[1].categoria_ingreso", "mensaje": "x"},
    ])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "APTO"
    assert {a["codigo"] for a in r["advertencias"]} == {"PROVEEDOR_NO_RESUELTO", "CATEGORIA_INGRESO_NO_RESUELTA"}


# 12-13. fecha / monto abono invalidos -> ERROR

def test_fecha_invalida_error():
    m = _movimiento(fecha_pago=None, errores_normalizacion=[
        {"codigo": "FECHA_NO_PARSEABLE", "campo": "fecha_pago", "mensaje": "x"}
    ])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "ERROR"
    assert "FECHA_INVALIDA" in _codigos(r)


def test_monto_abono_invalido_error():
    m = _movimiento(monto_abono=0)
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "ERROR"
    assert "MONTO_ABONO_INVALIDO" in _codigos(r)


# 14-16. asignacion invalida en pago normal -> ERROR

def test_asignacion_sin_rut_en_pago_normal_error():
    a = _asignacion(rut_cliente=None)
    m = _movimiento(ruts_banco=[], asignaciones=[a], errores_normalizacion=[
        {"codigo": "RUT_AUSENTE", "campo": "ruts_banco", "mensaje": "x"}
    ])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "ERROR"
    assert "RUT_ASIGNACION_AUSENTE" in _codigos(r)


def test_asignacion_sin_documento_en_pago_normal_error():
    a = _asignacion(numero_documento=None, texto_original_celda=None, requiere_revision=False, motivo_revision=None)
    m = _movimiento(asignaciones=[a])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "ERROR"
    assert "DOCUMENTO_ASIGNACION_AUSENTE" in _codigos(r)


def test_asignacion_con_monto_no_positivo_error():
    a = _asignacion(monto_aplicado=0)
    m = _movimiento(monto_abono=100000, asignaciones=[a])
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "ERROR"
    assert "MONTO_ASIGNACION_INVALIDO" in _codigos(r)


# 17. ERROR + REVISION simultanea -> ERROR domina

def test_error_domina_sobre_revision_simultanea():
    a = _asignacion(numero_documento=81, monto_aplicado=8100, texto_original_celda="BOLETA 81",
                     tipo_documento="BOLETA", requiere_revision=True, motivo_revision="BOLETA_DETECTADA")
    m = _movimiento(monto_abono=8100, asignaciones=[a], fecha_pago=None, errores_normalizacion=[
        {"codigo": "FECHA_NO_PARSEABLE", "campo": "fecha_pago", "mensaje": "x"}
    ])
    r = val.validar_movimiento(m, _reglas())
    codigos = _codigos(r)
    assert r["estado_motor"] == "ERROR"
    assert "FECHA_INVALIDA" in codigos
    assert "BOLETA_NO_SOPORTADA_MVP" in codigos


# 18. tolerancia $0: diferencia de $1 sin respaldo -> REVISION

def test_tolerancia_cero_diferencia_de_un_peso_revision():
    m = _movimiento(monto_abono=99999)  # suma=100000, diferencia=1
    r = val.validar_movimiento(m, _reglas())
    assert r["estado_motor"] == "REVISION"
    assert "DIFERENCIA_SIN_RESPALDO" in _codigos(r)


# 19. validate.py no agrega cuenta/debe/haber

def test_no_agrega_cuenta_debe_haber():
    m = _movimiento()
    r = val.validar_movimiento(m, _reglas())
    assert "cuenta" not in r
    assert "debe" not in r
    assert "haber" not in r
    texto = json.dumps(r)
    for cuenta_prohibida in ("10-01-003", "10-02-001", "10-04-001"):
        assert cuenta_prohibida not in texto


# 20. validate.py no modifica el Movimiento de entrada

def test_no_modifica_movimiento_de_entrada():
    m = _movimiento()
    antes = copy.deepcopy(m)
    val.validar_movimiento(m, _reglas())
    assert m == antes


# --- integracion sobre el fixture real (read_excel + normalize + validate) ---

def _resultados_pipeline():
    re_ = _load("read_excel")
    nz = _load("normalize")
    raw = re_.leer_conciliacion(FIXTURE)
    normalizado = nz.normalizar(raw, nz._cargar_reglas())
    resultados = val.validar(normalizado["movimientos"], _reglas())
    return {r["movimiento_id"]: r for r in resultados}


def test_integracion_pipeline_completo_sobre_fixture():
    resultados = _resultados_pipeline()
    assert resultados["mov-000003"]["estado_motor"] == "APTO"      # pago simple
    assert resultados["mov-000004"]["estado_motor"] == "APTO"      # multifactura
    assert resultados["mov-000007"]["estado_motor"] == "REVISION"  # DEVOLVER AL CLIENTE
    assert resultados["mov-000008"]["estado_motor"] == "REVISION"  # AJUSTAR
    assert resultados["mov-000009"]["estado_motor"] == "REVISION"  # BOLETA 81
    assert resultados["mov-000010"]["estado_motor"] == "APTO"      # #N/A pero datos esenciales OK
    assert resultados["mov-000011"]["estado_motor"] == "REVISION"  # multiples RUT
    assert resultados["mov-000015"]["estado_motor"] == "REVISION"  # columna huerfana con datos


def test_integracion_no_modifica_movimientos_normalizados():
    re_ = _load("read_excel")
    nz = _load("normalize")
    raw = re_.leer_conciliacion(FIXTURE)
    normalizado = nz.normalizar(raw, nz._cargar_reglas())
    antes = copy.deepcopy(normalizado["movimientos"])
    val.validar(normalizado["movimientos"], _reglas())
    assert normalizado["movimientos"] == antes
