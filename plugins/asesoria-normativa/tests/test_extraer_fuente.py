import importlib.util, os

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

ef = _cargar("extraer_fuente")


def test_n1_reune_palabra_partida_por_salto_de_linea():
    assert ef.normalizar_lectura("administra-\ntivo") == "administrativo"

def test_n1_colapsa_espacios_y_saltos():
    assert ef.normalizar_lectura("plazo  de\n90   días") == "plazo de 90 días"

def test_n1_unifica_comillas_y_guiones():
    assert ef.normalizar_lectura("“CT” — art") == '"ct" - art'

def test_n1_conserva_acentos():
    assert "días" in ef.normalizar_lectura("DÍAS")

def test_n1_conserva_espacios_para_el_parser_de_cantidades():
    assert ef.normalizar_lectura("cuarenta y cinco días") == "cuarenta y cinco días"

def test_n2_elimina_todo_espacio():
    assert ef.normalizar_matching("noventa días hábiles") == "noventadíashábiles"

def test_n2_absorbe_espacio_insertado_dentro_de_palabra():
    # pypdf produce "R eposición" en el PDF real
    assert ef.normalizar_matching("R eposición") == ef.normalizar_matching("Reposición")

def test_n2_resuelve_la_asimetria_del_guion():
    """Fuente con corte de línea y cita sin él deben converger."""
    fuente = ef.normalizar_matching("jurídico-\ntributario")
    cita = ef.normalizar_matching("jurídico-tributario")
    assert fuente == cita == "jurídicotributario"

def test_n2_es_idempotente_sobre_su_propia_salida():
    una_vez = ef.normalizar_matching("plazo de 90 días")
    assert ef.normalizar_matching(una_vez) == una_vez
