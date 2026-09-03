import copy, importlib.util, os, pytest

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

esq = _cargar("esquema")

FUENTE = {"tipo": "circular", "numero": "35", "anio": 2026,
          "metricas": {"paginas": 17, "caracteres": 1000}}

RESUMEN_VALIDO = {
    "meta": {"elaborado_por": "Asesor Tributario"},
    "secciones": [
        {"id": "tema", "bloques": [
            {"tipo": "parrafo", "afirmacion": "citada",
             "texto": "Sistematiza los mecanismos de impugnación administrativa.",
             "cita": "sistematiza en un solo cuerpo instruccional", "pagina": 1}]},
        {"id": "materia",
         "titulo": {"texto": "RAV (art. 123 bis CT)",
                    "cita": "recurso de reposición administrativa voluntaria", "pagina": 3},
         "bloques": [
             {"tipo": "subtitulo", "rotulo_id": "procedimiento"},
             {"tipo": "parrafo", "afirmacion": "citada", "texto": "Es voluntario.",
              "cita": "el recurso es voluntario para el contribuyente", "pagina": 3}]},
        {"id": "gestiones", "bloques": [
            {"tipo": "lista", "afirmacion": "derivada",
             "items": [{"texto": "Revisar los expedientes en curso."}]}]},
        {"id": "a_verificar", "bloques": [
            {"tipo": "lista", "afirmacion": "derivada",
             "items": [{"texto": "Confirmar publicación en el Diario Oficial."}]}]},
    ],
}


def _con(cambio):
    """Copia el resumen válido y le aplica una mutación."""
    resumen = copy.deepcopy(RESUMEN_VALIDO)
    cambio(resumen)
    return resumen


def test_resumen_valido_pasa():
    esq.validar(RESUMEN_VALIDO, FUENTE)

def test_propiedad_desconocida_rechazada():
    def mutar(r): r["secciones"][0]["bloques"][0]["confianza"] = "alta"
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "confianza" in str(e.value)

def test_id_de_seccion_desconocido_rechazado():
    def mutar(r): r["secciones"][0]["id"] = "resumen_libre"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_seccion_prohibida_por_el_perfil_rechazada():
    def mutar(r): r["secciones"][0]["id"] = "caso_consultado"
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "caso_consultado" in str(e.value)

def test_bloque_no_permitido_en_la_seccion_rechazado():
    def mutar(r): r["secciones"][0]["bloques"][0]["tipo"] = "callout"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_variante_de_callout_invalida_rechazada():
    def mutar(r):
        r["secciones"][1]["bloques"].append(
            {"tipo": "callout", "variante": "urgente", "afirmacion": "citada",
             "texto": "x", "cita": "y", "pagina": 3})
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_rotulo_id_fuera_del_catalogo_rechazado():
    def mutar(r): r["secciones"][1]["bloques"][0]["rotulo_id"] = "consideraciones"
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "consideraciones" in str(e.value)

def test_pagina_fuera_de_rango_rechazada():
    def mutar(r): r["secciones"][0]["bloques"][0]["pagina"] = 99
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_pagina_no_entera_rechazada():
    def mutar(r): r["secciones"][0]["bloques"][0]["pagina"] = "1"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_ruta_del_error_apunta_al_bloque():
    def mutar(r): r["secciones"][1]["bloques"][1]["pagina"] = 99
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert e.value.ruta == "secciones[1].bloques[1]"

def test_titulo_en_seccion_que_no_es_materia_rechazado():
    def mutar(r): r["secciones"][0]["titulo"] = {"texto": "Mi título", "cita": "x", "pagina": 1}
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "titulo" in str(e.value)

def test_titulo_de_materia_sin_cita_rechazado():
    def mutar(r): r["secciones"][1]["titulo"] = {"texto": "RAV"}
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_subtitulo_con_texto_en_vez_de_rotulo_id_rechazado():
    def mutar(r):
        r["secciones"][1]["bloques"][0] = {"tipo": "subtitulo", "texto": "Procedimiento"}
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_meta_con_campo_redactado_rechazado():
    def mutar(r): r["meta"]["descriptor"] = "RAV, RJ y RAF"
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "descriptor" in str(e.value)

def test_afirmacion_normativa_sin_literales_y_sin_cita_rechazada():
    """El caso que el detector de literales NO puede atajar: lo ataja el esquema."""
    def mutar(r):
        r["secciones"][0]["bloques"][0] = {
            "tipo": "parrafo", "afirmacion": "citada",
            "texto": "La interposición del recurso suspende el plazo para reclamar."}
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "cita" in str(e.value)

