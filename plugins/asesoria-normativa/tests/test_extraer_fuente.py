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
    # la extracción de PDF inserta espacios dentro de las palabras
    assert ef.normalizar_matching("R eposición") == "reposición"
    assert ef.normalizar_matching("Reposición") == "reposición"

def test_n2_elimina_todo_guion():
    """Fuente con corte de línea y cita sin él deben converger."""
    fuente = ef.normalizar_matching("jurídico-\ntributario")
    cita = ef.normalizar_matching("jurídico-tributario")
    assert fuente == cita == "jurídicotributario"

def test_n1_une_el_corte_antes_de_unificar_los_guiones():
    """Fija el orden de los pasos: si los guiones se unifican primero, el corte
    tipográfico deja de reconocerse y la palabra queda partida."""
    assert ef.normalizar_lectura("administra‐\ntivo") == "administrativo"
    assert ef.normalizar_lectura("administra­\ntivo") == "administrativo"

def test_n1_no_empalma_a_traves_de_una_raya():
    """La raya es puntuación, no corte de palabra: unir pegaría dos palabras y
    haría desaparecer la segunda para el detector de datos."""
    assert "noventa" in ef.normalizar_lectura("fijado por ley—\nnoventa días")

def test_n1_no_empalma_a_traves_de_un_quiebre_de_parrafo():
    assert "cuarenta" in ef.normalizar_lectura("certificada-\n\ncuarenta y cinco")

def test_n1_unifica_formas_unicode_equivalentes():
    """El mismo carácter acentuado llega precompuesto o descompuesto según el
    PDF; sin unificarlo ninguna cita con tilde de ese documento haría match."""
    import unicodedata
    descompuesta = unicodedata.normalize("NFD", "días hábiles administrativos")
    assert ef.normalizar_matching(descompuesta) == ef.normalizar_matching(
        "días hábiles administrativos")

def test_n2_elimina_las_comillas():
    """Mismo criterio que con los guiones: no se adivina cuál es de maquetado."""
    assert (ef.normalizar_matching("la «Reposición» suspende")
            == ef.normalizar_matching('la "Reposición" suspende'))
    assert (ef.normalizar_matching("el 'plazo fatal'")
            == ef.normalizar_matching('el "plazo fatal"'))

def test_n1_unifica_el_ordinal_masculino_con_el_signo_de_grado():
    """Circular Nº 35 y Circular N° 35 son el mismo documento."""
    assert (ef.normalizar_matching("la Circular Nº 35 de 2026")
            == ef.normalizar_matching("la Circular N° 35 de 2026"))

def test_n2_es_idempotente_sobre_su_propia_salida():
    una_vez = ef.normalizar_matching("plazo de 90 días")
    assert ef.normalizar_matching(una_vez) == una_vez

import pytest

# Bloque identificatorio con la forma del PDF real. En la Circular 35 este
# recuadro sale AL FINAL del texto de la página 1, después del cuerpo.
PAGINA_1 = """I. INTRODUCCIÓN
El Servicio de Impuestos Internos ha centrado sus esfuerzos en mejorar la relación
con los contribuyentes.
DEPARTAMENTO EMISOR:
Subdirección Jurídica
CIRCULAR N°35.-
SISTEMA DE PUBLICACIONES ADMINISTRATIVAS
FECHA: 31 DE AGOSTO DE 2026
MATERIA: Actualiza instrucciones sobre mecanismos de impugnación administrativa.
"""


def test_detecta_identidad_aunque_el_bloque_este_al_final():
    identidad = ef.detectar_identidad(PAGINA_1)
    assert identidad["tipo"] == "circular"
    assert identidad["numero"] == "35"
    assert identidad["fecha_documento"] == "31 de agosto de 2026"
    assert ef.derivar_anio(identidad["fecha_documento"]) == 2026
    assert "impugnación administrativa" in identidad["materia"]

def test_materia_exige_los_dos_puntos():
    """Sin los dos puntos engancha cualquier mención de la palabra en el cuerpo,
    y esa cadena termina siendo la bajada del documento entregado."""
    pagina = ("Las instrucciones impartidas previamente sobre la materia y su\n"
              "aplicación se detallan a continuación.\n"
              "CIRCULAR N°40.-\n"
              "MATERIA: Instruye sobre el nuevo procedimiento.\n")
    identidad = ef.detectar_identidad(pagina)
    assert identidad["materia"].startswith("Instruye sobre el nuevo procedimiento")

