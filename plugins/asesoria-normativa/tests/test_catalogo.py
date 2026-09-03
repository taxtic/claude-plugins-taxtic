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


# --- Integridad del catálogo. Sin estas invariantes, una sección sin clasificar
# --- pasa el gate y el builder la emite después de las secciones de cierre.

def test_cada_perfil_clasifica_todas_las_secciones():
    """Una sección sin clasificar es invisible dos veces: el gate no la rechaza
    y el orden de emisión no la conoce."""
    for tipo, perfil in cat.PERFILES.items():
        clasificadas = (set(perfil["obligatorias"]) | set(perfil["sugeridas"])
                        | set(perfil["prohibidas"]))
        sin_clasificar = set(cat.SECCIONES) - clasificadas
        assert not sin_clasificar, f"{tipo} deja sin clasificar: {sin_clasificar}"

def test_las_tres_listas_de_cada_perfil_son_disjuntas():
    for tipo, perfil in cat.PERFILES.items():
        obligatorias = set(perfil["obligatorias"])
        sugeridas = set(perfil["sugeridas"])
        prohibidas = set(perfil["prohibidas"])
        assert not obligatorias & sugeridas, tipo
        assert not obligatorias & prohibidas, tipo
        assert not sugeridas & prohibidas, tipo

def test_ningun_perfil_nombra_una_seccion_inexistente():
    for tipo, perfil in cat.PERFILES.items():
        for lista in ("obligatorias", "sugeridas", "prohibidas"):
            desconocidas = set(perfil[lista]) - set(cat.SECCIONES)
            assert not desconocidas, f"{tipo}.{lista}: {desconocidas}"

def test_el_orden_base_cubre_el_catalogo_completo():
    """Una sección ausente del orden se emite después del cierre, sin error."""
    assert set(cat.orden_de_emision("circular")) | set(
        cat.PERFILES["circular"]["prohibidas"]) == set(cat.SECCIONES)

def test_el_orden_de_emision_es_exactamente_lo_que_el_perfil_admite():
    for tipo, perfil in cat.PERFILES.items():
        admitidas = set(perfil["obligatorias"]) | set(perfil["sugeridas"])
        assert set(cat.orden_de_emision(tipo)) == admitidas, tipo

def test_el_orden_de_emision_nunca_incluye_una_prohibida():
    for tipo, perfil in cat.PERFILES.items():
        assert not set(cat.orden_de_emision(tipo)) & set(perfil["prohibidas"]), tipo

def test_todas_las_secciones_declaran_bloques_validos():
    bloques_conocidos = {"parrafo", "lista", "tabla", "nota", "callout", "subtitulo"}
    for id_seccion, definicion in cat.SECCIONES.items():
        admitidos = set(definicion["bloques"])
        assert admitidos, id_seccion
        assert admitidos <= bloques_conocidos, f"{id_seccion}: {admitidos}"

def test_solo_materia_tiene_titulo_libre():
    for tipo in cat.PERFILES:
        for id_seccion in cat.SECCIONES:
            titulo = cat.titulo_de(id_seccion, tipo)
            if id_seccion == "materia":
                assert titulo is None
            elif id_seccion in cat.orden_de_emision(tipo):
                assert titulo, f"{id_seccion} en {tipo} sin título de catálogo"

def test_el_caso_consultado_abre_el_documento_del_oficio():
    """Un oficio responde una consulta: el criterio no se entiende sin el caso."""
    orden = cat.orden_de_emision("oficio")
    assert orden[0] == "caso_consultado"
    assert orden.index("caso_consultado") < orden.index("tema")
