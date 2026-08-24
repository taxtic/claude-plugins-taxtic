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


vc = _load("verificar_consistencia")

MOV_ID = "mov-000001"


def _campos_1_a_61(valores=None):
    campos = {str(n): 0 for n in range(1, 62)}
    campos.update(valores or {})
    return campos


def _linea_banco():
    return {
        "movimiento_id": MOV_ID, "tipo_linea": "BANCO", "orden": 1,
        "cuenta": "10-01-003", "debe": 61267, "haber": 0,
        "glosa": "PAGO CLIENTE  F34174", "auxiliar": 0, "tipo_documento": 0,
        "numero_documento": 0, "fecha_emision": 0, "fecha_vencimiento": 0,
        "tipo_docto_conciliacion": "TB", "numero_docto_conciliacion": 186,
        "numero_docto_referencia": 0,
        "campos_1_a_61": _campos_1_a_61({"1": "10-01-003", "2": 61267, "4": "PAGO CLIENTE  F34174", "17": "TB", "18": 186}),
        "filas_excel_origen": [1],
    }


def _linea_cliente():
    return {
        "movimiento_id": MOV_ID, "tipo_linea": "CLIENTE", "orden": 2,
        "cuenta": "10-02-001", "debe": 0, "haber": 61267,
        "glosa": "PAGO F 34174", "auxiliar": "76543210", "tipo_documento": "20",
        "numero_documento": 34174, "fecha_emision": "12/08/2026", "fecha_vencimiento": "12/08/2026",
        "tipo_docto_conciliacion": "TB", "numero_docto_conciliacion": 0,
        "numero_docto_referencia": 34174,
        "campos_1_a_61": _campos_1_a_61({"1": "10-02-001", "3": 61267, "4": "PAGO F 34174", "19": "76543210", "20": "TB", "21": 34174}),
        "filas_excel_origen": [1],
    }


def _lineas():
    return [_linea_banco(), _linea_cliente()]


def _escribir(tmp_path, nombre, contenido):
    ruta = tmp_path / nombre
    ruta.write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    return str(ruta)


def _preview_path(tmp_path, previstos):
    return _escribir(tmp_path, "preview.json", {"previstos": previstos, "excluidos": []})


def _transform_path(tmp_path, transformados):
    return _escribir(tmp_path, "transform.json", {"transformados": transformados, "excluidos": []})


# 1. par identico

def test_par_identico_no_lanza(tmp_path):
    lineas = _lineas()
    preview = _preview_path(tmp_path, {MOV_ID: copy.deepcopy(lineas)})
    transform = _transform_path(tmp_path, {MOV_ID: copy.deepcopy(lineas)})
    vc.verificar(preview, transform, MOV_ID)  # no debe lanzar


def test_cli_par_identico_exit_0(tmp_path, capsys):
    lineas = _lineas()
    preview = _preview_path(tmp_path, {MOV_ID: copy.deepcopy(lineas)})
    transform = _transform_path(tmp_path, {MOV_ID: copy.deepcopy(lineas)})
    codigo = vc.main([preview, transform, MOV_ID])
    assert codigo == 0


# 2. movimiento ausente en preview

def test_movimiento_ausente_en_preview(tmp_path):
    preview = _preview_path(tmp_path, {"mov-000002": _lineas()})
    transform = _transform_path(tmp_path, {MOV_ID: _lineas()})
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "MOVIMIENTO_NO_ENCONTRADO_EN_PREVIEW"


# 3. movimiento ausente en transform

def test_movimiento_ausente_en_transform(tmp_path):
    preview = _preview_path(tmp_path, {MOV_ID: _lineas()})
    transform = _transform_path(tmp_path, {"mov-000002": _lineas()})
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "MOVIMIENTO_NO_ENCONTRADO_EN_TRANSFORM"


# 4. cero lineas preview

def test_cero_lineas_preview(tmp_path):
    preview = _preview_path(tmp_path, {MOV_ID: []})
    transform = _transform_path(tmp_path, {MOV_ID: _lineas()})
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "SIN_LINEAS_PREVIEW"


# 5. cero lineas transform

def test_cero_lineas_transform(tmp_path):
    preview = _preview_path(tmp_path, {MOV_ID: _lineas()})
    transform = _transform_path(tmp_path, {MOV_ID: []})
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "SIN_LINEAS_TRANSFORM"


# 6. diferencia en un campo normal (semantico, no anidado)

def test_diferencia_en_campo_normal(tmp_path):
    lineas_preview = _lineas()
    lineas_transform = copy.deepcopy(lineas_preview)
    lineas_transform[1]["glosa"] = "PAGO F 99999"  # difiere del preview, en la linea CLIENTE (indice 1)
    preview = _preview_path(tmp_path, {MOV_ID: lineas_preview})
    transform = _transform_path(tmp_path, {MOV_ID: lineas_transform})
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "LINEAS_DIFERENTES"
        assert f"movimiento_id={MOV_ID!r}" in str(e)
        assert "linea=2" in str(e)  # 1-based: indice 1 -> linea 2, claro para un humano
        assert "glosa" in str(e)
        assert "PAGO F 34174" in str(e)
        assert "PAGO F 99999" in str(e)


