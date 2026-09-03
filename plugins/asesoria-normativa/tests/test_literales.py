import importlib.util, os

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

lit = _cargar("literales")


def _hay(encontrados, prefijo):
    """Los centinelas cargan el contenido irresoluble, así que se comparan por
    prefijo: `?dato:dos` es un centinela de dato, distinto de `?dato:tres`."""
    return any(t == prefijo or t.startswith(prefijo + ":") for t in encontrados)


def _solo_centinelas(encontrados, prefijo):
    return bool(encontrados) and all(
        t == prefijo or t.startswith(prefijo + ":") for t in encontrados)


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
    assert lit.parsear_cardinal(["cien", "mil"]) is None

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
    # Los números de artículo se escriben siempre en dígitos en la normativa
    # chilena, así que la forma en palabras no resuelve a una referencia. Pero
    # tampoco pasa en silencio: es un dato en una forma no modelada.
    assert _solo_centinelas(lit.extraer("el artículo ciento veinticuatro"), lit.DATO_IRRESOLUBLE)

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
    assert "fecha:2026-08-31" in lit.extraer("con fecha 31 de agosto de 2026")

def test_extrae_fecha_en_formato_numerico():
    assert "fecha:2026-08-31" in lit.extraer("presentada el 31/08/2026")

def test_la_fecha_no_se_descompone_en_partes_sueltas():
    """El día, el mes y el año por separado respaldarían una fecha que no existe."""
    encontrados = lit.extraer("el 31 de agosto de 2026")
    assert "fecha:2026-08-31" in encontrados
    # el día y el mes no salen sueltos; el año sí, para que una afirmación que
    # solo lo menciona quede respaldada por una cita con la fecha completa
    assert "31" not in encontrados
    assert "agosto" not in encontrados

def test_una_fecha_distinta_produce_un_token_distinto():
    # Compara los tokens concretos: afirmar solo que los conjuntos difieren
    # pasaría igual si las fechas se degradaran a sus años sueltos.
    assert "fecha:2025-01-02" in lit.extraer("2 de enero de 2025")
    assert "fecha:2026-08-31" in lit.extraer("31 de agosto de 2026")
    assert lit.extraer("2 de enero de 2025") != lit.extraer("31 de agosto de 2026")

def test_partes_sueltas_no_respaldan_una_fecha_completa():
    """El caso que motivó el token atómico: 31, agosto y 2026 dispersos."""
    del_texto = lit.extraer("con fecha 31 de agosto de 2026")
    de_la_cita = lit.extraer(
        "en el numeral 31 el mes de agosto del año tributario 2026 se computa aparte")
    assert not del_texto <= de_la_cita

def test_anio_suelto_se_extrae_si_no_es_parte_de_una_fecha():
    assert "2026" in lit.extraer("correspondiente al año tributario 2026")

def test_los_ordinales_en_palabras_son_un_dato():
    """"hasta el décimo día hábil" es tan verificable como "hasta el día 10":
    sin marcarlo, se podía escribir sexagésimo donde el documento dice décimo."""
    assert _hay(lit.extraer("desde el primer día hábil siguiente"),
                lit.DATO_IRRESOLUBLE)
    assert lit.extraer("hasta el décimo día hábil") != lit.extraer(
        "hasta el sexagésimo día hábil")
    # "el 5° día" es una posición en el cómputo, no una cantidad de días
    assert _solo_centinelas(lit.extraer("desde el 5° día hábil siguiente"),
                            lit.MARCA_IRRESOLUBLE + "d")

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
    assert _solo_centinelas(encontrados, "?d")
    # ningún token de cantidad real puede respaldar al centinela
    assert not encontrados <= lit.extraer("dentro de noventa días hábiles")


# --- Formatos de fecha del uso real chileno, y falla cerrada de los que no se
# --- resuelven. Sin el centinela, una fecha no reconocida se degradaba a su
# --- año suelto y cualquier mención de ese año la respaldaba.

def test_fecha_con_puntos_como_separador():
    assert "fecha:2026-08-31" in lit.extraer("Rige desde el 31.08.2026.")

def test_fecha_con_marcador_ordinal():
    assert "fecha:2026-01-01" in lit.extraer("Rige desde el 1° de enero de 2026.")

def test_fecha_con_del_en_vez_de_de():
    assert "fecha:2026-01-01" in lit.extraer("Rige desde el 1 de enero del 2026.")

def test_fecha_en_formato_iso():
    assert "fecha:2026-08-31" in lit.extraer("con fecha 2026-08-31")

def test_mes_mal_escrito_no_se_degrada_a_anio_suelto():
    encontrados = lit.extraer("Con fecha 31 de agost de 2026.")
    assert _solo_centinelas(encontrados, lit.FECHA_IRRESOLUBLE)
    assert "2026" not in encontrados