def test_derivada_fuera_de_gestiones_rechazada():
    def mutar(r): r["secciones"][0]["bloques"][0]["afirmacion"] = "derivada"
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "derivada" in str(e.value)

def test_derivada_con_cita_rechazada():
    def mutar(r):
        r["secciones"][2]["bloques"][0]["items"][0]["cita"] = "algo"
        r["secciones"][2]["bloques"][0]["items"][0]["pagina"] = 1
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_dos_citas_en_un_parrafo_rechazadas():
    def mutar(r):
        bloque = r["secciones"][0]["bloques"][0]
        del bloque["cita"], bloque["pagina"]
        bloque["citas"] = [{"texto": "a" * 45, "pagina": 1}, {"texto": "b" * 45, "pagina": 2}]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "atomicidad" in str(e.value).lower()

def test_cita_y_citas_juntas_rechazadas():
    def mutar(r): r["secciones"][0]["bloques"][0]["citas"] = [{"texto": "x", "pagina": 1}]
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def _con_tabla(filas, encabezado=None):
    resumen = copy.deepcopy(RESUMEN_VALIDO)
    resumen["secciones"][1]["bloques"].append({
        "tipo": "tabla", "afirmacion": "citada",
        "encabezado": encabezado or [{"texto": ""},
                                     {"texto": "RAV", "cita": "a" * 45, "pagina": 3}],
        "filas": filas})
    return resumen


def test_tabla_con_fila_de_largo_distinto_rechazada():
    filas = [[{"texto": "Plazo", "cita": "a" * 45, "pagina": 3}]]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con_tabla(filas), FUENTE)
    assert "largo" in str(e.value).lower()

def test_celda_no_vacia_sin_cita_rechazada():
    filas = [[{"texto": "Plazo"}, {"texto": "30 días", "cita": "a" * 45, "pagina": 3}]]
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con_tabla(filas), FUENTE)

def test_celda_vacia_sin_cita_aceptada():
    filas = [[{"texto": ""}, {"texto": "30 días", "cita": "a" * 45, "pagina": 3}]]
    esq.validar(_con_tabla(filas), FUENTE)

def test_celda_con_rol_estructural_rechazada():
    filas = [[{"texto": "Plazo", "rol": "estructural"},
              {"texto": "30 días", "cita": "a" * 45, "pagina": 3}]]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con_tabla(filas), FUENTE)
    assert "rol" in str(e.value)

def test_mas_de_cuatro_citas_en_una_celda_rechazadas():
    citas = [{"texto": f"{i}" * 45, "pagina": 3} for i in range(5)]
    filas = [[{"texto": ""}, {"texto": "x", "citas": citas}]]
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con_tabla(filas), FUENTE)

def test_suple_seccion_de_una_obligatoria_ausente_aceptada():
    resumen = copy.deepcopy(RESUMEN_VALIDO)
    resumen["secciones"][3]["bloques"][0]["items"][0]["suple_seccion"] = "tema"
    del resumen["secciones"][0]
    esq.validar(resumen, FUENTE)

def test_suple_seccion_de_una_seccion_presente_rechazada():
    def mutar(r):
        r["secciones"][3]["bloques"][0]["items"][0]["suple_seccion"] = "tema"
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "presente" in str(e.value).lower()

def test_suple_seccion_de_una_no_obligatoria_rechazada():
    def mutar(r):
        r["secciones"][3]["bloques"][0]["items"][0]["suple_seccion"] = "plazos"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)


# --- shape: la etapa A tiene que garantizar que el resto del pipeline no
# --- reciba nada malformado. Sin esto, el error aparece recién en el gate o
# --- en el builder, como AttributeError o KeyError.

def test_parrafo_sin_texto_rechazado():
    def mutar(r): del r["secciones"][0]["bloques"][0]["texto"]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "texto" in str(e.value)

def test_item_sin_texto_rechazado():
    def mutar(r): r["secciones"][2]["bloques"][0]["items"][0] = {}
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "texto" in str(e.value)

def test_celda_vacia_como_objeto_vacio_rechazada():
    """El contrato pide {"texto": ""} explícito, no {}."""
    filas = [[{}, {"texto": "30 días", "cita": "a" * 45, "pagina": 3}]]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con_tabla(filas), FUENTE)
    assert "texto" in str(e.value)

def test_texto_no_string_rechazado():
    def mutar(r): r["secciones"][0]["bloques"][0]["texto"] = 123
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "texto" in str(e.value)

def test_cita_no_string_rechazada():
    def mutar(r): r["secciones"][0]["bloques"][0]["cita"] = ["a" * 45]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "cita" in str(e.value)

