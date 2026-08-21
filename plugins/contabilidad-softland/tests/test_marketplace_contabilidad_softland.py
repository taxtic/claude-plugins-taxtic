import json, os
ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")

def test_registrado_en_marketplace():
    with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8") as f:
        mk = json.load(f)
    nombres = [p.get("name") for p in mk.get("plugins", [])]
    assert "contabilidad-softland" in nombres
