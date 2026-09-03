import json, os

RAIZ_REPO = os.path.join(os.path.dirname(__file__), "..", "..", "..")

def test_registrado_en_marketplace():
    ruta = os.path.join(RAIZ_REPO, ".claude-plugin", "marketplace.json")
    with open(ruta, encoding="utf-8") as f:
        marketplace = json.load(f)
    nombres = [p.get("name") for p in marketplace.get("plugins", [])]
    assert "asesoria-normativa" in nombres
