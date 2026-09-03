"""Conversión del .docx a PDF con Word.

Falla suave a propósito: si Word no está instalado, está ocupado con un diálogo
abierto o la conversión se cae, el .docx ya generado se entrega igual con un
aviso. Un problema de conversión nunca debe dejar al usuario sin documento.
"""
import os

FORMATO_PDF = 17  # wdFormatPDF


def exportar(ruta_docx):
    """Devuelve {"pdf": ruta | None, "aviso": str | None}. No levanta por fallo."""
    if not os.path.isfile(ruta_docx):
        return {"pdf": None, "aviso": f"no se encontró '{ruta_docx}' para convertir"}

    destino = os.path.splitext(os.path.abspath(ruta_docx))[0] + ".pdf"
    word = None
    try:
        import win32com.client
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        documento = word.Documents.Open(os.path.abspath(ruta_docx))
        documento.SaveAs(destino, FileFormat=FORMATO_PDF)
        documento.Close(False)
        return {"pdf": destino, "aviso": None}
    except Exception as error:
        return {"pdf": None,
                "aviso": (f"no se pudo convertir a PDF con Word ({error}). "
                          f"El documento .docx está disponible en '{ruta_docx}'.")}
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass


def _main():
    import argparse, sys
    analizador = argparse.ArgumentParser(description="Convierte el .docx del resumen a PDF")
    analizador.add_argument("docx")
    argumentos = analizador.parse_args()
    resultado = exportar(argumentos.docx)
    if resultado["pdf"]:
        print(f"Generado {resultado['pdf']}")
    else:
        print(f"AVISO: {resultado['aviso']}")
        sys.exit(0)  # el .docx sigue siendo una entrega válida


if __name__ == "__main__":
    _main()
