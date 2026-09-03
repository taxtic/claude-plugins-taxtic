---
name: resumen-circular-sii
description: Genera un resumen ejecutivo en Word y PDF con marca TAXTIC de una circular, resolución exenta u oficio del SII, a partir de un PDF local o una URL de sii.cl. Cada afirmación factual queda respaldada por una cita textual verificada contra el documento; el criterio profesional va aparte y sin datos verificables. Palabras gatillo: "resume esta circular", "qué dice esta resolución", "resumen de este oficio", "impacto de esta normativa".
---

**Idioma de respuesta:** siempre en español chileno. Terminología contable y tributaria local. Todo el output en español.

# Resumen normativo SII (orquestador — tres fases)

Coordinas la generación del resumen. **No leas el PDF tú mismo**: un script lo extrae de forma determinista y escribe `fuente.json`, que es la fuente de verdad contra la que se verifican tus citas. Tú redactas; un gate valida antes de que se arme el documento.

## Inputs

Un PDF local, o una URL `https` de `sii.cl` que resuelva a un PDF. Un documento publicado solo en HTML no se procesa: pide al usuario que lo guarde a PDF primero.

Los scripts necesitan `pypdf`, `python-docx` y, para el PDF, `pywin32`. Si falta alguno, el primer comando lo dice y se instalan con `pip install -r requirements.txt` desde el directorio del plugin.

## FASE 1 — Extracción determinista

Ejecuta con `Bash`:

```
python scripts/extraer_fuente.py "<pdf-o-url>" --out fuente.json
```

Escribe `fuente.json` con el texto por página, sus normalizaciones y la identidad del documento (tipo, número, fecha, materia). El año se deriva de la fecha; nunca se pide ni se teclea por separado.

**Cómo se detecta la identidad.** El tipo y el número salen únicamente del recuadro identificatorio, que el SII cierra con `.-` (`CIRCULAR N°35.-`). Una mención del cuerpo no lleva esa marca y no se considera: quedarse con la primera norma citada en la introducción fabricaría una identidad completa, plausible y falsa. Si el documento no trae ese recuadro, **no se detecta ni el tipo ni el número**, y hay que aportarlos. La fecha se toma de una línea `FECHA:` con dos puntos, y la materia de una línea `MATERIA:`.

**Si el script sale con código 2**, falta identidad y te dice qué campos. Pregúntaselos al usuario y vuelve a correr el mismo comando agregando los flags que el script nombró:

```
python scripts/extraer_fuente.py "<pdf-o-url>" --out fuente.json \
  --tipo circular --numero "35" --fecha-documento "31 de agosto de 2026"
```

- Los flags son `--tipo` (`circular`, `resolucion` u `oficio`), `--numero` (solo dígitos) y `--fecha-documento` (`"31 de agosto de 2026"` o `"31/08/2026"`). **No existe `--anio`**: el año sale de la fecha.
- **Lo que aporta el usuario manda sobre lo detectado.** Si la detección se equivocó, los mismos flags la corrigen, y el campo queda marcado como aportado por el usuario en el respaldo.
- Con la identidad incompleta **no se escribe `fuente.json`**. No hay archivo a medias sobre el cual seguir: no pases a la fase 2 hasta que el script termine con código 0.
- Nunca infieras un campo del nombre del archivo, de la URL ni del año actual. Si el usuario no lo aporta, no se puede continuar.
- Si el PDF no tiene capa de texto, es un escaneo y no se procesa.
- **Nunca edites `fuente.json` a mano.** Es lo que hace verificables tus citas; tocarlo invalida la garantía completa.

Pregunta también el nombre de quien firma el resumen, para `meta.elaborado_por` (máximo 120 caracteres: es un nombre, no un campo de texto libre). Si no lo entregan, se omite la línea.

## FASE 2 — Redacción de `resumen.json`

Lee `fuente.json` y escribe `resumen.json` con `Write`.

### Secciones disponibles

Elige las secciones que el documento sustente, según el perfil del tipo detectado. Una sección que el perfil no admite hace fallar el gate. El orden en que las escribas no importa: el builder las emite en el orden del catálogo, con `caso_consultado` abriendo el oficio y `gestiones` y `a_verificar` cerrando siempre.

