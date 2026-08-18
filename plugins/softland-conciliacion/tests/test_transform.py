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


val = _load("validate")
tr = _load("transform")


def _reglas_validate():
    return val._cargar_reglas()


def _reglas_transform():
    return tr._cargar_reglas()


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
                 fecha_pago="2026-07-01", banco="BCI", numero_conciliacion=None):
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
        "numero_conciliacion": numero_conciliacion if numero_conciliacion is not None else fila_origen - 2,
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
    return val.validar_movimiento(movimiento, _reglas_validate())


def _decision(movimiento_id, estado_humano="APROBADO", revisor="claudio.alcaino@taxtic.com",
              fecha_decision="2026-08-10T10:00:00-04:00", observacion=None):
    return {
        "movimiento_id": movimiento_id,
        "estado_humano": estado_humano,
        "revisor": revisor,
        "fecha_decision": fecha_decision,
        "observacion": observacion,
    }


def _suma(lineas, campo):
    return sum(l[campo] for l in lineas)


# 1-3. pago simple / multifactura / nunca Banco por factura

def test_pago_simple_apto_aprobado_dos_lineas():
    m = _movimiento()
    r = _resultado(m)
    assert r["estado_motor"] == "APTO"
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert len(lineas) == 2
    assert [l["tipo_linea"] for l in lineas] == ["BANCO", "CLIENTE"]
    assert _suma(lineas, "debe") == _suma(lineas, "haber") == 100000


def test_multifactura_un_banco_mas_n_cliente():
    asigs = [
        _asignacion(1, numero_documento=2001, monto_aplicado=30000, texto_original_celda=2001),
        _asignacion(2, numero_documento=2002, monto_aplicado=20000, texto_original_celda=2002),
    ]
    m = _movimiento(monto_abono=50000, asignaciones=asigs)
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert [l["tipo_linea"] for l in lineas] == ["BANCO", "CLIENTE", "CLIENTE"]
    bancos = [l for l in lineas if l["tipo_linea"] == "BANCO"]
    assert len(bancos) == 1  # nunca un banco por factura
    assert _suma(lineas, "debe") == _suma(lineas, "haber") == 50000


def test_nunca_genera_banco_por_factura_con_cuatro_asignaciones():
    asigs = [
        _asignacion(i, numero_documento=3000 + i, monto_aplicado=10000, texto_original_celda=3000 + i)
        for i in range(1, 5)
    ]
    m = _movimiento(monto_abono=40000, asignaciones=asigs)
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert sum(1 for l in lineas if l["tipo_linea"] == "BANCO") == 1
    assert sum(1 for l in lineas if l["tipo_linea"] == "CLIENTE") == 4


# 4-7. guardias de entrada

def test_apto_sin_decision_no_transforma():
    m = _movimiento()
    r = _resultado(m)
    assert r["estado_motor"] == "APTO"
    try:
        tr.transformar_movimiento(m, r, None, _reglas_transform())
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "SIN_DECISION_HUMANA"


def test_apto_rechazado_no_transforma():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"], estado_humano="RECHAZADO")
    try:
        tr.transformar_movimiento(m, r, d, _reglas_transform())
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "NO_APROBADO"


