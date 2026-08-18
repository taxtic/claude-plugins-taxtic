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
tr = _load("transform")
es = _load("export_softland")

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
EXPECTED_DIR = os.path.join(os.path.dirname(__file__), "expected")


def _reglas_validate():
    return val._cargar_reglas()


def _reglas_transform():
    return tr._cargar_reglas()


def _layouts():
    return es._cargar_layouts()


def _asignacion(bloque_indice=1, rut_cliente="765432101", nombre_cliente="CLIENTE ABC",
                 categoria_ingreso="Ingresos por Plan Premium", tipo_documento="FACTURA",
                 numero_documento=1001, monto_aplicado=100000, texto_original_celda=1001,
                 requiere_revision=False, motivo_revision=None, fuente_respaldo=None):
    return {
        "bloque_indice": bloque_indice, "rut_cliente": rut_cliente, "nombre_cliente": nombre_cliente,
        "categoria_ingreso": categoria_ingreso, "tipo_documento": tipo_documento,
        "numero_documento": numero_documento, "monto_aplicado": monto_aplicado,
        "texto_original_celda": texto_original_celda, "requiere_revision": requiere_revision,
        "motivo_revision": motivo_revision, "fuente_respaldo": fuente_respaldo,
    }


def _movimiento(fila_origen=3, monto_abono=100000, asignaciones=None, origen_pago="TRANSFERENCIA",
                 ruts_banco=None, nombres_banco=None, respaldo_diferencia=None, diferencia=None,
                 fecha_pago="2026-07-01", banco="BCI", numero_conciliacion=None):
    asignaciones = [_asignacion()] if asignaciones is None else asignaciones
    ruts_banco = ruts_banco if ruts_banco is not None else [asignaciones[0]["rut_cliente"]]
    nombres_banco = nombres_banco if nombres_banco is not None else [asignaciones[0]["nombre_cliente"]]
    suma = sum(a.get("monto_aplicado") or 0 for a in asignaciones)
    if diferencia is None:
        diferencia = suma - (monto_abono or 0)
    return {
        "movimiento_id": f"mov-{fila_origen:06d}", "fila_origen": fila_origen, "hoja_origen": "Hoja1",
        "fecha_pago": fecha_pago, "numero_conciliacion": numero_conciliacion if numero_conciliacion is not None else fila_origen - 2,
        "descripcion_banco": "MENSUALIDAD JULIO 26", "banco": banco, "origen_pago": origen_pago,
        "monto_abono": monto_abono, "ruts_banco": ruts_banco, "nombres_banco": nombres_banco,
        "asignaciones": asignaciones, "suma_asignaciones": suma, "diferencia": diferencia,
        "respaldo_diferencia": respaldo_diferencia, "advertencias": [], "senales_revision": [],
        "errores_normalizacion": [], "campos_originales": {},
    }


def _decision(movimiento_id, estado_humano="APROBADO"):
    return {"movimiento_id": movimiento_id, "estado_humano": estado_humano, "revisor": "claudio.alcaino@taxtic.com",
            "fecha_decision": "2026-08-10T10:00:00-04:00", "observacion": None}


def _lineas_para(movimiento, decision_override=None):
    r = val.validar_movimiento(movimiento, _reglas_validate())
    d = decision_override if decision_override is not None else _decision(movimiento["movimiento_id"])
    return tr.transformar_movimiento(movimiento, r, d, _reglas_transform())


def _lineas_caso_simple():
    m = _movimiento()
    return _lineas_para(m)


def _lineas_multifactura():
    asigs = [
        _asignacion(1, numero_documento=32007, monto_aplicado=30000, texto_original_celda=32007),
        _asignacion(2, numero_documento=33100, monto_aplicado=70000, texto_original_celda=33100),
    ]
    m = _movimiento(monto_abono=100000, asignaciones=asigs)
    return _lineas_para(m)


def _lineas_caso_oro():
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
    return _lineas_para(m)


# 1-2. perfil default / perfil desconocido

def test_perfil_default_es_oficial_61():
    """Fase 8.8: OFICIAL_61 pasa a ser el perfil por defecto, respaldado por
    evidencia real directa (archivo de carga vigente + estructura oficial
    exportada de Softland, coincidentes campo a campo). OPERATIVO_62 queda
    disponible solo por historial, sin evidencia real de exito."""
    layouts = _layouts()
    assert layouts["perfil_default"] == "OFICIAL_61"
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, layouts=layouts)  # sin --perfil explicito
    assert contenido  # no lanza excepcion, usa OFICIAL_61 implicitamente


def test_perfil_desconocido_falla_explicito():
    lineas = _lineas_caso_simple()
    try:
        es.exportar(lineas, nombre_perfil="INVENTADO_99", layouts=_layouts())
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "PERFIL_LAYOUT_NO_CONFIGURADO"


# 3-6. OPERATIVO_62 estructura fisica

def test_operativo_62_crea_62_posiciones_logicas():
    layouts = _layouts()
    perfil = es._obtener_perfil(layouts, "OPERATIVO_62")
    assert perfil["total_columnas"] == 62
    lineas = _lineas_caso_simple()
    fila = es.construir_fila(lineas[0], perfil)
    assert len(fila) == 62


def test_trailing_comma_presente():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    assert primera_fila.endswith(",")


def test_split_coma_da_63_campos():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    assert len(primera_fila.split(",")) == 63


def test_campo_63_vacio():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    assert primera_fila.split(",")[62] == ""


