"""Verificacion determinista de consistencia preview -> transform.

Compara, para UN movimiento_id, las LineaSoftland[] que produjo
`transform.py --preview` (clave 'previstos') contra las que produjo el
`transform.py` normal tras la aprobacion humana (clave 'transformados').
Es el gate de seguridad que debe ejecutarse antes de `export_softland.py`:
si preview y transform no son estructuralmente identicos para ese
movimiento, no debe generarse ningun CSV.

Este script NO:
- recalcula ni reconstruye ninguna LineaSoftland (eso es responsabilidad
  exclusiva de transform.py);
- acepta un modo por lote -- una invocacion verifica exactamente un
  movimiento_id;
- escribe ningun archivo, en exito ni en fallo (no tiene --out);
- hace una whitelist de campos: compara TODA la estructura de cada
  LineaSoftland, incluyendo el dict anidado campos_1_a_61, sin excepciones.

Contrato de salida: exit 0 si son identicas, exit 1 con un ConsistenciaError
de codigo estable (mismo patron que TransformError/ExportError) si no.
"""
import argparse
import json
import sys


class ConsistenciaError(ValueError):
    """Error explicito de verificacion, con codigo estable para tests."""
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        super().__init__(f"{codigo}: {mensaje}")


def _cargar_lote(path, clave_esperada, codigo_invalido):
    with open(path, encoding="utf-8") as f:
        datos = json.load(f)
    if not isinstance(datos, dict) or clave_esperada not in datos:
        raise ConsistenciaError(
            codigo_invalido,
            f"El archivo {path!r} no tiene la clave {clave_esperada!r} esperada "
            "-- revisar si los archivos de preview/transform se entregaron invertidos.",
        )
    return datos[clave_esperada]


def _primera_diferencia_valor(preview, transform, ruta):
    """Recorre recursivamente dicts/listas comparando TODO el contenido de UNA
    linea (sin whitelist de campos). Devuelve None si son iguales, o (ruta,
    valor_preview, valor_transform) para la primera discrepancia encontrada,
    en un orden deterministico (claves de dict ordenadas, listas en su orden
    real). 'ruta' nunca incluye el indice de linea -- eso lo maneja
    _primera_diferencia_lineas() como un campo separado."""
    if isinstance(preview, dict) and isinstance(transform, dict):
        claves = sorted(set(preview.keys()) | set(transform.keys()), key=str)
        for clave in claves:
            sub_ruta = f"{ruta}.{clave}" if ruta else str(clave)
            if clave not in preview:
                return (sub_ruta, "<ausente>", transform.get(clave))
            if clave not in transform:
                return (sub_ruta, preview.get(clave), "<ausente>")
            diferencia = _primera_diferencia_valor(preview[clave], transform[clave], sub_ruta)
            if diferencia is not None:
                return diferencia
        return None

    if isinstance(preview, list) and isinstance(transform, list):
        if len(preview) != len(transform):
            return (ruta or "<raiz>", preview, transform)
        for indice, (a, b) in enumerate(zip(preview, transform)):
            sub_ruta = f"{ruta}[{indice}]"
            diferencia = _primera_diferencia_valor(a, b, sub_ruta)
            if diferencia is not None:
                return diferencia
        return None

    if preview != transform:
        return (ruta or "<raiz>", preview, transform)
    return None


def _primera_diferencia_lineas(lineas_preview, lineas_transform):
    """Compara LineaSoftland[] linea por linea, en orden. El indice de linea
    se reporta como campo propio (nunca mezclado dentro de la ruta de campo),
    en numeracion 1-based para el mensaje humano. Si un lado tiene menos
    lineas que el otro, identifica la PRIMERA linea que existe en un lado y
    no en el otro -- nunca un mensaje generico de solo cantidades -- usando
    el sentinela explicito '<ausente>' para el lado faltante.

    Devuelve None si son identicas, o un dict {indice, campo, valor_preview,
    valor_transform} para la primera discrepancia (indice es 0-based; quien
    construye el mensaje final decide como presentarlo)."""
    total = max(len(lineas_preview), len(lineas_transform))
    for indice in range(total):
        if indice >= len(lineas_preview):
            return {
                "indice": indice, "campo": "<linea_completa>",
                "valor_preview": "<ausente>", "valor_transform": lineas_transform[indice],
            }
        if indice >= len(lineas_transform):
            return {
                "indice": indice, "campo": "<linea_completa>",
                "valor_preview": lineas_preview[indice], "valor_transform": "<ausente>",
            }
        diferencia = _primera_diferencia_valor(lineas_preview[indice], lineas_transform[indice], "")
        if diferencia is not None:
            campo, valor_preview, valor_transform = diferencia
            return {
                "indice": indice, "campo": campo,
                "valor_preview": valor_preview, "valor_transform": valor_transform,
            }
    return None


def verificar(preview_json, transform_json, movimiento_id):
    """Funcion pura. Lanza ConsistenciaError con codigo estable si algo no
    coincide; no devuelve nada (ni escribe archivos) si todo es identico."""
    previstos = _cargar_lote(preview_json, "previstos", "PREVIEW_INVALIDO")
    transformados = _cargar_lote(transform_json, "transformados", "TRANSFORM_INVALIDO")

    if movimiento_id not in previstos:
        raise ConsistenciaError(
            "MOVIMIENTO_NO_ENCONTRADO_EN_PREVIEW",
            f"movimiento_id={movimiento_id!r} no existe en 'previstos' de {preview_json!r}.",
        )
    if movimiento_id not in transformados:
        raise ConsistenciaError(
            "MOVIMIENTO_NO_ENCONTRADO_EN_TRANSFORM",
            f"movimiento_id={movimiento_id!r} no existe en 'transformados' de {transform_json!r}.",
        )

    lineas_preview = previstos[movimiento_id]
    lineas_transform = transformados[movimiento_id]

    if not lineas_preview:
        raise ConsistenciaError(
            "SIN_LINEAS_PREVIEW",
            f"movimiento_id={movimiento_id!r} tiene 0 lineas en 'previstos' -- nada que verificar.",
        )
    if not lineas_transform:
        raise ConsistenciaError(
            "SIN_LINEAS_TRANSFORM",
            f"movimiento_id={movimiento_id!r} tiene 0 lineas en 'transformados' -- nada que verificar.",
        )

    diferencia = _primera_diferencia_lineas(lineas_preview, lineas_transform)
    if diferencia is not None:
        linea_humana = diferencia["indice"] + 1  # numeracion 1-based para el mensaje al usuario
        raise ConsistenciaError(
            "LINEAS_DIFERENTES",
            f"movimiento_id={movimiento_id!r}, linea={linea_humana}, "
            f"campo={diferencia['campo']!r}: "
            f"preview={diferencia['valor_preview']!r} != transform={diferencia['valor_transform']!r}.",
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preview_json", help="Salida de 'transform.py --preview' (clave 'previstos')")
    parser.add_argument("transform_json", help="Salida de 'transform.py' normal (clave 'transformados')")
    parser.add_argument("movimiento_id")
    args = parser.parse_args(argv)

    try:
        verificar(args.preview_json, args.transform_json, args.movimiento_id)
    except ConsistenciaError as e:
        print(f"Verificacion de consistencia fallida: {e}", file=sys.stderr)
        return 1

    print(
        f"Consistencia verificada: movimiento_id={args.movimiento_id!r} -- "
        "preview y transform son estructuralmente identicos."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