def test_materia_ausente_queda_en_none():
    assert ef.detectar_identidad("CIRCULAR N°40.-")["materia"] is None

def test_materia_corta_ante_la_siguiente_etiqueta_del_recuadro():
    """Sin el corte, la referencia legal queda pegada a la bajada del documento."""
    pagina = ("CIRCULAR N°35.-\n"
              "MATERIA: Actualiza instrucciones sobre \n"
              "mecanismos de impugnación administrativa: \n"
              "RAV, RAF y Recurso Jerárquico. \n"
              "REF. LEGAL: Artículos 123 bis y 124 del Código Tributario.\n")
    materia = ef.detectar_identidad(pagina)["materia"]
    assert materia.startswith("Actualiza instrucciones sobre mecanismos")
    assert "RAV, RAF y Recurso Jerárquico" in materia
    assert "REF. LEGAL" not in materia

def test_el_cuerpo_no_gana_sobre_el_recuadro_identificatorio():
    """La página cita normas anteriores antes de llegar al recuadro; quedarse
    con la primera aparición fabrica una identidad plausible y falsa."""
    pagina = ("La presente circular reemplaza la Circular N° 12, de 2019, y\n"
              "complementa la Resolución Exenta SII N° 112, de 2020.\n"
              "Con fecha 15 de enero de 2018 este Servicio impartió instrucciones.\n"
              "CIRCULAR N°35.-\n"
              "FECHA: 31 DE AGOSTO DE 2026\n")
    identidad = ef.detectar_identidad(pagina)
    assert identidad["tipo"] == "circular"
    assert identidad["numero"] == "35"
    assert identidad["fecha_documento"] == "31 de agosto de 2026"

def test_sin_recuadro_no_se_inventa_identidad():
    """Es preferible pedirle los datos al usuario que fabricar un número a
    partir de una cita del cuerpo."""
    pagina = ("Lo dispuesto en la Circular N° 12 de 2019 se mantiene vigente,\n"
              "conforme a la Resolución Exenta SII N° 112 de 2020.\n")
    identidad = ef.detectar_identidad(pagina)
    assert identidad["tipo"] is None
    assert identidad["numero"] is None

def test_la_fecha_del_recuadro_gana_sobre_la_del_cuerpo():
    pagina = ("Con fecha 15 de enero de 2018 este Servicio impartió instrucciones.\n"
              "CIRCULAR N°35.-\nFECHA: 31 DE AGOSTO DE 2026\n")
    assert ef.detectar_identidad(pagina)["fecha_documento"] == "31 de agosto de 2026"

def test_la_fecha_exige_los_dos_puntos():
    pagina = "CIRCULAR N°35.-\ncon fecha 15 de enero de 2018 se instruyó lo anterior\n"
    assert ef.detectar_identidad(pagina)["fecha_documento"] is None

def test_el_valor_del_usuario_corrige_la_deteccion():
    """Si la detección se equivocó, los flags existen para corregirla. Descartar
    el valor del usuario dejaría el dato malo marcado como 'detectado'."""
    detectada = {"tipo": "circular", "numero": "41",
                 "fecha_documento": None, "materia": None}
    completada = ef.completar_identidad(detectada, {"numero": "35"})
    assert completada["numero"] == "35"
    fuente = ef.construir_fuente(
        ["x"], {"clase": "pdf", "ruta": "x.pdf"}, completada)
    assert fuente["numero"] == "35"
    assert fuente["procedencia_campos"]["numero"] == "usuario"

def test_construir_fuente_no_lee_el_anio_de_la_identidad():
    """La derivación es la única vía, aunque la identidad traiga la clave."""
    identidad = {"tipo": "circular", "numero": "35", "materia": None,
                 "fecha_documento": "2 de enero de 2025", "anio": 2026}
    fuente = ef.construir_fuente(
        ["x"], {"clase": "pdf", "ruta": "x.pdf"}, identidad)
    assert fuente["anio"] == 2025