# 7. diferencia dentro de campos_1_a_61 (campo anidado, sin whitelist)

def test_diferencia_en_campos_1_a_61(tmp_path):
    lineas_preview = _lineas()
    lineas_transform = copy.deepcopy(lineas_preview)
    lineas_transform[0]["campos_1_a_61"]["37"] = "S"  # difiere solo en la posicion anidada 37, linea BANCO (indice 0)
    preview = _preview_path(tmp_path, {MOV_ID: lineas_preview})
    transform = _transform_path(tmp_path, {MOV_ID: lineas_transform})
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "LINEAS_DIFERENTES"
        assert "linea=1" in str(e)  # 1-based: indice 0 -> linea 1
        assert "campos_1_a_61.37" in str(e)
        assert "'S'" in str(e)


# 8. distinta cantidad de lineas -- debe identificar la PRIMERA linea ausente
# en un lado, con un sentinela explicito, no un mensaje generico de cantidades

def test_distinta_cantidad_de_lineas(tmp_path):
    preview = _preview_path(tmp_path, {MOV_ID: _lineas()})  # 2 lineas: BANCO, CLIENTE
    transform = _transform_path(tmp_path, {MOV_ID: [_linea_banco()]})  # solo 1 linea: BANCO
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "LINEAS_DIFERENTES"
        # la linea CLIENTE (indice 1) existe en preview y no en transform ->
        # linea humana = 2, sentinela explicito del lado ausente
        assert "linea=2" in str(e)
        assert "<linea_completa>" in str(e)
        assert "<ausente>" in str(e)


def test_distinta_cantidad_de_lineas_identifica_la_primera_linea_ausente(tmp_path):
    """Si el lado mas corto es el preview (no el transform), el sentinela
    '<ausente>' debe aparecer del lado correcto (valor_preview), no del otro."""
    preview = _preview_path(tmp_path, {MOV_ID: [_linea_banco()]})  # solo 1 linea
    transform = _transform_path(tmp_path, {MOV_ID: _lineas()})  # 2 lineas
    try:
        vc.verificar(preview, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "LINEAS_DIFERENTES"
        assert "linea=2" in str(e)
        assert "preview=" in str(e) and "'<ausente>'" in str(e)


# 9. archivos invertidos (preview/transform intercambiados)

def test_archivos_invertidos_preview_invalido(tmp_path):
    transform = _transform_path(tmp_path, {MOV_ID: _lineas()})
    try:
        # se pasa el archivo de transform como si fuera el de preview
        vc.verificar(transform, transform, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "PREVIEW_INVALIDO"


def test_archivos_invertidos_transform_invalido(tmp_path):
    preview = _preview_path(tmp_path, {MOV_ID: _lineas()})
    try:
        # se pasa el archivo de preview como si fuera el de transform
        vc.verificar(preview, preview, MOV_ID)
        assert False, "debia fallar"
    except vc.ConsistenciaError as e:
        assert e.codigo == "TRANSFORM_INVALIDO"


# 10. exit codes CLI

def test_cli_exit_1_en_fallo(tmp_path, capsys):
    preview = _preview_path(tmp_path, {MOV_ID: []})
    transform = _transform_path(tmp_path, {MOV_ID: _lineas()})
    codigo = vc.main([preview, transform, MOV_ID])
    assert codigo == 1
    salida = capsys.readouterr()
    assert "SIN_LINEAS_PREVIEW" in salida.err


# 11. el verificador nunca crea archivos (exito ni fallo)

def test_no_crea_ningun_archivo_en_exito(tmp_path):
    lineas = _lineas()
    preview = _preview_path(tmp_path, {MOV_ID: copy.deepcopy(lineas)})
    transform = _transform_path(tmp_path, {MOV_ID: copy.deepcopy(lineas)})
    antes = set(os.listdir(tmp_path))
    vc.main([preview, transform, MOV_ID])
    despues = set(os.listdir(tmp_path))
    assert antes == despues


def test_no_crea_ningun_archivo_en_fallo(tmp_path):
    preview = _preview_path(tmp_path, {MOV_ID: []})
    transform = _transform_path(tmp_path, {MOV_ID: _lineas()})
    antes = set(os.listdir(tmp_path))
    vc.main([preview, transform, MOV_ID])
    despues = set(os.listdir(tmp_path))
    assert antes == despues


def test_no_tiene_flag_out():
    """Contrato explicito: no --out, no genera archivos -- verificado
    estaticamente contra el parser real."""
    import inspect
    fuente = inspect.getsource(vc.main)
    assert "--out" not in fuente