| Sección | Bloques permitidos | Circular | Resolución | Oficio |
|---|---|---|---|---|
| `caso_consultado` | `parrafo` | — | — | obligatoria |
| `deroga` | `parrafo`, `lista` | sugerida | sugerida | — |
| `tema` | `parrafo` | obligatoria | obligatoria | obligatoria |
| `alcance` | `parrafo`, `lista` | sugerida | obligatoria | sugerida |
| `comparacion` | `tabla`, `nota` | sugerida | sugerida | sugerida |
| `materia` | `subtitulo`, `parrafo`, `lista`, `tabla`, `callout` | sugerida | sugerida | sugerida |
| `procedimiento` | `lista`, `tabla` | sugerida | obligatoria | — |
| `reglas_comunes` | `lista` | sugerida | sugerida | — |
| `novedades` | `lista`, `callout` | sugerida | sugerida | sugerida |
| `plazos` | `tabla` | sugerida | sugerida | sugerida |
| `sanciones` | `parrafo`, `lista` | sugerida | sugerida | sugerida |
| `vigencia` | `parrafo` | sugerida | obligatoria | sugerida |
| `otra` | `parrafo`, `lista` | sugerida | sugerida | sugerida |
| `gestiones` | `lista` | obligatoria | obligatoria | obligatoria |
| `a_verificar` | `lista` | obligatoria | obligatoria | obligatoria |

**Una sección sin contenido real en la fuente no se emite.** Solo `materia` es repetible: cualquier otra sección duplicada hace fallar el gate.

`rotulo_id` de un `subtitulo` sale de esta lista cerrada: `ambito`, `procedimiento`, `requisitos`, `admisibilidad`, `oportunidad`, `plazos`, `resolucion`, `silencio`, `prueba`, `efectos`, `limitaciones`, `recursos`, `ejemplos`.

`variante` de un `callout`: `novedad` para lo que cambia, `critico` para lo que mal entendido cuesta caro, `proteccion` para los resguardos del contribuyente.

### Forma del archivo

Contrato cerrado: una propiedad que no esté en este esquema es error, no se ignora en silencio.

```json
{
  "meta": { "elaborado_por": "Asesor Tributario" },
  "secciones": [
    {
      "id": "tema",
      "bloques": [
        {
          "tipo": "parrafo",
          "afirmacion": "citada",
          "texto": "El Servicio debe pronunciarse dentro de 90 días hábiles administrativos.",
          "cita": "deberá pronunciarse dentro del plazo de noventa (90) días hábiles administrativos",
          "pagina": 1
        }
      ]
    },
    {
      "id": "materia",
      "titulo": {
        "texto": "Reposición administrativa voluntaria",
        "cita": "las instrucciones sobre el recurso de reposición administrativa voluntaria",
        "pagina": 2
      },
      "bloques": [
        { "tipo": "subtitulo", "rotulo_id": "plazos" },
        {
          "tipo": "lista",
          "afirmacion": "citada",
          "items": [
            {
              "texto": "El recurso se interpone dentro de 15 días hábiles administrativos.",
              "cita": "el recurso deberá interponerse dentro del plazo de quince días hábiles administrativos",
              "pagina": 2
            }
          ]
        },
        {
          "tipo": "tabla",
          "afirmacion": "citada",
          "encabezado": [
            { "texto": "Trámite", "cita": "los trámites que contempla el procedimiento administrativo", "pagina": 2 },
            { "texto": "Plazo", "cita": "los plazos aplicables a cada uno de esos trámites", "pagina": 2 }
          ],
          "filas": [
            [
              { "texto": "Interposición", "cita": "la interposición del recurso ante la unidad correspondiente", "pagina": 2 },
              { "texto": "15 días hábiles", "cita": "dentro del plazo de quince días hábiles administrativos", "pagina": 2 }
            ]
          ]
        },
        {
          "tipo": "callout",
          "variante": "critico",
          "afirmacion": "citada",
          "texto": "Vencido el plazo, la presentación se declara inadmisible.",
          "cita": "vencido el plazo señalado la presentación será declarada inadmisible",
          "pagina": 2
        }
      ]
    },
    {
      "id": "gestiones",
      "bloques": [
        {
          "tipo": "lista",
          "afirmacion": "derivada",
          "items": [{ "texto": "Revisar los expedientes en curso del estudio." }]
        }
      ]
    },
    {
      "id": "a_verificar",
      "bloques": [
        {
          "tipo": "lista",
          "afirmacion": "derivada",
          "items": [{ "texto": "Confirmar la publicación en el Diario Oficial." }]
        }
      ]
    }
  ]
}
```