def test_parsear_fecha_esta_anclada():
    """Sin anclas deja de ser la única puerta: extraería una fecha de una frase."""
    assert ef.parsear_fecha("ver circular 12 del 31/08/2026 y siguientes") is None
    assert ef.parsear_fecha("x31 de agosto de 2026") is None

def test_parsear_fecha_con_mes_inexistente_no_revienta():
    assert ef.parsear_fecha("31 de brumario de 2026") is None

def test_url_con_userinfo_rechazada():
    """https://sii.cl@malo.com/ es el clásico para saltarse un chequeo de host."""
    with pytest.raises(ef.UrlRechazada):
        ef.validar_url("https://www.sii.cl@malo.com/doc.pdf")

def test_redirect_a_http_dentro_del_dominio_rechazado():
    with pytest.raises(ef.UrlRechazada):
        ef.validar_salto("https://www.sii.cl/a.pdf", "http://www.sii.cl/b.pdf")

def test_content_type_se_compara_por_media_type():
    """Buscar la subcadena en la cabecera completa acepta un HTML con
    'application/pdf' en un parámetro."""
    with pytest.raises(ef.UrlRechazada):
        ef.exigir_pdf("text/html; x=application/pdf")

def test_detecta_resolucion_exenta():
    identidad = ef.detectar_identidad("RESOLUCIÓN EXENTA SII N° 112.-\nFECHA: 4 DE MARZO DE 2025")
    assert identidad["tipo"] == "resolucion"
    assert identidad["numero"] == "112"

def test_detecta_oficio():
    identidad = ef.detectar_identidad("OFICIO N° 1408.-\nFECHA: 10 DE JULIO DE 2024")
    assert identidad["tipo"] == "oficio"
    assert identidad["numero"] == "1408"

def test_campos_no_detectados_quedan_en_none():
    identidad = ef.detectar_identidad("Un texto cualquiera sin bloque identificatorio.")
    assert identidad["tipo"] is None
    assert identidad["numero"] is None
    assert identidad["fecha_documento"] is None

def test_anio_no_es_un_campo_de_identidad():
    """El año no se detecta ni se pide: se deriva de la fecha."""
    assert "anio" not in ef.CAMPOS_DE_IDENTIDAD
    assert "anio" not in ef.detectar_identidad(PAGINA_1)

def test_el_anio_no_se_infiere_del_reloj():
    identidad = ef.detectar_identidad("CIRCULAR N°12.-\nsin línea de fecha")
    assert ef.derivar_anio(identidad["fecha_documento"]) is None

def test_el_anio_no_se_infiere_del_nombre_del_archivo():
    fuente = ef.construir_fuente(
        paginas=["CIRCULAR N°12.-"],
        origen={"clase": "pdf", "ruta": "circular-12-de-2019.pdf"},
        identidad=ef.detectar_identidad("CIRCULAR N°12.-"),
    )
    assert fuente["anio"] is None

def test_el_anio_siempre_deriva_de_la_fecha():
    identidad = ef.detectar_identidad("CIRCULAR N°12.-\nFECHA: 2 DE ENERO DE 2025")
    fuente = ef.construir_fuente(
        paginas=["x"], origen={"clase": "pdf", "ruta": "x.pdf"}, identidad=identidad)
    assert fuente["anio"] == 2025

def test_parsear_fecha_canoniza_las_formas_admitidas():
    assert ef.parsear_fecha("31 de agosto de 2026") == "31 de agosto de 2026"
    assert ef.parsear_fecha("31/08/2026") == "31 de agosto de 2026"
    assert ef.parsear_fecha("31-08-2026") == "31 de agosto de 2026"
    assert ef.parsear_fecha("4 de Marzo de 2025") == "4 de marzo de 2025"
    assert ef.parsear_fecha("1 de setiembre de 2025") == "1 de septiembre de 2025"

def test_parsear_fecha_rechaza_lo_que_no_existe_en_el_calendario():
    assert ef.parsear_fecha("31 de febrero de 2026") is None
    assert ef.parsear_fecha("30 de febrero de 2024") is None
    assert ef.parsear_fecha("32/01/2026") is None