def test_fecha_inexistente_en_calendario_emite_centinela():
    assert _solo_centinelas(lit.extraer("el 31 de febrero de 2026"), lit.FECHA_IRRESOLUBLE)
    assert _solo_centinelas(lit.extraer("el 13/45/2026"), lit.FECHA_IRRESOLUBLE)

def test_todos_los_centinelas_llevan_la_marca_comun():
    """Quien consume el módulo rechaza por la marca, así que todo centinela que
    salga de extraer() tiene que llevarla, sea de plazo, de fecha o de dato."""
    de_plazo = lit.extraer("transcurridos cinco y noventa dias")
    de_fecha = lit.extraer("con fecha 31 de agost de 2026")
    de_dato = lit.extraer("dentro de 48 horas")
    for encontrados in (de_plazo, de_fecha, de_dato):
        assert encontrados
        assert all(t.startswith(lit.MARCA_IRRESOLUBLE) for t in encontrados)

def test_dos_fechas_en_un_texto_se_atomizan_las_dos():
    encontrados = lit.extraer("entre el 1 de enero de 2025 y el 31 de agosto de 2026")
    assert {"fecha:2025-01-01", "fecha:2026-08-31"} <= encontrados


# --- Vocabulario sin tildes: los PDF y el texto tecleado llegan de las dos
# --- formas, y una palabra no reconocida no emitía ni literal ni centinela.

def test_cantidad_sin_tildes_se_reconoce():
    assert lit.extraer("El plazo es de veintiun dias habiles.") == {"21d"}
    assert lit.extraer("dieciseis meses") == {"16m"}
    assert lit.extraer("veintidos dias") == {"22d"}


# --- Separador de miles: antes daba un valor incorrecto, no None, y además
# --- clasificaba el plazo como monto.

def test_plazo_con_separador_de_miles():
    assert lit.extraer("1.500 dias") == {"1500d"}
    assert lit.extraer("El plazo es de 1.095 dias.") == {"1095d"}

def test_plazo_con_miles_no_se_clasifica_ademas_como_monto():
    assert not any(t.endswith("clp") for t in lit.extraer("1.500 dias"))


# --- Cantidades alternativas: quedarse con la más cercana a la unidad hacía
# --- pasar un plazo que la cita no menciona.

def test_cantidades_separadas_por_conector():
    assert lit.extraer("El plazo es de treinta o sesenta dias.") == {"30d", "60d"}
    assert lit.extraer("El plazo es de 30 o 90 dias.") == {"30d", "90d"}
    assert lit.extraer("de cinco a diez dias") == {"5d", "10d"}

def test_forma_mixta_de_la_normativa():
    assert lit.extraer("noventa (90) dias habiles") == {"90d"}
    assert lit.extraer("90 (noventa) dias habiles") == {"90d"}

def test_forma_mixta_contradictoria_emite_centinela():
    """Si la cifra y la palabra no coinciden, el texto se contradice."""
    assert _solo_centinelas(lit.extraer("noventa (60) dias habiles"),
                            lit.MARCA_IRRESOLUBLE + "d")


# --- Referencias normativas: la enumeración es la forma canónica de citar el
# --- Código Tributario, y `decreto ley` colisionaba con `ley`.

def test_enumeracion_de_articulos():
    assert lit.extraer("Conforme a los articulos 123 y 124 del Codigo.") == {
        "art123", "art124"}
    assert lit.extraer("los arts. 6 y 7 del codigo") == {"art6", "art7"}

def test_articulo_con_sufijo():
    assert lit.extraer("el articulo 123 bis") == {"art123bis"}
    assert lit.extraer("el articulo 4 quater") == {"art4quater"}

def test_decreto_ley_y_dl_producen_el_mismo_token():
    assert lit.extraer("Segun el decreto ley 824.") == {"dl824"}
    assert lit.extraer("Segun el D.L. 824.") == {"dl824"}
    assert lit.extraer("Segun el DL 824.") == {"dl824"}

def test_ley_no_se_confunde_con_decreto_ley():
    assert lit.extraer("la Ley 824") == {"ley824"}

def test_circular_y_resolucion():
    assert lit.extraer("la Circular N° 34 de 2018") == {"circular34", "2018"}
    assert lit.extraer("la Resolucion Exenta SII N° 112") == {"resolucion112"}

def test_norma_con_separador_de_miles_no_emite_monto_fantasma():
    assert lit.extraer("la ley 21.210") == {"ley21210"}


# --- Porcentajes y montos

def test_porcentaje_con_separador_de_miles():
    assert lit.extraer("una tasa de 10.000%") == {"10000pct"}

