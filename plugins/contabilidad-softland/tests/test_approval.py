import copy
import importlib.util
import os


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(os.path.dirname(__file__), "..", "scripts", name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ap = _load("approval")
val = _load("validate")


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
                 ruts_banco=None, nombres_banco=None, diferencia=None, respaldo_diferencia=None,
                 errores_normalizacion=None, senales_revision=None, advertencias=None,
                 fecha_pago="2026-07-01", banco="BCI"):
    asignaciones = [_asignacion()] if asignaciones is None else asignaciones
    ruts_banco = ["765432101"] if ruts_banco is None else ruts_banco
    nombres_banco = ["CLIENTE UNO SPA"] if nombres_banco is None else nombres_banco
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
        "nombres_banco": nombres_banco,
        "asignaciones": asignaciones,
        "suma_asignaciones": suma,
        "diferencia": diferencia,
        "respaldo_diferencia": respaldo_diferencia,
        "advertencias": advertencias or [],
        "senales_revision": senales_revision or [],
        "errores_normalizacion": errores_normalizacion or [],
        "campos_originales": {},
    }


def _resultado(movimiento):
    """Genera un ResultadoValidacion REAL corriendo validate.py sobre el
    Movimiento, en vez de fabricar uno a mano -- evita que los tests de
    approval.py se desincronicen del contrato real de validate.py."""
    return val.validar_movimiento(movimiento, _reglas())


# 1-3. puede_aprobar segun estado_motor

def test_apto_puede_aprobar_true():
    m = _movimiento()
    r = _resultado(m)
    assert r["estado_motor"] == "APTO"
    rev = ap.preparar_revision(m, r)
    assert rev["puede_aprobar"] is True


def test_revision_puede_aprobar_false():
    a = _asignacion(numero_documento=None, monto_aplicado=1000, texto_original_celda="AJUSTAR",
                     tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m = _movimiento(monto_abono=1000, asignaciones=[a])
    r = _resultado(m)
    assert r["estado_motor"] == "REVISION"
    rev = ap.preparar_revision(m, r)
    assert rev["puede_aprobar"] is False


def test_error_puede_aprobar_false():
    m = _movimiento(monto_abono=0)
    r = _resultado(m)
    assert r["estado_motor"] == "ERROR"
    rev = ap.preparar_revision(m, r)
    assert rev["puede_aprobar"] is False


# 4-5. decisiones validas sobre APTO

def test_apto_aprobado_decision_valida():
    m = _movimiento()
    r = _resultado(m)
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "claudio@taxtic.com", "2026-08-10T10:00:00-04:00")
    assert len(decisiones) == 1
    assert decisiones[0]["estado_humano"] == "APROBADO"


def test_apto_rechazado_decision_valida():
    m = _movimiento()
    r = _resultado(m)
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "RECHAZADO", "claudio@taxtic.com", "2026-08-10T10:00:00-04:00")
    assert len(decisiones) == 1
    assert decisiones[0]["estado_humano"] == "RECHAZADO"


# 6-7. REVISION/ERROR + intento APROBADO -> error