def test_bloque_que_no_es_objeto_rechazado():
    def mutar(r): r["secciones"][0]["bloques"][0] = "un párrafo"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_callout_sin_texto_rechazado():
    def mutar(r):
        r["secciones"][1]["bloques"].append(
            {"tipo": "callout", "variante": "novedad", "afirmacion": "citada",
             "cita": "a" * 45, "pagina": 3})
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "texto" in str(e.value)

def test_el_esquema_no_mide_el_largo_de_la_cita():
    """El largo mínimo es responsabilidad del gate: son 40 caracteres normalizados."""
    def mutar(r): r["secciones"][0]["bloques"][0]["cita"] = "corta"
    esq.validar(_con(mutar), FUENTE)


# --- nodos superiores: sin estos guardas, un resumen.json malformado revienta
# --- con AttributeError en vez de EsquemaInvalido.

def test_raiz_no_objeto_rechazada():
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar([], FUENTE)

def test_meta_ausente_rechazada():
    def mutar(r): del r["meta"]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "meta" in str(e.value)

def test_meta_no_objeto_rechazada():
    def mutar(r): r["meta"] = "Asesor Tributario"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_elaborado_por_no_string_rechazado():
    def mutar(r): r["meta"]["elaborado_por"] = 42
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "elaborado_por" in str(e.value)

def test_seccion_no_objeto_rechazada():
    def mutar(r): r["secciones"][0] = "tema"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)

def test_seccion_sin_bloques_rechazada():
    def mutar(r): del r["secciones"][0]["bloques"]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "bloques" in str(e.value)


# --- suple_seccion solo vive en a_verificar

def test_suple_seccion_en_gestiones_rechazada():
    """Fuera de a_verificar la suplencia nunca se comprueba: aceptarla engaña."""
    def mutar(r):
        del r["secciones"][0]
        r["secciones"][1]["bloques"][0]["items"][0]["suple_seccion"] = "tema"
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "a_verificar" in str(e.value)

def test_suple_seccion_en_item_citado_rechazada():
    def mutar(r):
        r["secciones"][3]["bloques"][0]["afirmacion"] = "citada"
        item = r["secciones"][3]["bloques"][0]["items"][0]
        item["cita"] = "a" * 45
        item["pagina"] = 1
        item["suple_seccion"] = "tema"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(_con(mutar), FUENTE)


# --- Reglas duras que antes pasaban por coincidencia léxica: estos tests fallan
# --- si la regla se borra del validador, no si otra la ataja por casualidad.

def test_derivada_fuera_de_lugar_sin_cita_rechazada():
    """El caso que importa: afirmación normativa pura, sin literales y sin cita,
    en una sección cualquiera. Es lo que la regla de ubicación hace imposible."""
    def mutar(r):
        r["secciones"][0]["bloques"][0] = {
            "tipo": "parrafo", "afirmacion": "derivada",
            "texto": "La interposición del recurso suspende el plazo para reclamar."}
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "gestiones" in str(e.value)

def test_suple_seccion_en_gestiones_con_a_verificar_presente():
    """Aísla la regla de ubicación: no falta ninguna obligatoria, así que el
    único motivo posible de rechazo es dónde está declarada la suplencia."""
    def mutar(r):
        r["secciones"][2]["bloques"][0]["items"][0]["suple_seccion"] = "tema"
        del r["secciones"][0]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "a_verificar" in e.value.motivo

def test_el_motivo_de_obligatoria_ausente_conserva_su_prefijo():
    """El gate reetiqueta por este prefijo: cambiarlo rompe la clasificación
    sin que ningún otro test se ponga rojo."""
    def mutar(r): del r["secciones"][0]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert e.value.motivo.startswith(esq.MOTIVO_OBLIGATORIA_AUSENTE)

def test_sin_a_verificar_el_mensaje_no_pide_lo_imposible():
    """Pedir que se declare la ausencia de a_verificar dentro de a_verificar
    no tiene solución."""
    def mutar(r): del r["secciones"][3]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "no hay dónde declarar" in e.value.motivo

def test_la_misma_seccion_no_se_suple_dos_veces():
    def mutar(r):
        del r["secciones"][0]
        a_verificar = next(s for s in r["secciones"] if s["id"] == "a_verificar")
        items = a_verificar["bloques"][0]["items"]
        items[0]["suple_seccion"] = "tema"
        items.append({"texto": "También falta el tema.", "suple_seccion": "tema"})
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "ya se declaró suplida" in e.value.motivo

def test_solo_materia_es_repetible():
    def mutar(r): r["secciones"].append(copy.deepcopy(r["secciones"][0]))
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "repetida" in e.value.motivo

