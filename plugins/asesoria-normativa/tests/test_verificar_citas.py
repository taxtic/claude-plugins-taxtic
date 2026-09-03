import copy, importlib.util, os, pytest

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

vc = _cargar("verificar_citas")
ef = _cargar("extraer_fuente")

TEXTO_PAGINA_1 = ("El Servicio deberá pronunciarse dentro del plazo de noventa (90) días "
                  "hábiles administrativos contados desde la presentación del recurso de "
                  "reposición administrativa voluntaria del artículo 123 bis.")
TEXTO_PAGINA_2 = ("El recurso jerárquico deberá interponerse dentro del plazo de cinco días "
                  "hábiles administrativos contados desde la notificación de la resolución.")

FUENTE = {
    "tipo": "circular", "numero": "35", "anio": 2026,
    "metricas": {"paginas": 2, "caracteres": 400},
    "paginas": [{"n": 1, "texto": TEXTO_PAGINA_1}, {"n": 2, "texto": TEXTO_PAGINA_2}],
    "texto_normalizado": ef.normalizar_matching(TEXTO_PAGINA_1 + " " + TEXTO_PAGINA_2),
    "paginas_normalizadas": [
        {"n": 1, "texto": ef.normalizar_matching(TEXTO_PAGINA_1)},
        {"n": 2, "texto": ef.normalizar_matching(TEXTO_PAGINA_2)},
    ],
    "procedencia_campos": {"tipo": "detectado", "numero": "detectado",
                           "fecha_documento": "detectado", "anio": "derivado"},
}

RESUMEN = {
    "meta": {"elaborado_por": "Asesor Tributario"},
    "secciones": [
        {"id": "tema", "bloques": [
            {"tipo": "parrafo", "afirmacion": "citada",
             "texto": "El SII debe pronunciarse dentro de 90 días hábiles administrativos.",
             "cita": "deberá pronunciarse dentro del plazo de noventa (90) días hábiles administrativos",
             "pagina": 1}]},
        {"id": "gestiones", "bloques": [
            {"tipo": "lista", "afirmacion": "derivada",
             "items": [{"texto": "Revisar los expedientes en curso del estudio."}]}]},
        {"id": "a_verificar", "bloques": [
            {"tipo": "lista", "afirmacion": "derivada",
             "items": [{"texto": "Confirmar la publicación en el Diario Oficial."}]}]},
    ],
}


def _con(cambio):
    resumen = copy.deepcopy(RESUMEN)
    cambio(resumen)
    return resumen


def test_resumen_valido_pasa_y_devuelve_el_respaldo():
    filas = vc.verificar(RESUMEN, FUENTE)
    assert any(f["pagina"] == 1 for f in filas)

def test_cita_inexistente():
    def mutar(r):
        r["secciones"][0]["bloques"][0]["cita"] = (
            "un texto que no aparece en ninguna parte del documento fuente citado")
    with pytest.raises(vc.CitaInexistente):
        vc.verificar(_con(mutar), FUENTE)

def test_cita_existente_pero_en_otra_pagina():
    def mutar(r):
        bloque = r["secciones"][0]["bloques"][0]
        bloque["cita"] = "deberá interponerse dentro del plazo de cinco días hábiles"
        bloque["texto"] = "El recurso se interpone dentro de 5 días hábiles."
        bloque["pagina"] = 1  # el texto está en la página 2
    with pytest.raises(vc.PaginaInvalida):
        vc.verificar(_con(mutar), FUENTE)

def test_cita_bajo_el_largo_minimo():
    def mutar(r):
        r["secciones"][0]["bloques"][0]["cita"] = "noventa días"
        r["secciones"][0]["bloques"][0]["texto"] = "Plazo de 90 días."
    with pytest.raises(vc.CitaAusente):
        vc.verificar(_con(mutar), FUENTE)

def test_literal_sin_respaldo_cifras_contra_cifras():
    def mutar(r):
        r["secciones"][0]["bloques"][0]["texto"] = (
            "El SII debe pronunciarse dentro de 30 días hábiles administrativos.")
    with pytest.raises(vc.LiteralSinRespaldo) as e:
        vc.verificar(_con(mutar), FUENTE)
    assert "30d" in str(e.value)

def test_parafrasis_en_cifras_contra_cita_en_palabras_pasa():
    """El texto dice 5 días; la fuente dice cinco días. Debe pasar."""
    def mutar(r):
        r["secciones"][0]["bloques"][0] = {
            "tipo": "parrafo", "afirmacion": "citada",
            "texto": "El recurso jerárquico se interpone dentro de 5 días hábiles.",
            "cita": "deberá interponerse dentro del plazo de cinco días hábiles administrativos",
            "pagina": 2}
    assert vc.verificar(_con(mutar), FUENTE)

def test_literal_en_palabras_contra_palabras_distintas_falla():
    """Sin un solo dígito de por medio: treinta contra cinco."""
    def mutar(r):
        r["secciones"][0]["bloques"][0] = {
            "tipo": "parrafo", "afirmacion": "citada",
            "texto": "El recurso se interpone dentro de treinta días hábiles.",
            "cita": "deberá interponerse dentro del plazo de cinco días hábiles administrativos",
            "pagina": 2}
    with pytest.raises(vc.LiteralSinRespaldo):
        vc.verificar(_con(mutar), FUENTE)