# 7-11. formato fisico general

def test_sin_encabezado():
    lineas = _lineas_multifactura()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    # la primera fila debe empezar con la cuenta Banco (dato), no un nombre de columna
    assert primera_fila.startswith("10-01-003,")


def test_utf8_sin_bom():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    b = contenido.encode("utf-8")
    assert b[:3] != bytes([0xEF, 0xBB, 0xBF])


def test_crlf_entre_filas():
    lineas = _lineas_multifactura()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert "\r\n" in contenido
    assert "\n" not in contenido.replace("\r\n", "")  # no hay LF suelto


def test_crlf_final():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert contenido.endswith("\r\n")


def test_sin_comillas():
    lineas = _lineas_multifactura()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert '"' not in contenido


# 12-13. fechas

def test_fecha_ddmmaaaa_a_ddmmaaaa_guion():
    lineas = _lineas_caso_simple()
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["fecha_emision"] == "01/07/2026"  # confirma supuesto de entrada
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(cliente, perfil)
    pos = perfil["posiciones"]["CLIENTE"]["fecha_emision"]
    assert fila[pos - 1] == "01-07-2026"


def test_fecha_invalida_falla():
    lineas = _lineas_caso_simple()
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    cliente_malo = copy.deepcopy(cliente)
    cliente_malo["fecha_emision"] = "2026/07/01"  # formato incorrecto (no DD/MM/AAAA)
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(cliente_malo, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "FECHA_NO_SERIALIZABLE"


# 14-17. montos

def test_debe_entero_puro():
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert isinstance(banco["debe"], int)
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(banco, perfil)
    pos = perfil["posiciones"]["BANCO"]["debe"]
    assert fila[pos - 1] == 100000


def test_haber_entero_puro():
    lineas = _lineas_caso_simple()
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(cliente, perfil)
    pos = perfil["posiciones"]["CLIENTE"]["haber"]
    assert fila[pos - 1] == 100000
    assert isinstance(fila[pos - 1], int)


def test_monto_decimal_falla():
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    banco["debe"] = 100000.00
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(banco, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "MONTO_NO_SERIALIZABLE"


def test_monto_negativo_falla():
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    banco["debe"] = -100000
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(banco, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "MONTO_NO_SERIALIZABLE"


# 18-23. seguridad de textos / glosas

def test_glosa_con_coma_falla():
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    banco["glosa"] = "PAGO CLIENTE A, B F1001"
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(banco, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "VALOR_NO_SERIALIZABLE"


def test_glosa_con_cr_falla():
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    banco["glosa"] = "PAGO CLIENTE\rABC F1001"
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(banco, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "VALOR_NO_SERIALIZABLE"


def test_glosa_con_lf_falla():
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    banco["glosa"] = "PAGO CLIENTE\nABC F1001"
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(banco, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "VALOR_NO_SERIALIZABLE"


def test_ningun_texto_se_limpia_silenciosamente():
    """Confirma que el error se lanza -- no que la coma/CR/LF se elimine."""
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    glosa_original = "PAGO CLIENTE A, B F1001"
    banco["glosa"] = glosa_original
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(banco, perfil)
        assert False, "debia fallar, no limpiar"
    except es.ExportError:
        pass
    assert banco["glosa"] == glosa_original  # no fue mutada


def test_glosa_mayor_a_255_falla():
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    banco["glosa"] = "A" * 256
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(banco, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "GLOSA_EXCEDE_LONGITUD_MAXIMA"


def test_glosa_de_71_caracteres_se_acepta():
    lineas = _lineas_caso_simple()
    banco = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "BANCO"))
    banco["glosa"] = "A" * 71  # observado como real en captura.csv (Fase 5.2)
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(banco, perfil)  # no debe lanzar
    pos = perfil["posiciones"]["BANCO"]["glosa"]
    assert fila[pos - 1] == "A" * 71


# 24-30. posiciones OPERATIVO_62

def test_columnas_1_a_36_respetan_posicion_esperada():
    """Confirmado por Contabilidad (Fase 7.3): CLIENTE lleva 'TB' en la
    posicion 20 (no el tipo de documento), que se desplaza a la 24; el
    folio se repite en la 25. BANCO conserva 17/18 sin cambios.

    Fase 8.7 (evidencia real captura.csv, Fase 8.6): BANCO nunca mapea
    'haber' ni 'auxiliar' (nunca aplican a una linea Banco -- siempre
    debito puro, sin auxiliar); CLIENTE nunca mapea 'debe' (nunca aplica a
    una linea Cliente -- siempre credito puro). Esos campos siguen
    existiendo en el modelo semantico LineaSoftland con su valor interno
    (0), pero no se fuerzan a una posicion fisica."""
    layouts = _layouts()
    perfil = layouts["perfiles"]["OPERATIVO_62"]
    esperado_banco = {
        "cuenta": 1, "debe": 2, "glosa": 4,
        "tipo_docto_conciliacion": 17, "numero_docto_conciliacion": 18,
    }
    esperado_cliente = {
        "cuenta": 1, "haber": 3, "glosa": 4,
        "auxiliar": 19, "tipo_docto_conciliacion": 20, "numero_documento": 21,
        "fecha_emision": 22, "fecha_vencimiento": 23, "tipo_documento": 24,
        "numero_docto_referencia": 25,
    }
    for campo, pos in esperado_banco.items():
        assert perfil["posiciones"]["BANCO"][campo] == pos
    for campo, pos in esperado_cliente.items():
        assert perfil["posiciones"]["CLIENTE"][campo] == pos
    assert "haber" not in perfil["posiciones"]["BANCO"]
    assert "auxiliar" not in perfil["posiciones"]["BANCO"]
    assert "debe" not in perfil["posiciones"]["CLIENTE"]


def test_operativo_62_documento_desde_37():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["posiciones_catalogo"]["numero_documento_desde"] == 37


def test_operativo_62_documento_hasta_38():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["posiciones_catalogo"]["numero_documento_hasta"] == 38


def test_operativo_62_agrupacion_39():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["posiciones_catalogo"]["numero_agrupacion_comprobante"] == 39


def test_operativo_62_graba_detalle_40():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["posiciones_catalogo"]["graba_detalle_libro"] == 40


def test_operativo_62_documento_nulo_41():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["posiciones_catalogo"]["documento_nulo"] == 41


def test_operativo_62_cuota_62():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["posiciones_catalogo"]["numero_cuota_pago"] == 62


# --- Fase 8.1/8.2: evidencia productiva real -- Softland rechazo 0 y luego
# vacio en la posicion 40 ("Graba el detalle de libro (S/N)"), documentado
# como campo S/N. Se adopta como HIPOTESIS (no confirmada aun; pendiente de
# un tercer intento real) 'N' en la posicion 40 para este flujo. La posicion
# 41 (documento_nulo) permanece vacia por evidencia de captura.csv, sin
# haber sido validada aisladamente todavia (Softland nunca llego a
# procesarla en los intentos reales, que se detuvieron en la posicion 40). ---

def test_operativo_62_valores_catalogo_declara_40_en_n_y_41_vacio():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["valores_catalogo"]["graba_detalle_libro"] == "N"
    assert perfil["valores_catalogo"]["documento_nulo"] == ""


def test_operativo_62_fila_fisica_posicion_40_es_n_literal():
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(banco, perfil)
    assert fila[40 - 1] == "N"
    assert fila[40 - 1] != 0
    assert fila[40 - 1] != "0"
    assert fila[40 - 1] != ""


def test_operativo_62_fila_fisica_posicion_41_permanece_vacia():
    lineas = _lineas_caso_simple()
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(cliente, perfil)
    assert fila[41 - 1] == ""
    assert fila[41 - 1] != 0
    assert fila[41 - 1] != "0"


def test_operativo_62_csv_serializado_mantiene_n_literal_en_posicion_40():
    """Defensa de regresion: el serializer debe conservar 'N' literal en la
    posicion 40 (no '0', no vacio) y mantener la 41 vacia entre comas."""
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    for fila_texto in contenido.split("\r\n"):
        if not fila_texto:
            continue
        campos = fila_texto.split(",")
        assert campos[40 - 1] == "N"
        assert campos[41 - 1] == ""


def test_oficial_61_declara_valores_catalogo_confirmados_fase_8_8():
    """Fase 8.8: a diferencia de fases anteriores, OFICIAL_61 SI tiene
    evidencia real directa (archivo de carga vigente, 42 filas) que
    confirma 'documento_nulo'='N' literal (nunca vacio) y varios campos de
    texto siempre vacios cuando no aplican."""
    perfil = _layouts()["perfiles"]["OFICIAL_61"]
    assert perfil["valores_catalogo"]["documento_nulo"] == "N"
    assert perfil["valores_catalogo"]["graba_detalle_libro"] == "N"
    assert perfil["valores_catalogo"]["codigo_condicion_venta"] == ""


# --- Fase 8.4: evidencia productiva real (V3) -- captura.csv deja SIEMPRE
# vacias las posiciones sin dato de negocio (no solo 40/41); el error nuevo
# de Softland en V3 ("valores no numericos o muy grandes en un campo
# numerico") aparece justo despues de que el error de 'Graba el detalle de
# libro' desaparece, con ~30 posiciones aun en 0 como relleno generico. Se
# adopta relleno fisico vacio para OPERATIVO_62 en su totalidad, sin tocar
# ningun campo con valor semantico explicito. ---

def test_operativo_62_valor_relleno_no_utilizado_es_vacio():
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["valor_relleno_no_utilizado"] == ""


def test_oficial_61_valor_relleno_no_utilizado_es_cero_texto():
    """Fase 8.8: el archivo de carga real (42 filas) muestra la MAYORIA de
    posiciones numericas no utilizadas en '0' (nunca vacio) -- por eso el
    relleno generico de OFICIAL_61 es '0' (string, para serializar tal
    cual). Los campos de TEXTO no utilizados se resuelven aparte via
    'valores_catalogo' (vacios), no cambiando este relleno generico."""
    perfil = _layouts()["perfiles"]["OFICIAL_61"]
    assert perfil["valor_relleno_no_utilizado"] == "0"


def test_operativo_62_posiciones_de_relleno_generico_quedan_vacias():
    """Posiciones que ningun campo semantico de LineaSoftland puebla para
    ESTE tipo_linea (relleno puro) deben quedar vacias, no en '0'. Cubre el
    bloque 5-16, partes de 26-39 y todo 42-61 identificado en Fase 8.3."""
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila_banco = es.construir_fila(banco, perfil)
    fila_cliente = es.construir_fila(cliente, perfil)
    posiciones_relleno_puro = list(range(5, 17)) + [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39] + list(range(42, 62))
    for pos in posiciones_relleno_puro:
        assert fila_banco[pos - 1] == "", f"posicion {pos} BANCO deberia ser relleno vacio"
        assert fila_cliente[pos - 1] == "", f"posicion {pos} CLIENTE deberia ser relleno vacio"


# --- Fase 8.7: evidencia productiva real (Fase 8.6) -- el lado de
# Debe/Haber que nunca aplica a un tipo_linea (BANCO.haber, CLIENTE.debe) y
# el Auxiliar cuando no aplica (BANCO.auxiliar) deben quedar FISICAMENTE
# vacios, no en "0": captura.csv (33/33 filas reales) nunca muestra "0" en
# esos casos. El modelo semantico de LineaSoftland SIGUE guardando 0
# internamente (indispensable para cuadratura); solo cambia que
# posiciones["BANCO"]/["CLIENTE"] ya no mapean esos campos, asi que
# construir_fila() nunca los escribe fisicamente. ---

def test_operativo_62_banco_haber_sigue_siendo_cero_semantico_interno():
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["haber"] == 0  # el modelo semantico no cambia


def test_operativo_62_cliente_debe_sigue_siendo_cero_semantico_interno():
    lineas = _lineas_caso_simple()
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    assert cliente["debe"] == 0  # el modelo semantico no cambia


def test_operativo_62_banco_haber_fisicamente_vacio_no_aplica():
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    assert "haber" not in perfil["posiciones"]["BANCO"]
    fila = es.construir_fila(banco, perfil)
    assert fila[3 - 1] == ""
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    assert primera_fila.split(",")[3 - 1] == ""


def test_operativo_62_cliente_debe_fisicamente_vacio_no_aplica():
    lineas = _lineas_caso_simple()
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    assert "debe" not in perfil["posiciones"]["CLIENTE"]
    fila = es.construir_fila(cliente, perfil)
    assert fila[2 - 1] == ""
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    segunda_fila = contenido.split("\r\n")[1]
    assert segunda_fila.split(",")[2 - 1] == ""


def test_operativo_62_banco_auxiliar_fisicamente_vacio_no_aplica():
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["auxiliar"] == 0  # el modelo semantico no cambia
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    assert "auxiliar" not in perfil["posiciones"]["BANCO"]
    fila = es.construir_fila(banco, perfil)
    assert fila[19 - 1] == ""
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    assert primera_fila.split(",")[19 - 1] == ""


def test_operativo_62_cuadratura_semantica_no_depende_de_la_fila_fisica():
    """Aunque BANCO.haber y CLIENTE.debe ya no aparezcan fisicamente, la
    cuadratura debe seguir calculandose desde LineaSoftland (modelo
    semantico), nunca releyendo los campos vacios del CSV."""
    lineas = _lineas_caso_simple()
    total_debe = sum(l["debe"] for l in lineas)
    total_haber = sum(l["haber"] for l in lineas)
    assert total_debe == total_haber == 100000
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())  # no debe lanzar DESCUADRE_EXPORTACION
    assert contenido


def test_operativo_62_numero_conciliacion_cero_real_si_serializa_cero():
    """Proteccion de la distincion: un campo que SI aplica a un tipo_linea
    (BANCO.numero_docto_conciliacion, sin cambios en Fase 8.7) debe seguir
    serializando '0' cuando su valor real es cero -- nunca vacio. Nota:
    DIFERENCIA_TRANSBANK.debe NUNCA puede ser 0 en este sistema (validate.py
    solo clasifica tipo_pago='TRANSBANK', y por lo tanto solo se crea la
    linea Diferencia, cuando diferencia != 0) -- por eso se usa aqui
    numero_conciliacion=0 (columna 'N°' del Excel, estructuralmente podria
    ser 0) como el ejemplo real de un campo mapeado con valor cero. Esto NO
    es una conversion global 0->vacio: depende exclusivamente de si el
    campo esta mapeado en 'posiciones' para ese tipo_linea."""
    m = _movimiento(numero_conciliacion=0)
    lineas = _lineas_para(m)
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    assert banco["numero_docto_conciliacion"] == 0
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    assert "numero_docto_conciliacion" in perfil["posiciones"]["BANCO"]  # sin cambios, Fase 8.7 no lo toca
    fila = es.construir_fila(banco, perfil)
    assert fila[18 - 1] == 0
    assert fila[18 - 1] != ""
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    assert primera_fila.split(",")[18 - 1] == "0"


def test_operativo_62_fechas_no_aplicables_en_banco_no_fallan():
    """Regresion critica de Fase 8.4: BANCO.fecha_emision/vencimiento=0 es
    la convencion de LineaSoftland para 'no aplica a este tipo_linea', NO
    el relleno fisico del perfil -- deben poder coexistir aunque el perfil
    ya no use 0 como relleno. Antes del fix (evaluacion perezosa de _set)
    esto lanzaba FECHA_NO_SERIALIZABLE."""
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(banco, perfil)  # no debe lanzar
    assert fila is not None


# 31-33. OFICIAL_61

def test_oficial_61_conserva_posiciones_pdf():
    perfil = _layouts()["perfiles"]["OFICIAL_61"]
    assert perfil["total_columnas"] == 61
    assert perfil["posiciones_catalogo"]["graba_detalle_libro"] == 37
    assert perfil["posiciones_catalogo"]["documento_nulo"] == 38
    assert perfil["posiciones_catalogo"]["numero_documento_desde"] == 60
    assert perfil["posiciones_catalogo"]["numero_documento_hasta"] == 61
    assert perfil["formato_fecha"] == "DD/MM/AAAA"


# --- Fase 8.8: formato fisico real de OFICIAL_61 (evidencia directa:
# archivo de carga vigente 'SOFTLAND.csv', 42 filas, + estructura oficial
# exportada de la pantalla 'Estructura Arch.' de Softland). Delimitador ';',
# BOM UTF-8, sin campo final vacio (a diferencia de OPERATIVO_62), S/N en
# posiciones 37/38 (no 40/41). ---

def test_oficial_61_delimitador_es_punto_y_coma():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OFICIAL_61", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    assert ";" in primera_fila
    assert "," not in primera_fila.replace("PAGO CLIENTE CLIENTE ABC F1001", "")  # sin comas de dato


def test_oficial_61_61_campos_sin_trailing():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OFICIAL_61", _layouts())
    primera_fila = contenido.split("\r\n")[0]
    campos = primera_fila.split(";")
    assert len(campos) == 61  # sin campo 62 vacio, a diferencia de OPERATIVO_62
    assert campos[-1] != ""  # el ultimo campo real, no un trailing vacio


def test_oficial_61_bom_presente():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OFICIAL_61", _layouts())
    b = contenido.encode("utf-8")
    assert b[:3] == bytes([0xEF, 0xBB, 0xBF])


def test_oficial_61_fila_fisica_37_38_son_n_n():
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OFICIAL_61")
    fila_banco = es.construir_fila(banco, perfil)
    fila_cliente = es.construir_fila(cliente, perfil)
    assert fila_banco[37 - 1] == "N"
    assert fila_banco[38 - 1] == "N"
    assert fila_cliente[37 - 1] == "N"
    assert fila_cliente[38 - 1] == "N"


def test_oficial_61_fila_fisica_40_41_no_son_s_n():
    """Confirma que el S/N NO esta en 40/41 (hipotesis previa OPERATIVO_62,
    contradicha en Fase 8.8) sino en 37/38."""
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    perfil = es._obtener_perfil(_layouts(), "OFICIAL_61")
    fila = es.construir_fila(banco, perfil)
    assert fila[40 - 1] == "0"  # relleno generico numerico (monto_flujo_1), no S/N
    assert fila[41 - 1] == ""  # relleno de texto (codigo_flujo_efectivo_2)


def test_oficial_61_crlf_final_y_sin_lf_suelto():
    lineas = _lineas_multifactura()
    contenido = es.exportar(lineas, "OFICIAL_61", _layouts())
    assert contenido.endswith("\r\n")
    assert "\n" not in contenido.replace("\r\n", "")


def test_oficial_61_sin_comillas():
    lineas = _lineas_multifactura()
    contenido = es.exportar(lineas, "OFICIAL_61", _layouts())
    assert '"' not in contenido


def test_oficial_61_posiciones_17_25_correctas():
    """Fase 8.12/8.13: los 3 atributos-par (Tipo+Nro) quedan completamente
    vacios (BANCO.20/21/24/25, CLIENTE.17/18) -- CONFIRMADO REAL en
    Softland (Fase 8.13): los 3 avisos correspondientes desaparecieron,
    dejando solo el de BANCO.Auxiliar(19). Fase 8.13 vacia tambien esa
    posicion como siguiente hipotesis (unico campo de LineaSoftland aun en
    relleno '0' pendiente de esta serie). El Auxiliar de CLIENTE va con el
    RUT SIN digito verificador (Fase 8.9, confirmado, sin cambios)."""
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OFICIAL_61")
    fila_banco = es.construir_fila(banco, perfil)
    fila_cliente = es.construir_fila(cliente, perfil)
    assert fila_banco[17 - 1] == "TB"
    assert fila_banco[18 - 1] == banco["numero_docto_conciliacion"]
    assert fila_banco[19 - 1] == ""  # Fase 8.13: HIPOTESIS pendiente de confirmar
    assert fila_banco[20 - 1] == ""  # Fase 8.12: par completo vacio (Tipo)
    assert fila_banco[21 - 1] == ""  # Fase 8.12: par completo vacio (Nro)
    assert fila_banco[24 - 1] == ""  # Fase 8.12: par completo vacio (Tipo)
    assert fila_banco[25 - 1] == ""  # Fase 8.12: par completo vacio (Nro)
    assert fila_cliente[17 - 1] == ""  # Fase 8.12: par completo vacio (Tipo)
    assert fila_cliente[18 - 1] == ""  # Fase 8.12: par completo vacio (Nro)
    assert fila_cliente[19 - 1] == "76543210"  # RUT sin DV (Fase 8.9)
    assert fila_cliente[20 - 1] == "TB"
    assert fila_cliente[21 - 1] == 1001
    assert fila_cliente[24 - 1] == "20"
    assert fila_cliente[25 - 1] == 1001


def test_oficial_61_valores_fijos_por_posicion_configurado_correctamente():
    """Fase 8.12/8.13: Fase 8.12 extendio a las mitades 'Nro' de cada par
    (BANCO.21, BANCO.25, CLIENTE.18); Fase 8.13 agrega BANCO.19 (Auxiliar),
    tras confirmarse real que los 3 pares completos resuelven sus avisos y
    solo queda pendiente el de Auxiliar."""
    perfil = _layouts()["perfiles"]["OFICIAL_61"]
    assert perfil["valores_fijos_por_posicion"]["BANCO"] == {"19": "", "20": "", "21": "", "24": "", "25": ""}
    assert perfil["valores_fijos_por_posicion"]["CLIENTE"] == {"17": "", "18": ""}


def test_oficial_61_diferencia_transbank_sin_valores_fijos_por_posicion():
    """DIFERENCIA_TRANSBANK no fue tocado en Fase 8.9: sin evidencia
    especifica sobre esa linea, no se le agrega ningun valor fijo."""
    perfil = _layouts()["perfiles"]["OFICIAL_61"]
    assert "DIFERENCIA_TRANSBANK" not in perfil["valores_fijos_por_posicion"]


def test_operativo_62_sin_valores_fijos_por_posicion():
    """OPERATIVO_62 no fue tocado en Fase 8.9 (esta contradicho y sin uso
    activo): no declara 'valores_fijos_por_posicion'."""
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert "valores_fijos_por_posicion" not in perfil


def test_oficial_61_debe_haber_no_aplicable_queda_relleno_generico():
    """A diferencia de OPERATIVO_62 (relleno vacio), en OFICIAL_61 el lado
    de Debe/Haber que no aplica cae en el relleno generico '0' (string) --
    no vacio, porque asi lo confirma el archivo real de Fase 8.8."""
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OFICIAL_61")
    assert "haber" not in perfil["posiciones"]["BANCO"]
    assert "debe" not in perfil["posiciones"]["CLIENTE"]
    fila_banco = es.construir_fila(banco, perfil)
    fila_cliente = es.construir_fila(cliente, perfil)
    assert fila_banco[3 - 1] == "0"
    assert fila_cliente[2 - 1] == "0"


def test_oficial_61_cuadratura_correcta_es_exportable():
    lineas = _lineas_multifactura()
    contenido = es.exportar(lineas, "OFICIAL_61", _layouts())
    assert contenido


def test_oficial_61_es_default_fase_8_8():
    """Fase 8.8: invierte la premisa de fases anteriores -- ahora es
    OPERATIVO_62 quien NO es el default (sin evidencia real de exito propia,
    5 intentos reales fallidos V1-V5)."""
    layouts = _layouts()
    assert layouts["perfil_default"] == "OFICIAL_61"
    assert layouts["perfil_default"] != "OPERATIVO_62"


def test_campos_1_a_61_no_se_usa_directamente_para_operativo_62():
    """El exportador nunca LEE la clave campos_1_a_61 de una LineaSoftland
    (puede mencionarla en comentarios/docstrings explicando la restriccion);
    construye la fila fisica exclusivamente desde los campos semanticos."""
    import inspect
    codigo_fuente = inspect.getsource(es)
    assert '["campos_1_a_61"]' not in codigo_fuente
    assert '.get("campos_1_a_61"' not in codigo_fuente
    # verificacion funcional directa: un dict sin campos_1_a_61 en absoluto
    # debe exportarse igual de bien que uno que sí la trae
    lineas = _lineas_caso_simple()
    lineas_sin_campos = [
        {k: v for k, v in l.items() if k != "campos_1_a_61"} for l in lineas
    ]
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila_con = es.construir_fila(lineas[0], perfil)
    fila_sin = es.construir_fila(lineas_sin_campos[0], perfil)
    assert fila_con == fila_sin


# 34-37. cuadratura y aborto sin archivo parcial

def test_cuadratura_correcta_es_exportable():
    lineas = _lineas_multifactura()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert contenido  # no lanza


def test_descuadre_aborta():
    lineas = copy.deepcopy(_lineas_caso_simple())
    lineas[0]["debe"] = 999999  # rompe la cuadratura deliberadamente
    try:
        es.exportar(lineas, "OPERATIVO_62", _layouts())
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "DESCUADRE_EXPORTACION"


def test_ningun_archivo_parcial_tras_error(tmp_path):
    lineas = copy.deepcopy(_lineas_caso_simple())
    lineas[0]["debe"] = 999999
    ruta = tmp_path / "salida.csv"
    try:
        contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
        es.escribir_archivo(ruta, contenido)
        assert False, "debia fallar antes de escribir"
    except es.ExportError:
        pass
    assert not ruta.exists()
    assert not (tmp_path / "salida.csv.tmp").exists()


def test_multiples_movimientos_cuadrados_exportacion_valida():
    lineas = _lineas_caso_simple() + _lineas_multifactura()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    filas = [f for f in contenido.split("\r\n") if f]
    # caso simple = 2 lineas (1 Banco + 1 Cliente); multifactura = 3 lineas (1 Banco + 2 Cliente)
    assert len(filas) == 5


# 38-40. casos de negocio

def test_caso_simple_banco_cliente():
    lineas = _lineas_caso_simple()
    assert [l["tipo_linea"] for l in lineas] == ["BANCO", "CLIENTE"]
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert len([f for f in contenido.split("\r\n") if f]) == 2


def test_caso_multifactura():
    lineas = _lineas_multifactura()
    assert [l["tipo_linea"] for l in lineas] == ["BANCO", "CLIENTE", "CLIENTE"]
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert len([f for f in contenido.split("\r\n") if f]) == 3


def test_caso_oro_transbank_export():
    """Fase 8.7: BANCO ya no mapea 'haber' ni CLIENTE 'debe' (nunca aplican
    a ese tipo_linea) -- sus posiciones fisicas quedan vacias, no en '0'.
    La suma fisica debe tratar el campo vacio como 0, exactamente igual que
    hace la cuadratura semantica (que nunca lee la fila fisica)."""
    lineas = _lineas_caso_oro()
    assert [l["tipo_linea"] for l in lineas] == ["BANCO", "CLIENTE", "CLIENTE", "CLIENTE", "DIFERENCIA_TRANSBANK"]
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    filas = [f for f in contenido.split("\r\n") if f]
    assert len(filas) == 5
    total_debe = sum(int(f.split(",")[1] or 0) for f in filas)
    total_haber = sum(int(f.split(",")[2] or 0) for f in filas)
    assert total_debe == total_haber == 245410


# 41-43. UTF-8 / determinismo

def test_caracteres_utf8_ene_i_bytes_correctos():
    nombre = "COMPA" + chr(0xD1) + chr(0xCD) + "A SPA"
    asigs = [_asignacion(nombre_cliente=nombre)]
    m = _movimiento(asignaciones=asigs)
    lineas = _lineas_para(m)
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    b = contenido.encode("utf-8")
    assert bytes([0xC3, 0x91]) in b  # Ñ en UTF-8
    assert bytes([0xC3, 0x8D]) in b  # Í en UTF-8


def test_no_bom():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert not contenido.encode("utf-8").startswith(bytes([0xEF, 0xBB, 0xBF]))


def test_serializacion_deterministica():
    lineas = _lineas_caso_oro()
    c1 = es.exportar(lineas, "OPERATIVO_62", _layouts())
    c2 = es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert c1.encode("utf-8") == c2.encode("utf-8")


# 44-47. no modifica entradas / aislamiento

def test_exportador_no_modifica_linea_softland():
    lineas = _lineas_caso_simple()
    antes = copy.deepcopy(lineas)
    es.exportar(lineas, "OPERATIVO_62", _layouts())
    assert lineas == antes


def test_exportador_no_importa_otros_plugins():
    import inspect
    fuente = inspect.getsource(es)
    for nombre_prohibido in ("contabilidad-conciliacion", "asesoria-informe-tributario", "contabilidad-facturas",
                              "contabilidad-rendiciones", "rrhh-planilla", "asesoria-normativa", "comun-anonimizacion"):
        assert nombre_prohibido not in fuente


def test_exportador_sin_cuentas_contables_hardcodeadas():
    import inspect
    fuente = inspect.getsource(es)
    for cuenta in ("10-01-003", "10-02-001", "10-04-001", "96689310"):
        assert cuenta not in fuente


def test_exportador_sin_reglas_especiales_bci():
    import inspect
    fuente = inspect.getsource(es)
    assert "BCI" not in fuente


# 48-49. forma fisica comparable con captura.csv / 0 permanece 0

def test_forma_fisica_comparable_con_captura_csv():
    """Misma forma estructural que el CSV real auditado en Fase 5.2/5.3:
    62 valores + coma final + CRLF, sin encabezado ni comillas."""
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    primera = contenido.split("\r\n")[0]
    campos = primera.split(",")
    assert len(campos) == 63
    assert campos[-1] == ""
    assert '"' not in contenido


def test_cero_permanece_cero_no_se_convierte_en_vacio():
    """Fase 8.7 (reemplaza la version Fase 8.4): DIFERENCIA_TRANSBANK.auxiliar
    es un valor FIJO real (reglas['auxiliares_fijos']['diferencia_transbank']),
    nunca 0 ni relleno -- sigue mapeado y sigue serializando su valor real
    literal. BANCO.auxiliar=0 (el caso que este test cubria en Fase 8.4) fue
    reclasificado en Fase 8.6/8.7 como sentinela 'no aplica' y ahora se
    prueba explicitamente en test_operativo_62_banco_auxiliar_fisicamente_vacio_no_aplica."""
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
    lineas = _lineas_para(m)
    diferencia = next(l for l in lineas if l["tipo_linea"] == "DIFERENCIA_TRANSBANK")
    assert diferencia["auxiliar"] != 0
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(diferencia, perfil)
    pos = perfil["posiciones"]["DIFERENCIA_TRANSBANK"]["auxiliar"]
    assert fila[pos - 1] == diferencia["auxiliar"]
    assert fila[pos - 1] != ""
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    ultima_fila = [f for f in contenido.split("\r\n") if f][-1]
    assert ultima_fila.split(",")[pos - 1] == diferencia["auxiliar"]


# 50. OFICIAL_61 marcado como no validado (Fase 6.1: dos estados separados,
# ninguno debe leerse como "todo el flujo esta productivamente validado")

def test_oficial_61_formato_y_conciliacion_bancaria_validados_fase_8_16():
    """Fase 8.16: tras la prueba end-to-end real confirmada por Contabilidad
    ('esta bien, procede a lo que sigue'), OFICIAL_61 pasa a tener AMBOS
    flags en true. El alcance de conciliacion_bancaria_validada esta
    escopeado (ver _nota_estados_validacion en rules/softland-layouts.json):
    banco BCI, un cliente, tipo_pago SIMPLE, una factura, diferencia=0 --
    no cubre TRANSBANK, multiples facturas/clientes, otros bancos,
    proveedores ni cargos."""
    perfil = _layouts()["perfiles"]["OFICIAL_61"]
    assert perfil["formato_importador_validado"] is True
    assert perfil["conciliacion_bancaria_validada"] is True


def test_operativo_62_formato_no_validado_fase_8_8():
    """Fase 8.8: OPERATIVO_62 pierde formato_importador_validado=true --
    los 5 intentos reales con este perfil (V1-V5) fallaron todos, y su
    hipotesis de formato quedo contradicha por evidencia mas fuerte."""
    perfil = _layouts()["perfiles"]["OPERATIVO_62"]
    assert perfil["formato_importador_validado"] is False
    assert perfil["conciliacion_bancaria_validada"] is False


# --- Fase 6.1: validacion calendarica real de fechas ---

def _linea_cliente_con_fecha(fecha):
    lineas = _lineas_caso_simple()
    cliente = copy.deepcopy(next(l for l in lineas if l["tipo_linea"] == "CLIENTE"))
    cliente["fecha_emision"] = fecha
    return cliente


def test_fecha_31_02_2026_invalida():
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(_linea_cliente_con_fecha("31/02/2026"), perfil)
        assert False, "31/02 no existe en ningun anio"
    except es.ExportError as e:
        assert e.codigo == "FECHA_NO_SERIALIZABLE"


def test_fecha_31_04_2026_invalida():
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(_linea_cliente_con_fecha("31/04/2026"), perfil)
        assert False, "abril tiene 30 dias"
    except es.ExportError as e:
        assert e.codigo == "FECHA_NO_SERIALIZABLE"


def test_fecha_29_02_2025_invalida_no_bisiesto():
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(_linea_cliente_con_fecha("29/02/2025"), perfil)
        assert False, "2025 no es bisiesto"
    except es.ExportError as e:
        assert e.codigo == "FECHA_NO_SERIALIZABLE"


def test_fecha_29_02_2028_valida_bisiesto():
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(_linea_cliente_con_fecha("29/02/2028"), perfil)  # 2028 es bisiesto
    pos = perfil["posiciones"]["CLIENTE"]["fecha_emision"]
    assert fila[pos - 1] == "29-02-2028"


def test_fecha_28_02_2026_valida():
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(_linea_cliente_con_fecha("28/02/2026"), perfil)
    pos = perfil["posiciones"]["CLIENTE"]["fecha_emision"]
    assert fila[pos - 1] == "28-02-2026"


def test_fecha_31_12_2026_valida():
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(_linea_cliente_con_fecha("31/12/2026"), perfil)
    pos = perfil["posiciones"]["CLIENTE"]["fecha_emision"]
    assert fila[pos - 1] == "31-12-2026"


def test_fecha_anio_0000_invalida():
    """Fase 7 precheck: calendar.monthrange no rechaza anio=0 por si solo
    (no hace validacion de rango de anio); se hizo hardening explicito
    1 <= anio <= 9999 en _convertir_fecha."""
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    try:
        es.construir_fila(_linea_cliente_con_fecha("01/01/0000"), perfil)
        assert False, "anio 0000 no es valido"
    except es.ExportError as e:
        assert e.codigo == "FECHA_NO_SERIALIZABLE"


# --- Fase 7.3: mapeo fisico Cliente 19-25 confirmado por Contabilidad ---

def test_fila_fisica_cliente_posiciones_19_a_25():
    lineas = _lineas_caso_simple()  # asignacion por defecto: rut_cliente=765432101, numero_documento=1001
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(cliente, perfil)
    assert fila[19 - 1] == "76543210"  # RUT sin DV (Fase 8.9)
    assert fila[20 - 1] == "TB"
    assert fila[21 - 1] == 1001
    assert fila[24 - 1] == "20"
    assert fila[25 - 1] == 1001


def test_fila_fisica_cliente_posiciones_19_a_25_con_otro_folio_no_hardcodeado():
    asigs = [_asignacion(rut_cliente="999888777", numero_documento=99999)]
    m = _movimiento(asignaciones=asigs)
    lineas = _lineas_para(m)
    cliente = next(l for l in lineas if l["tipo_linea"] == "CLIENTE")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(cliente, perfil)
    assert fila[19 - 1] == "99988877"  # RUT sin DV (Fase 8.9)
    assert fila[20 - 1] == "TB"
    assert fila[21 - 1] == 99999
    assert fila[24 - 1] == "20"
    assert fila[25 - 1] == 99999


def test_fila_fisica_banco_posiciones_17_18_no_cambian():
    lineas = _lineas_caso_simple()
    banco = next(l for l in lineas if l["tipo_linea"] == "BANCO")
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    fila = es.construir_fila(banco, perfil)
    assert fila[17 - 1] == "TB"
    assert fila[18 - 1] == banco["numero_docto_conciliacion"]


# --- guardia de lineas mal formadas (defensa, no reconstruye aprobacion) ---

def test_linea_mal_formada_falla():
    perfil = es._obtener_perfil(_layouts(), "OPERATIVO_62")
    linea_incompleta = {"movimiento_id": "mov-000003", "tipo_linea": "BANCO"}  # faltan campos
    try:
        es.construir_fila(linea_incompleta, perfil)
        assert False, "debia fallar"
    except es.ExportError as e:
        assert e.codigo == "LINEA_MAL_FORMADA"


# --- golden fixture: comparacion de bytes exactos ---

def test_golden_fixture_operativo_62_bytes_exactos():
    lineas = _lineas_caso_simple()
    contenido = es.exportar(lineas, "OPERATIVO_62", _layouts())
    ruta_esperado = os.path.join(EXPECTED_DIR, "operativo_62_caso_simple.csv")
    with open(ruta_esperado, "rb") as f:
        esperado_bytes = f.read()
    assert contenido.encode("utf-8") == esperado_bytes