def test_parsear_fecha_rechaza_texto_libre():
    assert ef.parsear_fecha("mañana 2026") is None
    assert ef.parsear_fecha("agosto de 2026") is None
    assert ef.parsear_fecha("") is None
    assert ef.parsear_fecha(None) is None

def test_fecha_de_usuario_invalida_se_rechaza():
    """Un string libre no puede convertirse en identidad válida."""
    identidad = ef.detectar_identidad("sin bloque identificatorio")
    with pytest.raises(ValueError) as error:
        ef.completar_identidad(identidad, {"fecha_documento": "mañana 2026"})
    assert "fecha_documento" in str(error.value)

def test_fecha_de_usuario_inexistente_se_rechaza():
    identidad = ef.detectar_identidad("sin bloque identificatorio")
    with pytest.raises(ValueError):
        ef.completar_identidad(identidad, {"fecha_documento": "31 de febrero de 2026"})

def test_fecha_de_usuario_se_guarda_canonizada():
    identidad = ef.detectar_identidad("sin bloque identificatorio")
    completada = ef.completar_identidad(identidad, {"fecha_documento": "31/08/2026"})
    assert completada["fecha_documento"] == "31 de agosto de 2026"

def test_numero_de_usuario_debe_ser_digitos():
    identidad = ef.detectar_identidad("sin bloque identificatorio")
    with pytest.raises(ValueError) as error:
        ef.completar_identidad(identidad, {"numero": "treinta y cinco"})
    assert "numero" in str(error.value)

def test_tipo_de_usuario_debe_estar_en_el_catalogo():
    identidad = ef.detectar_identidad("sin bloque identificatorio")
    with pytest.raises(ValueError):
        ef.completar_identidad(identidad, {"tipo": "instructivo"})

def test_nunca_hay_fecha_valida_con_anio_nulo():
    """Si hay fecha en fuente.json, el año derivado existe."""
    identidad = ef.detectar_identidad(PAGINA_1)
    fuente = ef.construir_fuente(
        paginas=[PAGINA_1], origen={"clase": "pdf", "ruta": "x.pdf"}, identidad=identidad)
    assert (fuente["fecha_documento"] is None) == (fuente["anio"] is None)
    assert fuente["anio"] == 2026

def test_anio_no_se_acepta_como_input_del_usuario():
    """El estado 'fecha de 2025 con año 2026' no debe ser representable."""
    identidad = ef.detectar_identidad("sin bloque identificatorio")
    with pytest.raises(ValueError) as error:
        ef.completar_identidad(identidad, {"fecha_documento": "2 de enero de 2025",
                                           "anio": 2026})
    assert "anio" in str(error.value)

def test_anio_aportado_por_el_usuario_se_deriva_de_su_fecha():
    identidad = ef.detectar_identidad("sin bloque identificatorio")
    completada = ef.completar_identidad(
        identidad, {"tipo": "circular", "numero": "40",
                    "fecha_documento": "2 de enero de 2025"})
    fuente = ef.construir_fuente(
        paginas=["x"], origen={"clase": "pdf", "ruta": "x.pdf"}, identidad=completada)
    assert fuente["anio"] == 2025
    assert fuente["procedencia_campos"]["anio"] == "derivado"

def test_construir_fuente_arma_paginas_y_normalizaciones():
    fuente = ef.construir_fuente(
        paginas=["CIRCULAR N°35.-\nFECHA: 31 DE AGOSTO DE 2026", "noventa días hábiles"],
        origen={"clase": "pdf", "ruta": "circu35.pdf"},
        identidad=ef.detectar_identidad(PAGINA_1),
    )
    assert fuente["metricas"]["paginas"] == 2
    assert fuente["paginas"][1]["n"] == 2
    assert "noventadíashábiles" in fuente["paginas_normalizadas"][1]["texto"]
    assert "noventadíashábiles" in fuente["texto_normalizado"]

def test_procedencia_campos_marca_lo_detectado():
    fuente = ef.construir_fuente(
        paginas=[PAGINA_1],
        origen={"clase": "pdf", "ruta": "circu35.pdf"},
        identidad=ef.detectar_identidad(PAGINA_1),
    )
    assert fuente["procedencia_campos"]["numero"] == "detectado"
    assert fuente["procedencia_campos"]["fecha_documento"] == "detectado"
    assert fuente["procedencia_campos"]["anio"] == "derivado"