def test_montos_en_unidades_reajustables():
    """Las multas de las circulares se expresan casi siempre en UTM o UTA."""
    assert lit.extraer("La multa es de 100 UTM.") == {"100utm"}
    assert lit.extraer("una multa de 5 UTA") == {"5uta"}
    assert lit.extraer("el valor de 1,5 UF") == {"1.5uf"}

def test_monto_en_pesos_con_signo():
    assert lit.extraer("un giro de $ 250.000") == {"250000clp"}


# --- Formas que no son español: el parser rechaza lo que no puede resolver

def test_formas_no_gramaticales_emiten_centinela():
    marca = lit.MARCA_IRRESOLUBLE + "d"
    for texto in ("cien uno dias", "ciento dias", "un mil dias"):
        assert _solo_centinelas(lit.extraer(texto), marca), texto


# --- Cifras que ninguna etapa reclama: el centinela residual es lo que impide
# --- que una forma no modelada sea una fuga silenciosa.

def test_forma_no_modelada_cae_en_centinela_residual():
    for texto in ("dentro de 48 horas", "en 3 semanas", "el día 30 del mes",
                  "rige desde el 1 de enero", "vence el 31/08/26",
                  "los 30 primeros días", "el artículo 97 N° 4"):
        encontrados = lit.extraer(texto)
        assert _hay(encontrados, lit.DATO_IRRESOLUBLE), texto

def test_una_fecha_sin_dia_no_se_degrada_a_anio_suelto():
    assert _solo_centinelas(lit.extraer("a contar de agosto de 2026"), lit.FECHA_IRRESOLUBLE)

def test_el_anio_suelto_sigue_saliendo_cuando_no_hay_fecha():
    assert lit.extraer("correspondiente al año tributario 2026") == {"2026"}

def test_texto_sin_cifras_no_produce_centinela_residual():
    assert lit.extraer("el contribuyente puede impugnar el acto") == set()


# --- Etapas que se pisaban entre sí: la corrida temporal mira hacia atrás
# --- saltando lo que no es token, y sin consumir antes leía datos ajenos.

def test_un_porcentaje_no_se_lee_como_plazo():
    assert lit.extraer("un recargo del 10% a 60 días") == {"10pct", "60d"}

def test_un_monto_no_se_lee_como_plazo():
    assert lit.extraer("una multa de $500.000 a 30 días") == {"500000clp", "30d"}

def test_un_numero_de_articulo_no_se_lee_como_plazo():
    assert lit.extraer("amplía el plazo del artículo 59 a 12 meses") == {"art59", "12m"}


# --- Montos

def test_monto_con_signo_no_pierde_digitos():
    """La rama del signo aceptaba cero grupos de miles y se quedaba con los
    tres primeros dígitos: $3000 se leía como 300."""
    assert lit.extraer("$3000") == {"3000clp"}
    assert lit.extraer("$12345") == {"12345clp"}
    assert lit.extraer("$1.500.000") == {"1500000clp"}

def test_decimal_con_punto_no_pierde_la_parte_entera():
    assert lit.extraer("una tasa de 1.5%") == {"1.5pct"}
    assert lit.extraer("el valor de 1.5 UTM") == {"1.5utm"}


# --- Normas

def test_norma_en_plural_y_enumerada():
    assert lit.extraer("las leyes 20.780 y 21.210") == {"ley20780", "ley21210"}
    assert lit.extraer("las circulares 33 y 39") == {"circular33", "circular39"}

def test_decreto_ley_con_espacios_y_puntos():
    """D. L., D.L. y DL son la misma norma."""
    for forma in ("D. L. 824", "D.L. 824", "DL 824", "decreto ley 824"):
        assert lit.extraer("Se aplica el " + forma + ".") == {"dl824"}

def test_tipo_de_norma_desconocido_no_desaparece():
    """Si no se reconoce el tipo, el número cae al residuo como centinela en
    vez de borrarse junto con el tramo."""
    assert _hay(lit.extraer("el acuerdo 1234 del consejo"), lit.DATO_IRRESOLUBLE)


# --- Cantidades

def test_una_cifra_al_lado_no_cura_una_cantidad_irresoluble():
    marca = lit.MARCA_IRRESOLUBLE + "d"
    assert _solo_centinelas(lit.extraer("diez mil (5.000) días"), marca)
    assert _solo_centinelas(lit.extraer("cien uno (90) días"), marca)

