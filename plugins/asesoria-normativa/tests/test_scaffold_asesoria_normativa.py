import json, os

RAIZ_PLUGIN = os.path.join(os.path.dirname(__file__), "..")

def test_version_del_plugin_es_020():
    ruta = os.path.join(RAIZ_PLUGIN, ".claude-plugin", "plugin.json")
    with open(ruta, encoding="utf-8") as f:
        manifiesto = json.load(f)
    assert manifiesto["version"] == "0.2.0"

def test_assets_de_marca_presentes():
    for nombre in ("imagotipo-principal-negro.png", "isologo-naranjo.png", "marca.md"):
        ruta = os.path.join(RAIZ_PLUGIN, "assets", nombre)
        assert os.path.isfile(ruta), f"falta el asset {nombre}"

def test_requirements_declara_las_dependencias():
    ruta = os.path.join(RAIZ_PLUGIN, "requirements.txt")
    with open(ruta, encoding="utf-8") as f:
        contenido = f.read()
    for paquete in ("pypdf", "python-docx", "pywin32", "pytest"):
        assert paquete in contenido