def test_procedencia_campos_marca_lo_aportado_por_el_usuario():
    identidad = ef.detectar_identidad("texto sin bloque identificatorio")
    identidad_completada = ef.completar_identidad(
        identidad, {"tipo": "circular", "numero": "40",
                    "fecha_documento": "2 de enero de 2026"})
    fuente = ef.construir_fuente(
        paginas=["texto sin bloque identificatorio"],
        origen={"clase": "pdf", "ruta": "x.pdf"},
        identidad=identidad_completada,
    )
    assert fuente["procedencia_campos"]["numero"] == "usuario"
    assert fuente["numero"] == "40"

def test_identidad_incompleta_aborta():
    identidad = ef.detectar_identidad("texto sin bloque identificatorio")
    with pytest.raises(ef.IdentidadIncompleta) as error:
        ef.exigir_identidad_completa(identidad)
    assert "numero" in str(error.value)

import pytest

def test_url_https_de_sii_aceptada():
    url = "https://www.sii.cl/normativa_legislacion/circulares/2026/circu35.pdf"
    assert ef.validar_url(url) == url

def test_url_http_rechazada():
    with pytest.raises(ef.UrlRechazada) as error:
        ef.validar_url("http://www.sii.cl/circu35.pdf")
    assert "https" in str(error.value).lower()

def test_url_de_otro_dominio_rechazada():
    with pytest.raises(ef.UrlRechazada) as error:
        ef.validar_url("https://ejemplo.com/circu35.pdf")
    assert "ejemplo.com" in str(error.value)

def test_subdominio_de_sii_aceptado():
    assert ef.validar_url("https://homer.sii.cl/doc.pdf")

def test_dominio_que_termina_parecido_rechazado():
    # "notsii.cl" no es subdominio de sii.cl
    with pytest.raises(ef.UrlRechazada):
        ef.validar_url("https://notsii.cl/doc.pdf")

def test_redirect_fuera_del_dominio_rechazado():
    with pytest.raises(ef.UrlRechazada) as error:
        ef.validar_salto("https://www.sii.cl/a.pdf", "https://cdn-externo.com/a.pdf")
    assert "cdn-externo.com" in str(error.value)

def test_redirect_dentro_del_dominio_aceptado():
    assert ef.validar_salto("https://www.sii.cl/a.pdf", "https://www.sii.cl/b.pdf")

def test_respuesta_html_rechazada():
    with pytest.raises(ef.UrlRechazada) as error:
        ef.exigir_pdf("text/html; charset=utf-8")
    assert "pdf" in str(error.value).lower()

def test_respuesta_pdf_aceptada():
    assert ef.exigir_pdf("application/pdf")

import email.message, urllib.error


class _RespuestaFalsa:
    def __init__(self, cuerpo, content_type="application/pdf"):
        self._cuerpo = cuerpo
        self.headers = {"Content-Type": content_type}
    def read(self): return self._cuerpo
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _AbridorFalso:
    """Registra CADA URL que se intenta abrir: el test falla si toca un host externo."""
    def __init__(self, guion):
        self.guion = guion          # url -> ("redirect", destino) | ("ok", cuerpo)
        self.visitadas = []

    def open(self, url):
        self.visitadas.append(url)
        accion, valor = self.guion[url]
        if accion == "redirect":
            cabeceras = email.message.Message()
            cabeceras["Location"] = valor
            raise urllib.error.HTTPError(url, 302, "Found", cabeceras, None)
        return _RespuestaFalsa(valor)


def test_redirect_dentro_del_dominio_se_sigue(tmp_path):
    abridor = _AbridorFalso({
        "https://www.sii.cl/a.pdf": ("redirect", "https://www.sii.cl/b.pdf"),
        "https://www.sii.cl/b.pdf": ("ok", b"%PDF-1.4"),
    })
    destino = str(tmp_path / "d.pdf")
    ef.descargar_pdf("https://www.sii.cl/a.pdf", destino, abridor=abridor)
    assert abridor.visitadas == ["https://www.sii.cl/a.pdf", "https://www.sii.cl/b.pdf"]