def test_materia_si_es_repetible():
    resumen = copy.deepcopy(RESUMEN_VALIDO)
    resumen["secciones"].insert(2, copy.deepcopy(resumen["secciones"][1]))
    esq.validar(resumen, FUENTE)

def test_una_seccion_no_admitida_por_el_perfil_se_rechaza():
    """Falla cerrada: no basta con que no esté prohibida.

    La sección se rechaza durante el recorrido, antes de comprobar las
    obligatorias, así que el motivo es el perfil y no otra ausencia."""
    def mutar(r):
        r["secciones"].insert(0, {"id": "deroga", "bloques": [
            {"tipo": "parrafo", "afirmacion": "citada",
             "texto": "Deja sin efecto la instrucción anterior.",
             "cita": "z" * 45, "pagina": 1}]})
    esq.validar(_con(mutar), FUENTE)  # `deroga` es sugerida en circular
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), {**FUENTE, "tipo": "oficio"})
    assert "deroga" in e.value.motivo

def test_item_derivada_no_lleva_pagina_suelta():
    def mutar(r): r["secciones"][2]["bloques"][0]["items"][0]["pagina"] = 999
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "pagina" in e.value.motivo

def test_elaborado_por_no_es_un_campo_de_texto_libre():
    def mutar(r):
        r["meta"]["elaborado_por"] = "Asesor Tributario. " + "Nota normativa. " * 20
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(_con(mutar), FUENTE)
    assert "elaborado_por" in e.value.motivo


# --- La fuente malformada da EsquemaInvalido con ruta, no un traceback

def test_fuente_malformada_da_error_interpretable():
    for fuente in ({}, {"tipo": "circular"},
                   {"tipo": "circular", "metricas": {}},
                   {"tipo": "circular", "metricas": {"paginas": "17"}},
                   {"tipo": ["circular"], "metricas": {"paginas": 17}}):
        with pytest.raises(esq.EsquemaInvalido):
            esq.validar(RESUMEN_VALIDO, fuente)

def test_un_valor_no_hashable_no_revienta():
    for mutacion in (lambda r: r["secciones"][0].__setitem__("id", ["tema"]),
                     lambda r: r["secciones"][0]["bloques"][0].__setitem__(
                         "tipo", ["parrafo"])):
        with pytest.raises(esq.EsquemaInvalido):
            esq.validar(_con(mutacion), FUENTE)


# --- Los otros dos perfiles, que no tenían ninguna cobertura

FUENTE_OFICIO = {**FUENTE, "tipo": "oficio"}

RESUMEN_OFICIO = {
    "meta": {"elaborado_por": "Asesor Tributario"},
    "secciones": [
        {"id": "caso_consultado", "bloques": [
            {"tipo": "parrafo", "afirmacion": "citada",
             "texto": "Se consulta por el tratamiento del gasto.",
             "cita": "a" * 45, "pagina": 1}]},
        {"id": "tema", "bloques": [
            {"tipo": "parrafo", "afirmacion": "citada", "texto": "Criterio del SII.",
             "cita": "b" * 45, "pagina": 1}]},
        {"id": "gestiones", "bloques": [
            {"tipo": "lista", "afirmacion": "derivada",
             "items": [{"texto": "Revisar los antecedentes."}]}]},
        {"id": "a_verificar", "bloques": [
            {"tipo": "lista", "afirmacion": "derivada",
             "items": [{"texto": "Confirmar la vigencia del criterio."}]}]},
    ],
}


def test_perfil_oficio_valido():
    esq.validar(RESUMEN_OFICIO, FUENTE_OFICIO)

def test_el_oficio_exige_caso_consultado():
    resumen = copy.deepcopy(RESUMEN_OFICIO)
    del resumen["secciones"][0]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(resumen, FUENTE_OFICIO)
    assert "caso_consultado" in e.value.motivo

def test_el_oficio_prohibe_deroga():
    resumen = copy.deepcopy(RESUMEN_OFICIO)
    resumen["secciones"][1]["id"] = "deroga"
    with pytest.raises(esq.EsquemaInvalido):
        esq.validar(resumen, FUENTE_OFICIO)

def test_la_resolucion_exige_procedimiento_y_vigencia():
    resumen = copy.deepcopy(RESUMEN_OFICIO)
    resumen["secciones"][0]["id"] = "tema"
    del resumen["secciones"][1]
    with pytest.raises(esq.EsquemaInvalido) as e:
        esq.validar(resumen, {**FUENTE, "tipo": "resolucion"})
    assert "procedimiento" in e.value.motivo or "alcance" in e.value.motivo