def test_una_corrida_demasiado_larga_no_se_trunca_a_un_valor():
    """Cortar la corrida partiría una cantidad compuesta al medio y produciría
    un valor que nadie escribió."""
    largo = "de ciento veinte o 10 o 40 o 30 o ciento cuarenta y cinco días"
    encontrados = lit.extraer(largo)
    assert _hay(encontrados, lit.MARCA_IRRESOLUBLE + "d")
    # ningún valor concreto: truncar la corrida inventaría uno
    assert not any(t[0].isdigit() for t in encontrados)


# --- Cantidades en palabras con unidad no temporal. Sin esto no dejaban ni un
# --- dígito, salía conjunto vacío, y cualquier cita respaldaba la afirmación.

def test_cantidad_en_palabras_con_unidad_no_temporal_falla_cerrada():
    for texto in ("un recargo de treinta por ciento sobre el impuesto",
                  "una multa de mil unidades tributarias mensuales",
                  "tres millones de pesos",
                  "quinientas unidades de fomento"):
        assert _hay(lit.extraer(texto), lit.DATO_IRRESOLUBLE), texto

def test_un_mes_suelto_es_una_fecha_incompleta():
    assert _hay(lit.extraer("el plazo vence el primero de enero"), lit.FECHA_IRRESOLUBLE)
    assert _hay(lit.extraer("durante el mes de agosto"), lit.FECHA_IRRESOLUBLE)

def test_el_articulo_indefinido_y_la_conjuncion_no_disparan_centinela():
    """Están en el vocabulario de números pero sueltos no son cantidades."""
    for texto in ("el contribuyente presenta un recurso",
                  "una circular del Servicio",
                  "la reposición y el recurso jerárquico proceden",
                  "el Servicio debe pronunciarse fundadamente"):
        assert lit.extraer(texto) == set(), texto


# --- Los centinelas cargan contenido: un hecho en forma no modelada tiene que
# --- ser expresable cuando la fuente dice exactamente lo mismo, y rechazado
# --- cuando dice otra cosa. Los tres casos vienen de una corrida real.

def _respalda(cita, texto):
    return lit.extraer(texto) <= lit.extraer(cita)


def test_un_hecho_en_forma_no_modelada_es_expresable_si_la_fuente_lo_dice():
    assert _respalda(
        "la audiencia se celebrará con la asistencia de al menos dos funcionarios",
        "la audiencia exige al menos dos funcionarios")
    assert _respalda(
        "podrán acompañarse antecedentes hasta el día sesenta (60) desde la presentación",
        "los antecedentes se acompañan hasta el día sesenta")
    assert _respalda(
        "deja sin efecto las Circulares N°34 de 27 de junio de 2018, N°26 de 18 de junio de 2026",
        "las Circulares N°34 de 2018 y N°26 de 2026")

def test_el_mismo_hecho_con_otra_cifra_sigue_rechazado():
    assert not _respalda(
        "la audiencia se celebrará con la asistencia de al menos dos funcionarios",
        "la audiencia exige al menos tres funcionarios")
    assert not _respalda(
        "podrán acompañarse antecedentes hasta el día sesenta desde la presentación",
        "los antecedentes se acompañan hasta el día cuarenta")
    assert not _respalda(
        "un recargo de diez por ciento sobre el impuesto adeudado",
        "un recargo de treinta por ciento sobre el impuesto")

def test_el_anio_suelto_queda_respaldado_por_la_fecha_completa():
    """Una afirmación que solo dice "de 2018" la respalda una cita con la fecha
    entera; la dirección peligrosa la sigue cerrando el token atómico."""
    assert _respalda("dictada el 27 de junio de 2018", "la circular de 2018")
    assert not _respalda(
        "en el numeral 27 el mes de junio del año 2018 se computa aparte",
        "dictada el 27 de junio de 2018")



def test_el_ordinal_en_palabras_no_es_una_puerta_trasera():
    """El caso que atravesaba el gate completo: la cita dice décimo y el texto
    dice sexagésimo, sin que ninguno produjera literal."""
    fuente = lit.extraer("hasta el décimo día hábil contado desde la notificación")
    assert not lit.extraer("hasta el sexagésimo día hábil") <= fuente
    assert lit.extraer("hasta el décimo día hábil") <= fuente

def test_una_cantidad_con_articulo_y_unidad_es_un_dato():
    """"una unidad tributaria" es una cantidad tanto como "dos UTM"; tratarlas
    distinto dejaba pasar la primera sin literal alguno."""
    assert _hay(lit.extraer("una multa de una unidad tributaria mensual"),
                lit.DATO_IRRESOLUBLE)
    assert not lit.extraer("una multa de una unidad tributaria mensual") <= lit.extraer(
        "una multa de cien unidades tributarias mensuales")
    # y el artículo suelto sigue sin ensuciar
    assert lit.extraer("el contribuyente presenta un recurso") == set()
