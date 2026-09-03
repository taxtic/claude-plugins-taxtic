import importlib.util, os

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

lit = _cargar("literales")


def test_cardinal_irregulares():
    assert lit.parsear_cardinal(["cinco"]) == 5
    assert lit.parsear_cardinal(["quince"]) == 15

def test_cardinal_palabra_unica_hasta_29():
    assert lit.parsear_cardinal(["veinte"]) == 20
    assert lit.parsear_cardinal(["veintinueve"]) == 29
    assert lit.parsear_cardinal(["dieciseis"]) == 16

def test_cardinal_decena_con_y():
    assert lit.parsear_cardinal(["cuarenta", "y", "cinco"]) == 45
    assert lit.parsear_cardinal(["noventa"]) == 90

def test_cardinal_centenas():
    assert lit.parsear_cardinal(["cien"]) == 100
    assert lit.parsear_cardinal(["ciento", "veinte"]) == 120
    assert lit.parsear_cardinal(["doscientos", "treinta", "y", "uno"]) == 231

def test_cardinal_miles():
    assert lit.parsear_cardinal(["mil"]) == 1000
    assert lit.parsear_cardinal(["dos", "mil"]) == 2000
    assert lit.parsear_cardinal(["mil", "ochocientos"]) == 1800

def test_cardinal_irresoluble_devuelve_none():
    assert lit.parsear_cardinal(["hábiles"]) is None
    assert lit.parsear_cardinal([]) is None

def test_fuera_del_rango_declarado_devuelve_none():
    """El parser promete 0-9999; diez mil queda afuera y no se resuelve a medias."""
    assert lit.parsear_cardinal(["diez", "mil"]) is None
    assert lit.parsear_cardinal(["nueve", "mil", "novecientos", "noventa", "y", "nueve"]) == 9999

def test_extrae_plazo_en_cifras():
    assert "90d" in lit.extraer("el plazo es de 90 días hábiles administrativos")

def test_extrae_plazo_en_palabras():
    assert "90d" in lit.extraer("dentro del plazo de noventa días hábiles")

def test_extrae_forma_mixta():
    assert lit.extraer("noventa (90) días hábiles") == {"90d"}

def test_extrae_cantidad_compuesta():
    assert "45d" in lit.extraer("un plazo de cuarenta y cinco días")

def test_un_anio_es_cantidad_pero_un_recurso_no():
    assert "1a" in lit.extraer("suspende por un año el cómputo")
    assert lit.extraer("el contribuyente presenta un recurso") == set()

def test_extrae_referencia_normativa():
    assert "art123bis" in lit.extraer("conforme al artículo 123 bis del código tributario")
    assert "art124" in lit.extraer("los actos del art. 124")

def test_referencia_normativa_no_usa_palabras():
    # los números de artículo se escriben siempre en dígitos en la normativa chilena
    assert lit.extraer("el artículo ciento veinticuatro") == set()

def test_extrae_porcentaje_y_monto():
    assert "27pct" in lit.extraer("tasa de 27%")
    assert "1500000clp" in lit.extraer("una multa de 1.500.000")

def test_canonicalizacion_de_porcentajes():
    """Los ceros finales se recortan del decimal, nunca del entero."""
    assert lit.extraer("tasa de 10%") == {"10pct"}
    assert lit.extraer("tasa de 100%") == {"100pct"}
    assert lit.extraer("tasa de 10,0%") == {"10pct"}
    assert lit.extraer("tasa de 10,50%") == {"10.5pct"}

def test_extrae_la_fecha_como_una_unidad():
    assert lit.extraer("con fecha 31 de agosto de 2026") == {"fecha:2026-08-31"}

def test_extrae_fecha_en_formato_numerico():
    assert lit.extraer("presentada el 31/08/2026") == {"fecha:2026-08-31"}

def test_la_fecha_no_se_descompone_en_partes_sueltas():
    """El día, el mes y el año por separado respaldarían una fecha que no existe."""
    encontrados = lit.extraer("el 31 de agosto de 2026")
    assert "31" not in encontrados
    assert "agosto" not in encontrados
    assert "2026" not in encontrados

def test_una_fecha_distinta_produce_un_token_distinto():
    assert lit.extraer("2 de enero de 2025") != lit.extraer("31 de agosto de 2026")

def test_partes_sueltas_no_respaldan_una_fecha_completa():
    """El caso que motivó el token atómico: 31, agosto y 2026 dispersos."""
    del_texto = lit.extraer("con fecha 31 de agosto de 2026")
    de_la_cita = lit.extraer(
        "en el numeral 31 el mes de agosto del año tributario 2026 se computa aparte")
    assert not del_texto <= de_la_cita

def test_anio_suelto_se_extrae_si_no_es_parte_de_una_fecha():
    assert "2026" in lit.extraer("correspondiente al año tributario 2026")

def test_ordinales_fuera_del_parser():
    assert lit.extraer("desde el primer día hábil siguiente") == set()

def test_cantidad_irresoluble_no_produce_literal_silencioso():
    # "muchos días" no es una cantidad: no debe inventar un token
    assert lit.extraer("transcurridos muchos días") == set()

def test_bypass_de_cantidades_en_palabras_queda_cerrado():
    """Sin un solo dígito de por medio, treinta y sesenta deben diferir."""
    del_texto = lit.extraer("El plazo es de treinta días hábiles.")
    de_la_cita = lit.extraer("dentro del plazo de sesenta días hábiles")
    assert del_texto == {"30d"}
    assert de_la_cita == {"60d"}
    assert not del_texto <= de_la_cita

def test_extremo_superior_del_rango():
    assert lit.parsear_cardinal(
        ["nueve", "mil", "novecientos", "noventa", "y", "nueve"]) == 9999
    assert "9999d" in lit.extraer("un plazo de nueve mil novecientos noventa y nueve días")

def test_cantidad_irresoluble_falla_cerrado():
    """Palabras de cantidad que no forman un número no pueden pasar en silencio."""
    encontrados = lit.extraer("transcurridos cinco y noventa días")
    assert encontrados == {"?d"}
    # ningún token de cantidad real puede respaldar al centinela
    assert not encontrados <= lit.extraer("dentro de noventa días hábiles")