`meta` es obligatorio, aunque vaya vacío (`{}`). Un bloque `nota` tiene la misma forma que un `parrafo`. Una celda de tabla vacía se escribe `{"texto": ""}` explícito y no lleva cita.

### Reglas que el gate hace cumplir

1. **Toda afirmación `citada` lleva cita textual y página.** La cita se copia de `paginas[].texto`, mínimo 40 caracteres una vez normalizada. Un párrafo, una nota o un ítem de lista llevan exactamente una cita (`cita` + `pagina`); solo una celda de tabla puede llevar hasta cuatro (`citas`), porque la grilla impide partir el contenido en dos. `cita` y `citas` son mutuamente excluyentes.

   **No transcribas los saltos de línea ni los cortes de palabra del PDF.** La comparación ignora espacios, guiones y comillas, así que escribe la cita en una sola línea con espacios simples: `deberá pronunciarse dentro del plazo` vale aunque la fuente diga `deberá pronun-\nciarse dentro del plazo`. Copiar los `\n` solo rompe el JSON.

   **La página se comprueba aparte de la existencia.** Una cita que existe en el documento pero en otra página da `PaginaInvalida`, no `CitaInexistente`: si te sale eso, el texto está bien y el número de página no.
2. **Los datos del texto de una `citada` tienen que estar en su cita.** Plazos, fechas, porcentajes, montos y referencias normativas. Puedes parafrasear `noventa días` como `90 días`, pero no puedes escribir un número que la cita no respalde. Las fechas se comparan completas: una cita donde el día, el mes y el año aparecen sueltos y en contextos distintos **no** respalda una fecha.
3. **Los títulos de sección y los subtítulos no los escribes tú.** Salen del catálogo. En los subtítulos envías `rotulo_id`. La única excepción es el título de una sección `materia`, que es libre y **lleva cita**.
4. **El título y la bajada del documento tampoco los escribes tú.** Se ensamblan desde `fuente.json`: el título con el tipo, el número y el año, y la bajada con `fuente.materia`, o sea la línea `MATERIA:` del documento copiada tal cual. Esa bajada **no pasa por el gate**, así que léela antes de reportar: es texto que llega al cliente con los artefactos que traiga la extracción, y a veces dice cosas que tu resumen no necesita repetir.
5. **`derivada` es solo para criterio profesional**, en `gestiones` y `a_verificar`, sin cita y **sin datos verificables de ningún tipo**. Si una recomendación necesita un plazo o una cifra, divídela en dos: el hecho como afirmación `citada`, la recomendación como `derivada`.
6. **Toda celda de tabla no vacía lleva cita**, incluidos los encabezados y la primera columna.
7. **Una sección obligatoria sin sustento no se rellena.** Va como ítem `derivada` de `a_verificar` con `suple_seccion` apuntando a la sección que suple. Solo se suple una sección **obligatoria en el perfil de este documento**, ausente y no suplida ya por otro ítem. `a_verificar` no se suple a sí misma.

En una circular las obligatorias son `tema`, `gestiones` y `a_verificar`, así que solo esas se pueden suplir:

```json
{ "texto": "El documento no enuncia un tema único; confirmar el alcance con el contribuyente.",
  "suple_seccion": "tema" }
```

En una resolución exenta las obligatorias son además `alcance`, `procedimiento` y `vigencia`; en un oficio, `caso_consultado`. Apuntar a una sección que no es obligatoria en el perfil del documento hace fallar el gate.

### Cifras: qué entiende el detector

El gate compara datos, no palabras, y solo reconoce estas formas:

