import importlib.util, os, sys, types

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

ep = _cargar("exportar_pdf")


class _DocumentoFalso:
    def __init__(self, registro, opciones=None):
        self._registro = registro
        registro.append(("abrir", tuple(sorted((opciones or {}).items()))))
    def SaveAs(self, ruta, FileFormat=None): self._registro.append(("guardar", ruta))
    def Close(self, *a, **k): self._registro.append(("cerrar",))


class _WordFalso:
    def __init__(self, registro):
        self._registro = registro
        self.Visible = True
        self.DisplayAlerts = True
        self.Documents = types.SimpleNamespace(
            Open=lambda ruta, **opciones: _DocumentoFalso(registro, opciones))
    def Quit(self, *a): self._registro.append(("salir",) + tuple(a))


def _instalar_word(monkeypatch, registro, falla=False):
    def dispatch_ex(nombre):
        if falla:
            raise OSError("Word no está disponible")
        return _WordFalso(registro)
    def dispatch(nombre):
        registro.append(("dispatch-compartido",))
        return _WordFalso(registro)
    modulo = types.SimpleNamespace(Dispatch=dispatch, DispatchEx=dispatch_ex)
    monkeypatch.setitem(sys.modules, "win32com", types.SimpleNamespace(client=modulo))
    monkeypatch.setitem(sys.modules, "win32com.client", modulo)


def test_conversion_exitosa_devuelve_la_ruta_del_pdf(tmp_path, monkeypatch):
    registro = []
    _instalar_word(monkeypatch, registro)
    docx = tmp_path / "resumen.docx"
    docx.write_bytes(b"x")
    resultado = ep.exportar(str(docx))
    assert resultado["pdf"] == str(tmp_path / "resumen.pdf")
    assert resultado["aviso"] is None
    assert ("salir", ep.SIN_GUARDAR_CAMBIOS) in registro

def test_word_ausente_no_levanta_y_devuelve_aviso(tmp_path, monkeypatch):
    _instalar_word(monkeypatch, [], falla=True)
    docx = tmp_path / "resumen.docx"
    docx.write_bytes(b"x")
    resultado = ep.exportar(str(docx))
    assert resultado["pdf"] is None
    assert "Word" in resultado["aviso"]
    assert ".docx" in resultado["aviso"]

def test_docx_inexistente_devuelve_aviso(tmp_path, monkeypatch):
    _instalar_word(monkeypatch, [])
    resultado = ep.exportar(str(tmp_path / "no-existe.docx"))
    assert resultado["pdf"] is None
    assert resultado["aviso"]


def test_no_se_engancha_a_la_sesion_de_word_del_usuario(tmp_path, monkeypatch):
    """Word es un servidor de instancia única: Dispatch se engancharía al Word
    que el contador tiene abierto, y ocultarle las ventanas y llamar a Quit le
    cerraría su sesión con lo que estuviera escribiendo."""
    registro = []
    _instalar_word(monkeypatch, registro)
    docx = tmp_path / "resumen.docx"
    docx.write_bytes(b"x")
    ep.exportar(str(docx))
    assert ("dispatch-compartido",) not in registro

def test_quit_no_deja_word_esperando_una_respuesta(tmp_path, monkeypatch):
    """Sin el argumento, Word pregunta si guardar y el diálogo queda invisible."""
    registro = []
    _instalar_word(monkeypatch, registro)
    docx = tmp_path / "resumen.docx"
    docx.write_bytes(b"x")
    ep.exportar(str(docx))
    assert ("salir", ep.SIN_GUARDAR_CAMBIOS) in registro

def test_un_archivo_que_no_es_de_word_no_se_convierte(tmp_path, monkeypatch):
    """Word abriría un diálogo modal invisible para ofrecer la conversión y el
    proceso quedaría colgado; con un .pdf el destino además pisa el origen."""
    registro = []
    _instalar_word(monkeypatch, registro)
    for nombre in ("resumen.pdf", "datos.xlsx", "notas.txt"):
        archivo = tmp_path / nombre
        archivo.write_bytes(b"x")
        resultado = ep.exportar(str(archivo))
        assert resultado["pdf"] is None, nombre
        assert "Word" in resultado["aviso"]
    assert registro == []  # ni siquiera se arranca Word


def test_el_documento_se_abre_en_solo_lectura(tmp_path, monkeypatch):
    """Si el usuario tiene el mismo archivo abierto, una instancia invisible que
    lo pide en escritura queda esperando una respuesta que nadie puede dar."""
    registro = []
    _instalar_word(monkeypatch, registro)
    docx = tmp_path / "resumen.docx"
    docx.write_bytes(b"x")
    ep.exportar(str(docx))
    apertura = next(e for e in registro if e[0] == "abrir")
    assert ("ReadOnly", True) in apertura[1]