def test_el_host_externo_nunca_se_abre(tmp_path):
    """La validación ocurre ANTES de seguir el salto, no después de haberlo hecho."""
    abridor = _AbridorFalso({
        "https://www.sii.cl/a.pdf": ("redirect", "https://cdn-externo.com/a.pdf"),
        "https://cdn-externo.com/a.pdf": ("ok", b"%PDF-1.4"),
    })
    with pytest.raises(ef.UrlRechazada):
        ef.descargar_pdf("https://www.sii.cl/a.pdf", str(tmp_path / "d.pdf"),
                         abridor=abridor)
    assert "https://cdn-externo.com/a.pdf" not in abridor.visitadas

def test_redirect_relativo_se_resuelve_y_se_valida(tmp_path):
    abridor = _AbridorFalso({
        "https://www.sii.cl/docs/a.pdf": ("redirect", "/otros/b.pdf"),
        "https://www.sii.cl/otros/b.pdf": ("ok", b"%PDF-1.4"),
    })
    ef.descargar_pdf("https://www.sii.cl/docs/a.pdf", str(tmp_path / "d.pdf"),
                     abridor=abridor)
    assert abridor.visitadas[-1] == "https://www.sii.cl/otros/b.pdf"

def test_cadena_de_redirects_demasiado_larga(tmp_path):
    guion = {f"https://www.sii.cl/{i}.pdf": ("redirect", f"https://www.sii.cl/{i + 1}.pdf")
             for i in range(10)}
    abridor = _AbridorFalso(guion)
    with pytest.raises(ef.UrlRechazada) as error:
        ef.descargar_pdf("https://www.sii.cl/0.pdf", str(tmp_path / "d.pdf"),
                         abridor=abridor)
    assert "redirects" in str(error.value)
    assert len(abridor.visitadas) == ef.MAXIMO_DE_SALTOS + 1

def test_respuesta_html_tras_redirect_valido_se_rechaza(tmp_path):
    class _AbridorHtml(_AbridorFalso):
        def open(self, url):
            self.visitadas.append(url)
            return _RespuestaFalsa(b"<html>", content_type="text/html")
    abridor = _AbridorHtml({})
    with pytest.raises(ef.UrlRechazada):
        ef.descargar_pdf("https://www.sii.cl/a.pdf", str(tmp_path / "d.pdf"),
                         abridor=abridor)

def test_pdf_sin_capa_de_texto_aborta(tmp_path, monkeypatch):
    class PaginaVacia:
        def extract_text(self):
            return ""
    class LectorFalso:
        pages = [PaginaVacia(), PaginaVacia()]
    monkeypatch.setitem(__import__("sys").modules, "pypdf",
                        type("m", (), {"PdfReader": lambda ruta: LectorFalso()}))
    with pytest.raises(ef.PdfSinTexto):
        ef.leer_pdf("cualquiera.pdf")


def test_n2_conserva_el_guion_entre_cifras():
    """"30-60 UTM" y "3060 UTM" son cantidades distintas: borrar el guion dejaba
    que una cita reescribiera un rango de la fuente como un número único."""
    assert (ef.normalizar_matching("de 30-60 UTM")
            != ef.normalizar_matching("de 3060 UTM"))
    # el guion de maquetado entre letras se sigue eliminando
    assert (ef.normalizar_matching("jurídico-tributario")
            == ef.normalizar_matching("jurídicotributario"))


def test_la_materia_del_recuadro_gana_sobre_la_del_cuerpo():
    """El tercer hermano de los otros dos: el cuerpo puede decir "sobre la
    siguiente materia:" antes del recuadro, y esa cadena termina siendo la
    bajada de la portada que va al cliente."""
    pagina = ("El Servicio se pronuncia sobre la siguiente materia: la procedencia\n"
              "del recurso respecto de las liquidaciones emitidas.\n"
              "CIRCULAR N°35.-\n"
              "MATERIA: Actualiza instrucciones sobre mecanismos de impugnación.\n")
    materia = ef.detectar_identidad(pagina)["materia"]
    assert materia.startswith("Actualiza instrucciones")
    assert "procedencia" not in materia