- **Fechas completas:** `31 de agosto de 2026`, `31/08/2026`, `2026-08-31`.
- **Cantidades con unidad temporal:** días, meses y años, en cifras o en palabras (`noventa días` y `90 días` son el mismo dato).
- **Referencias normativas:** `artículo 123 bis`, `art. 124`, enumeraciones de artículos, y ley, decreto ley, decreto supremo, circular, resolución u oficio con su número.
- **Porcentajes:** `27%`, `10,5%`.
- **Montos:** `$1.500.000`, cifras con separador de miles, y cantidades en UTM, UTA o UF.
- **Años sueltos**, cuando no forman parte de una fecha.

**Todo lo demás con forma de dato falla cerrado.** No solo las cifras: también las palabras de cantidad y los nombres de mes. `48 horas`, `el N° 4 del artículo 97`, `el día 30`, `agosto de 2026` sin día, `el 5° día hábil`, `treinta por ciento`, `mil unidades tributarias`, `dos funcionarios` y `primero de enero` emiten un centinela en vez de un dato.

**El centinela lleva el contenido que no se pudo resolver, así que se compara.** Si tu cita dice exactamente lo mismo, la afirmación pasa: `dos funcionarios` respaldado por una cita que dice `dos funcionarios` está bien. Lo que el gate rechaza es afirmar `tres` cuando la cita dice `dos`. Tienes tres salidas cuando te rechaza:

1. **Reescribe la cifra** en una de las formas de arriba — `30%` en vez de `treinta por ciento` es además la forma inequívoca en un documento que se firma.
2. **Elige una cita que contenga la misma forma.** Si la fuente escribe `hasta el día sesenta (60)`, una cita que incluya esas palabras respalda tu `hasta el día sesenta`.
3. **Saca la cifra de tu texto** y deja que la cita la lleve. Los ordinales en palabras —`el sexagésimo día`— no emiten literal, así que sirven para decir el hecho sin la cifra.

En una `derivada` la regla es más estricta y **no basta con evitar dígitos**: tampoco puede llevar palabras de cantidad ni nombres de mes. `Revisar los expedientes dentro de treinta días` y `Coordinar la revisión para agosto` son rechazadas aunque no tengan un solo número. Divide en dos: el hecho como afirmación `citada`, la recomendación como `derivada`.

Aprovecha los recursos del formato cuando el documento los pida: una `comparacion` con tabla cuando hay alternativas que contrastar, `callout` de variante `novedad` para lo que cambia, `critico` para lo que mal entendido cuesta caro, y `proteccion` para los resguardos del contribuyente.

## FASE 3 — Gate, Word y PDF

```
python scripts/verificar_citas.py fuente.json resumen.json --respaldo respaldo-citas.md
python scripts/generar_resumen.py fuente.json resumen.json --docx "resumen-<tipo>-<numero>-<anio>.docx"
python scripts/exportar_pdf.py "resumen-<tipo>-<numero>-<anio>.docx"
```

El gate rechaza con código 1 e imprime `RECHAZADO [<clase>] <ruta del bloque>: <motivo>`. **Reporta todos los rechazos de la corrida, no solo el primero**, así que corrígelos todos antes de volver a correr. No sigas al builder con el gate en rojo.

`exportar_pdf.py` nunca falla duro: si Word no está disponible o la conversión se cae, imprime un aviso y el `.docx` sigue siendo la entrega. La conversión usa Word y a veces falla de forma transitoria —un archivo de bloqueo `~$` de una sesión anterior, por ejemplo—; vale reintentar una vez antes de dar el PDF por perdido.

## Reportar al usuario

- Los archivos generados: `.docx`, `.pdf` y `respaldo-citas.md`.
- Si la conversión a PDF falló, dilo y entrega el `.docx` igual.
- Qué secciones quedaron declaradas en `a_verificar` y por qué.
- Qué campos de identidad los aportó el usuario en vez de detectarse.
- **Pídele explícitamente que revise `respaldo-citas.md` antes de enviar el documento al cliente**, y aclara que ese archivo no se entrega.

## Límites

- El gate garantiza que cada cita existe en la página declarada y que los datos del texto coinciden con su respaldo. **No garantiza que la paráfrasis sea semánticamente fiel** ni que la extracción del PDF esté libre de artefactos: el texto extraído puede pegar un número de nota al pie a una cifra. La revisión del respaldo es lo que cubre eso.
- No verifica que el documento siga vigente.
- Un documento por invocación.
