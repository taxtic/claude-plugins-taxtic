import json, os

RAIZ_PLUGIN = os.path.join(os.path.dirname(__file__), "..")

def test_plugin_json_valido():
    ruta = os.path.join(RAIZ_PLUGIN, ".claude-plugin", "plugin.json")
    with open(ruta, encoding="utf-8") as f:
        manifiesto = json.load(f)
    assert manifiesto["name"] == "asesoria-normativa"
    assert manifiesto["version"] == "0.2.0"

def test_assets_de_marca_presentes_y_no_vacios():
    for nombre in ("imagotipo-principal-negro.png", "isologo-naranjo.png", "marca.md"):
        ruta = os.path.join(RAIZ_PLUGIN, "assets", nombre)
        assert os.path.isfile(ruta), f"falta el asset {nombre}"
        # isfile() es True para un archivo de 0 bytes: una copia fallida pasaría
        assert os.path.getsize(ruta) > 0, f"el asset {nombre} está vacío"

def test_requirements_declara_las_dependencias_con_sus_pisos():
    ruta = os.path.join(RAIZ_PLUGIN, "requirements.txt")
    with open(ruta, encoding="utf-8") as f:
        lineas = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    # Los pisos son el contrato: el resto del plugin depende de esas versiones.
    pisos = {"pypdf": ">=6.0", "python-docx": ">=1.1",
             "pywin32": ">=306", "pytest": ">=8.0"}
    for paquete, piso in pisos.items():
        declarada = next((l for l in lineas if l.startswith(paquete)), None)
        assert declarada, f"falta {paquete} en requirements.txt"
        assert piso in declarada, f"{paquete} sin piso de versión {piso}: {declarada!r}"

def test_pywin32_solo_se_instala_en_windows():
    """Sin el marcador, pip aborta el archivo entero en Linux o macOS."""
    ruta = os.path.join(RAIZ_PLUGIN, "requirements.txt")
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    linea = next(l for l in contenido.splitlines() if l.startswith("pywin32"))
    assert 'sys_platform == "win32"' in linea
