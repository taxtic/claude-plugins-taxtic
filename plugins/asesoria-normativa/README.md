# asesoria-normativa

Plugin de apoyo a asesoría tributaria para el equipo Taxtic.

## Componentes

- **Skill `/resumen-circular-sii`** — resumen ejecutivo en Word y PDF de una circular, resolución
  exenta u oficio del SII, con respaldo de citas verificado.
- **Skill `/checklist-f29`** — checklist pre-envío F29 por giro y régimen.
- **Agent `consultor-tributario`** — Q&A normativa tributaria chilena.

## `/resumen-circular-sii`

Tres fases: un script extrae el documento a `fuente.json` de forma determinista, el modelo redacta
`resumen.json` eligiendo secciones de un catálogo cerrado, y un gate valida antes de armar el
documento.

```
python scripts/extraer_fuente.py circular.pdf --out fuente.json
python scripts/verificar_citas.py fuente.json resumen.json --respaldo respaldo-citas.md
python scripts/generar_resumen.py fuente.json resumen.json --docx resumen-circular-35-2026.docx
python scripts/exportar_pdf.py resumen-circular-35-2026.docx
```

El tipo y el número del documento se detectan solo del recuadro identificatorio del SII, que cierra
el número con `.-`. Si el documento no lo trae, la extracción se detiene con código 2 y no escribe
`fuente.json`: los datos se aportan con `--tipo`, `--numero` y `--fecha-documento`, y lo aportado
manda sobre lo detectado. No hay `--anio`: el año se deriva de la fecha.

**Qué garantiza el gate:** que todo texto del documento tenga una procedencia verificable
estructuralmente. Son cinco y no hay una sexta:

| Procedencia | Quién escribe el texto |
|---|---|
| Determinista | se ensambla desde el documento fuente (título, bajada, fecha) |
| Catálogo | lista cerrada del plugin (títulos de sección y subtítulos) |
| Citada | el modelo, con cita textual obligatoria |
| Derivada | el modelo, sin cita: criterio profesional, solo en dos secciones y **sin datos verificables** |
| Entrada de usuario | el contador: los campos de identidad del documento y el nombre de quien firma |

Además, los plazos, fechas, cifras y referencias normativas de una afirmación citada tienen que
coincidir con los de su respaldo, y una cifra escrita en una forma que el detector no modela falla
cerrada en vez de pasar sin comparar.

**Qué no garantiza:** que la paráfrasis sea semánticamente fiel a la cita —una afirmación con sus
cifras bien respaldadas puede invertir el sentido si la cita empieza después de una negación—, que
una cita disyuntiva no respalde una afirmación asertiva, que una recomendación derivada no afirme
algo normativo de paso, que la extracción del PDF esté libre de artefactos de maquetado, ni que el
documento siga vigente. Por eso `respaldo-citas.md` es un paso de revisión
obligatorio antes de enviar, y **no se entrega al cliente**.

## Instalación

```
/plugin install asesoria-normativa@plugins-taxtic
```

Dependencias: `pip install -r requirements.txt` (`pypdf`, `python-docx`, `pywin32`, `pytest`).
La conversión a PDF usa Word; si no está disponible, se entrega el `.docx` con un aviso.

## Tests

```
python -m pytest tests/ -v
```

## Versión

0.2.0