def test_revision_con_decision_manipulada_aprobado_no_transforma():
    a = _asignacion(numero_documento=None, monto_aplicado=1000, texto_original_celda="AJUSTAR",
                     tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m = _movimiento(monto_abono=1000, asignaciones=[a])
    r = _resultado(m)
    assert r["estado_motor"] == "REVISION"
    # decision "manipulada": construida a mano, sin pasar por approval.registrar_decision
    d = _decision(m["movimiento_id"], estado_humano="APROBADO")
    try:
        tr.transformar_movimiento(m, r, d, _reglas_transform())
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "ESTADO_MOTOR_NO_APTO"


def test_error_con_decision_manipulada_aprobado_no_transforma():
    m = _movimiento(monto_abono=0)
    r = _resultado(m)
    assert r["estado_motor"] == "ERROR"
    d = _decision(m["movimiento_id"], estado_humano="APROBADO")
    try:
        tr.transformar_movimiento(m, r, d, _reglas_transform())
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "ESTADO_MOTOR_NO_APTO"


# 8. movimiento_id mismatch -> error

def test_movimiento_id_mismatch_error():
    m = _movimiento(fila_origen=3)
    r = _resultado(m)
    d = _decision("mov-999999", estado_humano="APROBADO")
    try:
        tr.transformar_movimiento(m, r, d, _reglas_transform())
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "MOVIMIENTO_ID_INCONSISTENTE"

    r_otro = _resultado(_movimiento(fila_origen=4))
    d_ok = _decision(m["movimiento_id"])
    try:
        tr.transformar_movimiento(m, r_otro, d_ok, _reglas_transform())
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "MOVIMIENTO_ID_INCONSISTENTE"


# 9-10. resolucion de cuenta Banco desde configuracion

def test_banco_bci_obtiene_cuenta_desde_configuracion():
    m = _movimiento(banco="BCI")
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco_linea = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco_linea["cuenta"] == _reglas_transform()["banco"]["cuenta"] == "10-01-003"


def test_banco_no_configurado_falla_explicito():
    m = _movimiento(banco="SANTANDER")
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    try:
        tr.transformar_movimiento(m, r, d, _reglas_transform())
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "BANCO_NO_CONFIGURADO"


def test_no_existe_fallback_automatico_a_bci():
    """Un banco vacio/None tampoco debe caer silenciosamente a BCI."""
    m = _movimiento(banco=None)
    r = _resultado(m)
    # banco ausente ya deberia dar ERROR en validate.py, pero probamos
    # transform.py de forma aislada con una decision igualmente invalida
    # para confirmar que NO hay fallback a BCI en la resolucion de cuenta.
    reglas = _reglas_transform()
    try:
        tr._obtener_cuenta_banco(reglas, None)
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "BANCO_NO_CONFIGURADO"
    try:
        tr._obtener_cuenta_banco(reglas, "SANTANDER")
        assert False, "debia fallar"
    except tr.TransformError as e:
        assert e.codigo == "BANCO_NO_CONFIGURADO"


# 11-14. Linea Cliente

def test_linea_cliente_cuenta():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["cuenta"] == "10-02-001"


def test_linea_cliente_auxiliar_rut_normalizado():
    """Confirmado por Contabilidad (Fase 8.9), con evidencia real de
    Softland ('El Auxiliar "774957936" NO existe o esta inactivo'): el
    Codigo Auxiliar de Softland esta configurado SIN digito verificador --
    se quita el ultimo caracter del RUT normalizado (que siempre trae el DV
    pegado al final) exclusivamente para este campo."""
    m = _movimiento(asignaciones=[_asignacion(rut_cliente="765432101")], ruts_banco=["765432101"])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["auxiliar"] == "76543210"


def test_linea_cliente_tipo_documento_20():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["tipo_documento"] == "20"


def test_linea_cliente_nro_documento_es_factura():
    m = _movimiento(asignaciones=[_asignacion(numero_documento=1001)])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["numero_documento"] == 1001


# 15-16. glosas Cliente

def test_glosa_cliente_pago_normal():
    m = _movimiento(asignaciones=[_asignacion(numero_documento=1001)])
    r = _resultado(m)
    assert r["tipo_pago"] in ("SIMPLE", "MULTIFACTURA")
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["glosa"] == "PAGO F 1001"


def test_glosa_cliente_transbank():
    ruts = ["111111111", "222222222", "333333333"]
    datos = [(34053, 71649), (34052, 71649), (34008, 102112)]
    asigs = [
        _asignacion(i + 1, rut_cliente=ruts[i], nombre_cliente=f"CLIENTE {chr(65+i)} SPA",
                    numero_documento=doc, monto_aplicado=monto, texto_original_celda=doc,
                    fuente_respaldo="respaldo-test-transbank-001")
        for i, (doc, monto) in enumerate(datos)
    ]
    m = _movimiento(
        fila_origen=20, monto_abono=241615, asignaciones=asigs, origen_pago="TRANSBANK",
        ruts_banco=ruts,
        respaldo_diferencia={"tipo": "TRANSBANK", "referencia": "respaldo-test-transbank-001", "verificado": True},
    )
    r = _resultado(m)
    assert r["tipo_pago"] == "TRANSBANK"
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    clientes = [l for l in lineas if l["tipo_linea"] == "CLIENTE"]
    assert clientes[0]["glosa"] == "PAGO CLIENTES F 34053"


# 17-18. Linea Banco: TB y numero_docto_conciliacion

def test_banco_usa_tipo_conciliacion_tb():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["tipo_docto_conciliacion"] == "TB"


def test_banco_numero_docto_conciliacion_es_numero_conciliacion_del_movimiento():
    m = _movimiento(fila_origen=9, numero_conciliacion=7)
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["numero_docto_conciliacion"] == 7 == m["numero_conciliacion"]


# 19-20. glosa Banco: nombre + folios, orden conservado

def test_glosa_banco_contiene_nombre_y_folio():
    m = _movimiento(asignaciones=[_asignacion(nombre_cliente="CLIENTE UNO SPA", numero_documento=1001)])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert "CLIENTE UNO SPA" in banco["glosa"]
    assert "1001" in banco["glosa"]


def test_glosa_banco_multifactura_conserva_orden_de_folios():
    asigs = [
        _asignacion(1, numero_documento=32007, monto_aplicado=50000, texto_original_celda=32007),
        _asignacion(2, numero_documento=33100, monto_aplicado=50000, texto_original_celda=33100),
    ]
    m = _movimiento(monto_abono=100000, asignaciones=asigs)
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert "F32007-33100" in banco["glosa"]


# Fase 4.1: glosa Banco confirmada -- un cliente (con nombre) vs multicliente (sin nombre)

def test_glosa_banco_un_cliente_una_factura_texto_exacto():
    m = _movimiento(asignaciones=[_asignacion(rut_cliente="765432101", nombre_cliente="CLIENTE ABC", numero_documento=32007)])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["glosa"] == "PAGO CLIENTE CLIENTE ABC F32007"


def test_glosa_banco_un_cliente_varias_facturas_texto_exacto():
    asigs = [
        _asignacion(1, rut_cliente="765432101", nombre_cliente="CLIENTE ABC", numero_documento=32007, monto_aplicado=50000, texto_original_celda=32007),
        _asignacion(2, rut_cliente="765432101", nombre_cliente="CLIENTE ABC", numero_documento=33100, monto_aplicado=50000, texto_original_celda=33100),
    ]
    m = _movimiento(monto_abono=100000, asignaciones=asigs)
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["glosa"] == "PAGO CLIENTE CLIENTE ABC F32007-33100"


def test_glosa_banco_multicliente_sin_nombre_texto_exacto():
    asigs = [
        _asignacion(1, rut_cliente="111111111", nombre_cliente="CLIENTE A SPA", numero_documento=32007, monto_aplicado=50000, texto_original_celda=32007),
        _asignacion(2, rut_cliente="222222222", nombre_cliente="CLIENTE B SPA", numero_documento=33100, monto_aplicado=50000, texto_original_celda=33100),
    ]
    m = _movimiento(monto_abono=100000, asignaciones=asigs, ruts_banco=["111111111", "222222222"])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["glosa"] == "PAGO CLIENTE F32007-33100"


def test_glosa_banco_multicliente_no_contiene_ningun_nombre_de_cliente():
    asigs = [
        _asignacion(1, rut_cliente="111111111", nombre_cliente="CLIENTE A SPA", numero_documento=32007, monto_aplicado=50000, texto_original_celda=32007),
        _asignacion(2, rut_cliente="222222222", nombre_cliente="CLIENTE B SPA", numero_documento=33100, monto_aplicado=50000, texto_original_celda=33100),
    ]
    m = _movimiento(monto_abono=100000, asignaciones=asigs, ruts_banco=["111111111", "222222222"])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert "CLIENTE A SPA" not in banco["glosa"]
    assert "CLIENTE B SPA" not in banco["glosa"]


def test_glosa_banco_multicliente_no_usa_separador_inventado():
    asigs = [
        _asignacion(1, rut_cliente="111111111", nombre_cliente="CLIENTE A SPA", numero_documento=32007, monto_aplicado=50000, texto_original_celda=32007),
        _asignacion(2, rut_cliente="222222222", nombre_cliente="CLIENTE B SPA", numero_documento=33100, monto_aplicado=50000, texto_original_celda=33100),
        _asignacion(3, rut_cliente="333333333", nombre_cliente="CLIENTE C SPA", numero_documento=34008, monto_aplicado=50000, texto_original_celda=34008),
    ]
    m = _movimiento(monto_abono=150000, asignaciones=asigs, ruts_banco=["111111111", "222222222", "333333333"])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    for separador_no_permitido in (" / ", "/", ",", " Y ", " y "):
        assert separador_no_permitido not in banco["glosa"]


def test_glosa_banco_folios_no_se_ordenan_ni_interpretan_como_rango():
    asigs = [
        _asignacion(1, numero_documento=500, monto_aplicado=10000, texto_original_celda=500),
        _asignacion(2, numero_documento=100, monto_aplicado=10000, texto_original_celda=100),
        _asignacion(3, numero_documento=300, monto_aplicado=10000, texto_original_celda=300),
    ]
    m = _movimiento(monto_abono=30000, asignaciones=asigs)
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    # se conserva el orden de las Asignacion tal cual (500, 100, 300);
    # nunca se ordena numericamente (100-300-500) ni se interpreta como rango.
    assert "F500-100-300" in banco["glosa"]


# 21-25. Caso Oro Transbank

def _movimiento_caso_oro():
    ruts = ["111111111", "222222222", "333333333"]
    datos = [(34053, 71649), (34052, 71649), (34008, 102112)]
    asigs = [
        _asignacion(i + 1, rut_cliente=ruts[i], nombre_cliente=f"CLIENTE {chr(65+i)} SPA",
                    numero_documento=doc, monto_aplicado=monto, texto_original_celda=doc,
                    fuente_respaldo="respaldo-test-transbank-001")
        for i, (doc, monto) in enumerate(datos)
    ]
    return _movimiento(
        fila_origen=20, monto_abono=241615, asignaciones=asigs, origen_pago="TRANSBANK",
        ruts_banco=ruts,
        respaldo_diferencia={"tipo": "TRANSBANK", "referencia": "respaldo-test-transbank-001", "verificado": True},
    )


def test_caso_oro_genera_cinco_lineas():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    assert r["estado_motor"] == "APTO"
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert len(lineas) == 5
    assert [l["tipo_linea"] for l in lineas] == ["BANCO", "CLIENTE", "CLIENTE", "CLIENTE", "DIFERENCIA_TRANSBANK"]


def test_caso_oro_glosa_banco_multicliente_confirmada():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["glosa"] == "PAGO CLIENTE F34053-34052-34008"


def test_caso_oro_banco_debe_241615():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["debe"] == 241615
    assert banco["haber"] == 0


def test_caso_oro_diferencia_debe_3795():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["debe"] == 3795
    assert diferencia["haber"] == 0


def test_caso_oro_clientes_haber_total_245410():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    clientes = [l for l in lineas if l["tipo_linea"] == "CLIENTE"]
    assert _suma(clientes, "haber") == 245410
    assert sorted(l["haber"] for l in clientes) == [71649, 71649, 102112]


def test_caso_oro_total_debe_igual_total_haber():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert _suma(lineas, "debe") == _suma(lineas, "haber") == 245410


# 26-31. Linea Diferencia Transbank

def test_diferencia_cuenta_desde_configuracion():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["cuenta"] == _reglas_transform()["cuentas"]["diferencia_transbank"] == "10-04-001"


def test_diferencia_auxiliar_fijo():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["auxiliar"] == "96689310"


def test_diferencia_tipo_documento_cero():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["tipo_documento"] == 0


def test_diferencia_nro_documento_cero():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["numero_documento"] == 0


def test_diferencia_sin_tb():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["tipo_docto_conciliacion"] == 0
    assert diferencia["numero_docto_conciliacion"] == 0


def test_diferencia_glosa_exacta():
    m = _movimiento_caso_oro()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["glosa"] == "DIFERENCIA POR COBRO COMISION TRANSBANK"


# 32. diferencia no respaldada no llega legitimamente a transformacion

def test_diferencia_no_respaldada_no_llega_a_transformacion():
    m = _movimiento_caso_oro()
    m["respaldo_diferencia"] = None  # sin respaldo
    r = _resultado(m)
    assert r["estado_motor"] == "REVISION"  # nunca deberia ser APTO sin respaldo
    d = _decision(m["movimiento_id"], estado_humano="APROBADO")  # decision manipulada, no deberia poder existir en la practica
    try:
        tr.transformar_movimiento(m, r, d, _reglas_transform())
        assert False, "debia fallar: REVISION no llega a transformacion"
    except tr.TransformError as e:
        assert e.codigo == "ESTADO_MOTOR_NO_APTO"


# 33-39. campos_1_a_61

def test_campos_1_a_61_exactamente_61_claves():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    for l in lineas:
        assert len(l["campos_1_a_61"]) == 61
        assert set(l["campos_1_a_61"].keys()) == {str(n) for n in range(1, 62)}


def test_campos_1_2_3_correctos():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["campos_1_a_61"]["1"] == "10-01-003"
    assert banco["campos_1_a_61"]["2"] == 100000
    assert banco["campos_1_a_61"]["3"] == 0
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["campos_1_a_61"]["1"] == "10-02-001"
    assert cliente["campos_1_a_61"]["2"] == 0
    assert cliente["campos_1_a_61"]["3"] == 100000


def test_posiciones_17_18_solo_en_banco():
    m = _movimiento(numero_conciliacion=7)
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert banco["campos_1_a_61"]["17"] == "TB"
    assert banco["campos_1_a_61"]["18"] == 7
    assert cliente["campos_1_a_61"]["17"] == 0
    assert cliente["campos_1_a_61"]["18"] == 0


def test_posiciones_19_a_25_correctas_en_cliente():
    """Confirmado por Contabilidad (Fase 7.3): posicion 20 = 'TB' (no el tipo
    de documento), posicion 24 = tipo de documento de la factura ('20'),
    posicion 25 = folio REPETIDO (ademas de la posicion 21)."""
    m = _movimiento(asignaciones=[_asignacion(rut_cliente="765432101", numero_documento=1001)])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["campos_1_a_61"]["19"] == "76543210"  # RUT sin DV (Fase 8.9)
    assert cliente["campos_1_a_61"]["20"] == "TB"
    assert cliente["campos_1_a_61"]["21"] == 1001
    assert cliente["campos_1_a_61"]["24"] == "20"
    assert cliente["campos_1_a_61"]["25"] == 1001
    assert cliente["tipo_docto_conciliacion"] == "TB"
    assert cliente["numero_docto_referencia"] == 1001


def test_posiciones_19_a_25_correctas_con_otro_folio_no_hardcodeado():
    """Mismo contrato que test_posiciones_19_a_25_correctas_en_cliente pero
    con un folio distinto (99999), para probar que el mapeo no depende de
    ningun valor hardcodeado en transform.py."""
    m = _movimiento(asignaciones=[_asignacion(rut_cliente="111222333", numero_documento=99999)])
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["campos_1_a_61"]["19"] == "11122233"  # RUT sin DV (Fase 8.9)
    assert cliente["campos_1_a_61"]["20"] == "TB"
    assert cliente["campos_1_a_61"]["21"] == 99999
    assert cliente["campos_1_a_61"]["24"] == "20"
    assert cliente["campos_1_a_61"]["25"] == 99999
    assert cliente["numero_docto_referencia"] == 99999


def test_columnas_27_a_36_son_cero():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    for l in lineas:
        for n in range(27, 37):
            assert l["campos_1_a_61"][str(n)] == 0


def test_columnas_39_a_58_son_cero():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    for l in lineas:
        for n in range(39, 59):
            assert l["campos_1_a_61"][str(n)] == 0


def test_columnas_59_a_61_son_cero():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
    for l in lineas:
        for n in (59, 60, 61):
            assert l["campos_1_a_61"][str(n)] == 0


# 40-41. cuadratura

def test_suma_debe_igual_suma_haber_en_todos_los_casos():
    for m in (_movimiento(), _movimiento_caso_oro()):
        r = _resultado(m)
        d = _decision(m["movimiento_id"])
        lineas = tr.transformar_movimiento(m, r, d, _reglas_transform())
        assert _suma(lineas, "debe") == _suma(lineas, "haber")


def test_descuadre_interno_falla_sin_salida_parcial():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    reglas_rotas = copy.deepcopy(_reglas_transform())
    reglas_rotas["banco"]["cuenta"] = "10-01-003"
    # forzamos un descuadre modificando la tolerancia de forma imposible de
    # cumplir via un monto_abono distinto a la suma de asignaciones, sin
    # pasar por validate.py (que ya lo hubiera bloqueado) -- construimos un
    # ResultadoValidacion "manipulado" marcado APTO para poder ejercer la
    # guardia interna de transform.py de forma aislada.
    r_manipulado = copy.deepcopy(r)
    r_manipulado["estado_motor"] = "APTO"
    m_descuadrado = copy.deepcopy(m)
    m_descuadrado["monto_abono"] = 999999  # ya no coincide con la suma de asignaciones
    try:
        tr.transformar_movimiento(m_descuadrado, r_manipulado, d, _reglas_transform())
        assert False, "debia fallar por descuadre"
    except tr.TransformError as e:
        assert e.codigo == "DESCUADRE_INTERNO"


# 42-45. no modifica entradas, no serializa archivo fisico

def test_no_modifica_movimiento():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    antes = copy.deepcopy(m)
    tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert m == antes


def test_no_modifica_resultado_validacion():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    antes = copy.deepcopy(r)
    tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert r == antes


def test_no_modifica_decision_humana():
    m = _movimiento()
    r = _resultado(m)
    d = _decision(m["movimiento_id"])
    antes = copy.deepcopy(d)
    tr.transformar_movimiento(m, r, d, _reglas_transform())
    assert d == antes


def test_no_serializa_archivo_fisico():
    """transform.py no debe tener ninguna nocion de delimitador/encoding/
    header/CSV/TXT -- eso pertenece a export_softland.py, que no existe."""
    assert not hasattr(tr, "csv")
    assert not hasattr(tr, "export_softland")
    assert not hasattr(tr, "escribir_archivo_softland")
    assert not hasattr(tr, "serializar_softland")


# 46. sin fallback automatico a BCI -- ver test_no_existe_fallback_automatico_a_bci arriba


# --- transformacion de lote ---

def test_transformar_lote_separa_transformados_y_excluidos():
    m_apto = _movimiento(fila_origen=3)
    a_revision = _asignacion(numero_documento=None, monto_aplicado=1000, texto_original_celda="AJUSTAR",
                              tipo_documento="DESCONOCIDO", requiere_revision=True, motivo_revision="TEXTO_NO_FACTURA")
    m_revision = _movimiento(fila_origen=7, monto_abono=1000, asignaciones=[a_revision])

    r_apto = _resultado(m_apto)
    r_revision = _resultado(m_revision)
    decisiones = [_decision(m_apto["movimiento_id"])]

    resultado = tr.transformar_lote(
        [m_apto, m_revision], [r_apto, r_revision], decisiones, _reglas_transform()
    )
    assert m_apto["movimiento_id"] in resultado["transformados"]
    assert len(resultado["transformados"][m_apto["movimiento_id"]]) == 2
    excluidos_ids = {e["movimiento_id"] for e in resultado["excluidos"]}
    assert m_revision["movimiento_id"] in excluidos_ids
    motivo = next(e["motivo"] for e in resultado["excluidos"] if e["movimiento_id"] == m_revision["movimiento_id"])
    # REVISION falla en la guardia de estado_motor antes de siquiera llegar
    # a comprobar si existe una DecisionHumana (fail-fast en el problema mas
    # fundamental primero).
    assert motivo == "ESTADO_MOTOR_NO_APTO"


def test_transformar_lote_nunca_produce_lineas_para_no_aprobados():
    m = _movimiento()
    r = _resultado(m)
    resultado = tr.transformar_lote([m], [r], [], _reglas_transform())
    assert resultado["transformados"] == {}
    assert resultado["excluidos"][0]["motivo"] == "SIN_DECISION_HUMANA"