def test_revision_intento_aprobado_falla():
    a = _asignacion(numero_documento=None, monto_aplicado=1000, texto_original_celda="AJUSTAR",
                     tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m = _movimiento(monto_abono=1000, asignaciones=[a])
    r = _resultado(m)
    assert r["estado_motor"] == "REVISION"
    try:
        ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
        assert False, "debia fallar"
    except ValueError:
        pass


def test_error_intento_aprobado_falla():
    m = _movimiento(monto_abono=0)
    r = _resultado(m)
    assert r["estado_motor"] == "ERROR"
    try:
        ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
        assert False, "debia fallar"
    except ValueError:
        pass


# Fase 3.1: la capa de decision humana SOLO aplica a APTO. REVISION/ERROR
# tampoco pueden recibir RECHAZADO -- no solo APROBADO.

def test_revision_intento_rechazado_falla():
    a = _asignacion(numero_documento=None, monto_aplicado=1000, texto_original_celda="AJUSTAR",
                     tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m = _movimiento(monto_abono=1000, asignaciones=[a])
    r = _resultado(m)
    assert r["estado_motor"] == "REVISION"
    try:
        ap.registrar_decision(r, [], m["movimiento_id"], "RECHAZADO", "x", "2026-08-10T10:00:00-04:00")
        assert False, "debia fallar: REVISION no admite ninguna decision humana"
    except ValueError:
        pass


def test_error_intento_rechazado_falla():
    m = _movimiento(monto_abono=0)
    r = _resultado(m)
    assert r["estado_motor"] == "ERROR"
    try:
        ap.registrar_decision(r, [], m["movimiento_id"], "RECHAZADO", "x", "2026-08-10T10:00:00-04:00")
        assert False, "debia fallar: ERROR no admite ninguna decision humana"
    except ValueError:
        pass


def test_apto_rechazado_sigue_funcionando():
    m = _movimiento()
    r = _resultado(m)
    assert r["estado_motor"] == "APTO"
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "RECHAZADO", "x", "2026-08-10T10:00:00-04:00")
    assert decisiones[0]["estado_humano"] == "RECHAZADO"


def test_apto_aprobado_sigue_funcionando():
    m = _movimiento()
    r = _resultado(m)
    assert r["estado_motor"] == "APTO"
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
    assert decisiones[0]["estado_humano"] == "APROBADO"


def test_lote_original_no_se_modifica_si_la_decision_falla():
    a = _asignacion(numero_documento=None, monto_aplicado=1000, texto_original_celda="AJUSTAR",
                     tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m = _movimiento(monto_abono=1000, asignaciones=[a])
    r = _resultado(m)
    assert r["estado_motor"] == "REVISION"

    lote = ap.crear_lote("2026-08-lote-C")
    lote_antes = copy.deepcopy(lote)
    for decision in ("APROBADO", "RECHAZADO"):
        try:
            ap.registrar_decision_en_lote(lote, [r], m["movimiento_id"], decision, "x", "2026-08-10T10:00:00-04:00")
            assert False, f"debia fallar para decision={decision!r}"
        except ValueError:
            pass
        assert lote == lote_antes  # el lote original permanece sin modificar


# 8. decision distinta de APROBADO/RECHAZADO -> error

def test_decision_invalida_falla():
    m = _movimiento()
    r = _resultado(m)
    for decision_invalida in ("PENDIENTE", "aprobado", "OK", "", None):
        try:
            ap.registrar_decision(r, [], m["movimiento_id"], decision_invalida, "x", "2026-08-10T10:00:00-04:00")
            assert False, f"debia fallar para decision={decision_invalida!r}"
        except ValueError:
            pass


# 9. movimiento inexistente -> error

def test_movimiento_inexistente_falla():
    m = _movimiento()
    r = _resultado(m)
    try:
        ap.registrar_decision(r, [], "mov-999999", "APROBADO", "x", "2026-08-10T10:00:00-04:00")
        assert False, "debia fallar"
    except ValueError:
        pass

    try:
        ap.registrar_decision(None, [], "mov-999999", "APROBADO", "x", "2026-08-10T10:00:00-04:00")
        assert False, "debia fallar"
    except ValueError:
        pass


# 10. decision duplicada -> error, sin sobrescribir silenciosamente

def test_decision_duplicada_falla():
    m = _movimiento()
    r = _resultado(m)
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
    try:
        ap.registrar_decision(r, decisiones, m["movimiento_id"], "RECHAZADO", "y", "2026-08-10T11:00:00-04:00")
        assert False, "debia fallar"
    except ValueError:
        pass
    # la decision original no debe haber sido alterada
    assert len(decisiones) == 1
    assert decisiones[0]["estado_humano"] == "APROBADO"
    assert decisiones[0]["revisor"] == "x"


# 11-14. la decision conserva sus datos, observacion puede ser null

def test_decision_conserva_movimiento_id_revisor_fecha():
    m = _movimiento()
    r = _resultado(m)
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "claudio.alcaino@taxtic.com", "2026-08-10T10:00:00-04:00", observacion="revisado ok")
    d = decisiones[0]
    assert d["movimiento_id"] == m["movimiento_id"]
    assert d["revisor"] == "claudio.alcaino@taxtic.com"
    assert d["fecha_decision"] == "2026-08-10T10:00:00-04:00"
    assert d["observacion"] == "revisado ok"


def test_observacion_puede_ser_null():
    m = _movimiento()
    r = _resultado(m)
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
    assert decisiones[0]["observacion"] is None


# 15-16. lote_id obligatorio, lotes distintos no comparten decisiones

def test_lote_id_obligatorio():
    for lote_id_invalido in (None, "", 0):
        try:
            ap.crear_lote(lote_id_invalido)
            assert False, f"debia fallar para lote_id={lote_id_invalido!r}"
        except ValueError:
            pass


def test_dos_lotes_distintos_no_comparten_decisiones():
    m = _movimiento()
    r = _resultado(m)
    lote_a = ap.crear_lote("2026-08-lote-A")
    lote_b = ap.crear_lote("2026-08-lote-B")
    lote_a2 = ap.registrar_decision_en_lote(lote_a, [r], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
    assert lote_a2["decisiones"]
    assert lote_b["decisiones"] == []  # el lote B nunca se toco
    assert lote_a["decisiones"] == []  # crear_lote/registrar_decision_en_lote no mutan el lote original


# 17-19. funciones puras: no modifican Movimiento ni ResultadoValidacion

def test_preparar_revision_no_modifica_movimiento():
    m = _movimiento()
    r = _resultado(m)
    antes = copy.deepcopy(m)
    ap.preparar_revision(m, r)
    assert m == antes


def test_preparar_revision_no_modifica_resultado_validacion():
    m = _movimiento()
    r = _resultado(m)
    antes = copy.deepcopy(r)
    ap.preparar_revision(m, r)
    assert r == antes


def test_registrar_decision_no_modifica_resultado_validacion():
    m = _movimiento()
    r = _resultado(m)
    antes = copy.deepcopy(r)
    ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
    assert r == antes


# 20. approval.py no agrega cuenta/debe/haber

def test_no_agrega_cuenta_debe_haber():
    m = _movimiento()
    r = _resultado(m)
    rev = ap.preparar_revision(m, r)
    for clave_prohibida in ("cuenta", "debe", "haber", "lineas_softland"):
        assert clave_prohibida not in rev
    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
    for clave_prohibida in ("cuenta", "debe", "haber", "lineas_softland"):
        assert clave_prohibida not in decisiones[0]
    import json
    texto = json.dumps(rev) + json.dumps(decisiones)
    for cuenta in ("10-01-003", "10-02-001", "10-04-001"):
        assert cuenta not in texto


# --- Caso Oro Transbank (multi-RUT, resuelto por respaldo) ---

REFERENCIA_RESPALDO_TEST = "respaldo-test-transbank-001"


def _movimiento_caso_oro_transbank():
    ruts = ["111111111", "222222222", "333333333"]
    datos = [(34053, 71649), (34052, 71649), (34008, 102112)]
    asignaciones = [
        _asignacion(i + 1, rut_cliente=ruts[i], numero_documento=doc, monto_aplicado=monto,
                    texto_original_celda=doc, fuente_respaldo=REFERENCIA_RESPALDO_TEST)
        for i, (doc, monto) in enumerate(datos)
    ]
    return _movimiento(
        monto_abono=241615, asignaciones=asignaciones, origen_pago="TRANSBANK",
        ruts_banco=ruts, nombres_banco=["CLIENTE A SPA", "CLIENTE B SPA", "CLIENTE C SPA"],
        respaldo_diferencia={"tipo": "TRANSBANK", "referencia": REFERENCIA_RESPALDO_TEST, "verificado": True},
    )


def test_caso_oro_transbank_apto_y_aprobable():
    m = _movimiento_caso_oro_transbank()
    r = _resultado(m)
    assert r["estado_motor"] == "APTO"
    rev = ap.preparar_revision(m, r)
    assert rev["puede_aprobar"] is True

    # 21. el resumen conserva exactamente los valores del Caso Oro, sin recalcular
    assert rev["monto_abono"] == 241615
    assert rev["suma_asignaciones"] == 245410
    assert rev["diferencia"] == 3795
    assert len(rev["asignaciones"]) == 3
    assert sorted(a["monto_aplicado"] for a in rev["asignaciones"]) == [71649, 71649, 102112]

    decisiones = ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "claudio.alcaino@taxtic.com", "2026-08-10T10:00:00-04:00")
    assert decisiones[0]["estado_humano"] == "APROBADO"
    assert decisiones[0]["movimiento_id"] == m["movimiento_id"]


# 22. movimiento REVISION multi-RUT (informacion parcial) no puede aprobarse

def test_revision_multi_rut_con_informacion_parcial_no_aprobable():
    ruts = ["111111111", "222222222", "333333333"]
    datos = [(34053, 71649), (34052, 71649), (34008, 102112)]
    # informacion parcial: solo 1 de las 3 asignaciones quedo resuelta con RUT
    asignaciones = [
        _asignacion(1, rut_cliente=ruts[0], numero_documento=datos[0][0], monto_aplicado=datos[0][1], texto_original_celda=datos[0][0], fuente_respaldo=REFERENCIA_RESPALDO_TEST),
        _asignacion(2, rut_cliente=None, numero_documento=datos[1][0], monto_aplicado=datos[1][1], texto_original_celda=datos[1][0]),
        _asignacion(3, rut_cliente=None, numero_documento=datos[2][0], monto_aplicado=datos[2][1], texto_original_celda=datos[2][0]),
    ]
    m = _movimiento(
        monto_abono=241615, asignaciones=asignaciones, origen_pago="TRANSBANK",
        ruts_banco=ruts,
        respaldo_diferencia={"tipo": "TRANSBANK", "referencia": REFERENCIA_RESPALDO_TEST, "verificado": True},
    )
    r = _resultado(m)
    assert r["estado_motor"] == "REVISION"
    rev = ap.preparar_revision(m, r)
    assert rev["puede_aprobar"] is False
    try:
        ap.registrar_decision(r, [], m["movimiento_id"], "APROBADO", "x", "2026-08-10T10:00:00-04:00")
        assert False, "debia fallar: REVISION no es aprobable aunque tenga informacion parcial"
    except ValueError:
        pass
