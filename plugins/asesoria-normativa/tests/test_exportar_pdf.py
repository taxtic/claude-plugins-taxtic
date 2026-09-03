import importlib.util, os, sys, types

def _cargar(nombre):
    ruta = os.path.join(os.path.dirname(__file__), "..", "scripts", nombre + ".py")
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo

ep = _cargar("exportar_pdf")


class _DocumentoFalso:
    def __init__(self, registro): self._registro = registro
    def SaveAs(self, ruta, FileFormat=None): self._registro.append(("guardar", ruta))
    def Close(self, *a, **k): self._registro.append(("cerrar",))


class _WordFalso:
    def __init__(self, registro):
        self._registro = registro
        self.Visible = True
        self.Documents = types.SimpleNamespace(Open=lambda ruta: _DocumentoFalso(registro))
    def Quit(self): self._registro.append(("salir",))


def _instalar_word(monkeypatch, registro, falla=False):
    def dispatch(nombre):
        if falla:
            raise OSError("Word no está disponible")
        return _WordFalso(registro)
    modulo = types.SimpleNamespace(Dispatch=dispatch)
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
    assert ("salir",) in registro

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
