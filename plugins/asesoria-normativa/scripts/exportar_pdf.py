"""Conversión del .docx a PDF con Word.

Falla suave a propósito: si Word no está instalado, está ocupado con un diálogo
abierto o la conversión se cae, el .docx ya generado se entrega igual con un
aviso. Un problema de conversión nunca debe dejar al usuario sin documento.
"""
import os

FORMATO_PDF = 17  # wdFormatPDF
SIN_GUARDAR_CAMBIOS = 0  # wdDoNotSaveChanges
EXTENSIONES_DE_WORD = (".docx", ".doc", ".rtf")


def exportar(ruta_docx):
    """Devuelve {"pdf": ruta | None, "aviso": str | None}. No levanta por fallo."""
    if not os.path.isfile(ruta_docx):
        return {"pdf": None, "aviso": f"no se encontró '{ruta_docx}' para convertir"}
    if not ruta_docx.lower().endswith(EXTENSIONES_DE_WORD):
        # Word ofrece convertir otros formatos con un diálogo modal. Como la
        # instancia es invisible, ese diálogo no se puede contestar y el proceso
        # queda colgado sin PDF, sin aviso y sin falla suave. Además, con un
        # .pdf de entrada el destino coincide con el origen y lo sobrescribiría.
        return {"pdf": None,
                "aviso": (f"'{ruta_docx}' no es un documento de Word; solo se "
                          f"convierten {', '.join(EXTENSIONES_DE_WORD)}")}

    destino = os.path.splitext(os.path.abspath(ruta_docx))[0] + ".pdf"
    word = None
    try:
        import win32com.client
        # DispatchEx arranca una instancia PROPIA. Dispatch se engancharía a la
        # que el usuario ya tiene abierta —Word es un servidor de instancia
        # única—, y entonces ocultarle las ventanas y llamar a Quit al terminar
        # le cerraría su sesión con lo que estuviera escribiendo.
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        documento = word.Documents.Open(os.path.abspath(ruta_docx))
        documento.SaveAs(destino, FileFormat=FORMATO_PDF)
        documento.Close(SIN_GUARDAR_CAMBIOS)
        return {"pdf": destino, "aviso": None}
    except Exception as error:
        return {"pdf": None,
                "aviso": (f"no se pudo convertir a PDF con Word ({error}). "
                          f"El documento .docx está disponible en '{ruta_docx}'.")}
    finally:
        if word is not None:
            try:
                # Sin el argumento, Word pregunta si guardar y el diálogo queda
                # invisible: el proceso sobreviviría colgado.
                word.Quit(SIN_GUARDAR_CAMBIOS)
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