def test_fecha_respaldada_por_la_misma_fecha_pasa():
    fuente = copy.deepcopy(FUENTE)
    texto = ("La circular fue emitida con fecha 31 de agosto de 2026 según consta "
             "en el sistema de publicaciones administrativas del Servicio.")
    fuente["paginas"] = [{"n": 1, "texto": texto}]
    fuente["paginas_normalizadas"] = [{"n": 1, "texto": ef.normalizar_matching(texto)}]
    fuente["texto_normalizado"] = ef.normalizar_matching(texto)
    fuente["metricas"]["paginas"] = 1
    def mutar(r):
        r["secciones"][0]["bloques"][0] = {
            "tipo": "parrafo", "afirmacion": "citada",
            "texto": "La circular es del 31 de agosto de 2026.",
            "cita": "emitida con fecha 31 de agosto de 2026 según consta en el sistema",
            "pagina": 1}
    assert vc.verificar(_con(mutar), fuente)

def test_partes_de_fecha_dispersas_no_respaldan_la_fecha():
    """La fecha es un literal atómico: 31, agosto y 2026 sueltos no alcanzan."""
    fuente = copy.deepcopy(FUENTE)
    texto = ("En el numeral 31 se trata el mes de agosto y el año tributario 2026 "
             "queda regulado en un apartado distinto de esta circular.")
    fuente["paginas"] = [{"n": 1, "texto": texto}]
    fuente["paginas_normalizadas"] = [{"n": 1, "texto": ef.normalizar_matching(texto)}]
    fuente["texto_normalizado"] = ef.normalizar_matching(texto)
    fuente["metricas"]["paginas"] = 1
    def mutar(r):
        r["secciones"][0]["bloques"][0] = {
            "tipo": "parrafo", "afirmacion": "citada",
            "texto": "La circular es del 31 de agosto de 2026.",
            "cita": "el numeral 31 se trata el mes de agosto y el año tributario 2026",
            "pagina": 1}
    with pytest.raises(vc.LiteralSinRespaldo) as e:
        vc.verificar(_con(mutar), fuente)
    assert "fecha:2026-08-31" in str(e.value)

def test_referencia_normativa_sin_respaldo_falla():
    def mutar(r):
        r["secciones"][0]["bloques"][0]["texto"] = (
            "El plazo de 90 días hábiles se cuenta según el artículo 200.")
    with pytest.raises(vc.LiteralSinRespaldo) as e:
        vc.verificar(_con(mutar), FUENTE)
    assert "art200" in str(e.value)

def test_cantidad_irresoluble_se_rechaza_aunque_la_cita_sea_igual_de_ambigua():
    """El centinela no se respalda a sí mismo: dos '?d' no se cancelan."""
    fuente = copy.deepcopy(FUENTE)
    texto = ("transcurridos cinco y noventa días hábiles administrativos contados "
             "desde la notificación del acto que se impugna en esta sede")
    fuente["paginas"] = [{"n": 1, "texto": texto}]
    fuente["paginas_normalizadas"] = [{"n": 1, "texto": ef.normalizar_matching(texto)}]
    fuente["texto_normalizado"] = ef.normalizar_matching(texto)
    fuente["metricas"]["paginas"] = 1
    def mutar(r):
        r["secciones"][0]["bloques"][0] = {
            "tipo": "parrafo", "afirmacion": "citada",
            "texto": "El plazo es de cinco y noventa días hábiles.",
            "cita": "transcurridos cinco y noventa días hábiles administrativos contados",
            "pagina": 1}
    with pytest.raises(vc.LiteralSinRespaldo) as e:
        vc.verificar(_con(mutar), fuente)
    assert "?d" in str(e.value)

def test_derivada_con_dato_factual():
    def mutar(r):
        r["secciones"][1]["bloques"][0]["items"][0]["texto"] = (
            "Revisar los expedientes antes de que venzan los 30 días.")
    with pytest.raises(vc.DerivadaConDato) as e:
        vc.verificar(_con(mutar), FUENTE)
    assert "30d" in str(e.value)

def test_suplencia_faltante():
    def mutar(r):
        del r["secciones"][0]  # borra `tema`, que es obligatoria, sin suplirla
    with pytest.raises(vc.SuplenciaFaltante):
        vc.verificar(_con(mutar), FUENTE)

def test_suplencia_declarada_pasa():
    def mutar(r):
        del r["secciones"][0]
        r["secciones"][1]["bloques"][0]["items"][0]["suple_seccion"] = "tema"
    assert vc.verificar(_con(mutar), FUENTE) is not None


def test_respaldo_incluye_procedencia_de_los_campos(tmp_path):
    fuente = copy.deepcopy(FUENTE)
    fuente["procedencia_campos"]["numero"] = "usuario"
    filas = vc.verificar(RESUMEN, fuente)
    salida = tmp_path / "respaldo-citas.md"
    vc.escribir_respaldo(filas, fuente, str(salida))
    contenido = salida.read_text(encoding="utf-8")
    assert "numero" in contenido and "usuario" in contenido
    assert "no se entrega al cliente" in contenido
