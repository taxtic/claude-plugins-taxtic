import importlib.util, os

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

cat = _cargar("catalogo")


def test_los_tres_perfiles_existen():
    assert set(cat.PERFILES) == {"circular", "resolucion", "oficio"}

def test_obligatorias_de_la_circular():
    assert set(cat.PERFILES["circular"]["obligatorias"]) == {"tema", "gestiones", "a_verificar"}

def test_obligatorias_de_la_resolucion():
    assert set(cat.PERFILES["resolucion"]["obligatorias"]) == {
        "tema", "alcance", "procedimiento", "vigencia", "gestiones", "a_verificar"}

def test_obligatorias_del_oficio():
    assert set(cat.PERFILES["oficio"]["obligatorias"]) == {
        "caso_consultado", "tema", "gestiones", "a_verificar"}

def test_caso_consultado_prohibido_fuera_del_oficio():
    assert "caso_consultado" in cat.PERFILES["circular"]["prohibidas"]
    assert "caso_consultado" in cat.PERFILES["resolucion"]["prohibidas"]

def test_el_oficio_prohibe_deroga_y_procedimiento():
    prohibidas = set(cat.PERFILES["oficio"]["prohibidas"])
    assert {"deroga", "procedimiento", "reglas_comunes"} <= prohibidas

def test_gestiones_y_a_verificar_van_al_final_en_ese_orden():
    for tipo in cat.PERFILES:
        orden = cat.orden_de_emision(tipo)
        assert orden[-2:] == ("gestiones", "a_verificar")

def test_titulo_de_deroga_depende_del_perfil():
    assert cat.titulo_de("deroga", "circular") == "Qué reemplaza esta circular"
    assert cat.titulo_de("deroga", "resolucion") == "Normativa que reemplaza"

def test_titulo_fijo_para_comparacion_y_otra():
    assert cat.titulo_de("comparacion", "circular") == "Cuadro comparativo"
    assert cat.titulo_de("otra", "circular") == "Otras materias"

def test_materia_no_tiene_titulo_de_catalogo():
    assert cat.titulo_de("materia", "circular") is None

def test_bloques_permitidos_por_seccion():
    assert set(cat.bloques_permitidos("plazos")) == {"tabla"}
    assert "callout" in cat.bloques_permitidos("materia")
    assert "callout" not in cat.bloques_permitidos("otra")

def test_catalogo_de_subtitulos_cubre_los_del_documento_de_referencia():
    assert cat.SUBTITULOS["ambito"] == "Ámbito de aplicación"
    assert cat.SUBTITULOS["procedimiento"] == "Procedimiento"
    assert cat.SUBTITULOS["silencio"] == "Resolución y silencio administrativo"
