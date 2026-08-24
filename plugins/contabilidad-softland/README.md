# contabilidad-softland

Plugin para automatizar el procesamiento de conciliaciones bancarias de TAXTIC (banco BCI)
y generar movimientos compatibles con la Captura de Movimientos Mensuales de Softland.

Es un plugin **nuevo e independiente**: no reutiliza, modifica ni depende de
`contabilidad-conciliacion` ni de ningún otro plugin del marketplace.

## Instalación

```text
/plugin install contabilidad-softland@plugins-taxtic
```

## Estado actual: validado end-to-end en Softland real para el escenario base

El pipeline determinista implementado hasta ahora:

1. **`scripts/read_excel.py`** — lee el Excel de conciliación fila por fila, sin interpretar
   significado de negocio. Detecta y separa filas fuera de alcance (CARGO, fila `Total`,
   filas de control/saldo, filas vacías, columnas huérfanas con datos) de los movimientos
   candidatos.
2. **`scripts/normalize.py`** — convierte cada movimiento candidato en un `Movimiento` con sus
   `Asignacion[]` canónicas: normaliza fecha, montos y RUT; detecta uno o varios RUT por fila;
   extrae el folio de cada asignación conservando siempre el texto original; marca (sin decidir)
   los casos que requieren revisión humana o contable posterior.
3. **`scripts/validate.py`** — toma cada `Movimiento` normalizado y produce un
   `ResultadoValidacion` **separado** (nunca modifica el `Movimiento`) con `estado_motor`
   (`APTO`/`REVISION`/`ERROR`). Aplica las reglas del MVP (cuadratura exacta, diferencia
   Transbank con respaldo estructurado, textos especiales, boletas, RUT múltiple sin asociar)
   con precedencia `ERROR > REVISION > APTO`.
4. **`scripts/approval.py`** — capa de aprobación humana entre `validate.py` y `transform.py`.
   `preparar_revision()` arma el objeto que la skill muestra al usuario (sin recalcular
   reglas); `registrar_decision()` valida y persiste una decisión `APROBADO`/`RECHAZADO` por
   lote/corrida. La capa de decisión humana **solo aplica a `APTO`**: ni `APROBADO` ni `RECHAZADO`
   pueden registrarse sobre un movimiento `REVISION` o `ERROR`.
5. **`scripts/transform.py`** — toma `Movimiento` + `ResultadoValidacion` + `DecisionHumana` y
   produce `LineaSoftland[]` (1 `BANCO` + N `CLIENTE` + 0/1 `DIFERENCIA_TRANSBANK`), **solo** para
   `estado_motor == "APTO"` **y** `estado_humano == "APROBADO"` — cualquier otra combinación falla
   explícitamente, nunca se excluye en silencio. Cada línea incluye tanto la vista semántica
   (`cuenta`/`debe`/`haber`/`glosa`/...) como la vista posicional (`campos_1_a_61`, las 61
   posiciones oficiales de Softland). La cuenta del Banco se resuelve siempre desde
   `rules/taxtic.json`; un banco no configurado produce `BANCO_NO_CONFIGURADO`, nunca un fallback
   silencioso a BCI. Verifica `sum(debe) == sum(haber)` antes de devolver cualquier resultado.
   También admite un modo `--preview` de solo lectura: exige únicamente `estado_motor == "APTO"`
   (nunca aprobación), reutiliza exactamente la misma lógica de construcción de líneas, y produce
   las mismas `LineaSoftland[]` que el camino normal generará una vez aprobado.
6. **`scripts/export_softland.py`** — toma `LineaSoftland[]` ya transformadas (`APTO`+`APROBADO`,
   nunca reconstruye esa aprobación) y las serializa al formato físico de un **perfil de layout**
   (`rules/softland-layouts.json`). No decide cuentas, Debe/Haber, auxiliares ni glosas — solo
   convierte la forma semántica de `LineaSoftland` en una fila física y la escribe. Perfil por
   defecto: **`OFICIAL_61`** (ver más abajo). Vuelve a verificar `sum(debe) == sum(haber)` por
   `movimiento_id` como defensa redundante antes de escribir cualquier archivo, rechaza
   explícitamente una lista de líneas vacía (nunca genera un CSV vacío en silencio), y escribe
   siempre de forma atómica (temporal + rename) para nunca dejar un CSV parcial ante un error.
7. **`scripts/verificar_consistencia.py`** — gate determinista que compara, para un `movimiento_id`,
   las `LineaSoftland[]` de `transform.py --preview` contra las del `transform.py` normal posterior
   a la aprobación humana. Compara la estructura completa de cada línea (incluido `campos_1_a_61`,
   sin excepciones); ante cualquier discrepancia reporta `movimiento_id`, número de línea (1-based),
   campo o ruta del campo, y ambos valores en conflicto. No tiene modo por lote, no escribe ningún
   archivo, y su contrato es únicamente el código de salida del proceso.

**Confirmado con carga real en Softland** (ver "Limitaciones conocidas" para la evidencia
completa del historial de intentos):

- El **formato físico** del perfil `OFICIAL_61` (61 columnas, delimitador `;`, BOM UTF-8, sin campo
  final vacío, fechas `DD/MM/AAAA`) fue aceptado por el Capturador de Transacciones de Softland.
- El **escenario contable base** — banco BCI, abono de un cliente, `tipo_pago=SIMPLE`, una factura,
  diferencia `0`, cuentas `10-01-003`/`10-02-001` — fue confirmado por Contabilidad como
  efectivamente contabilizado de punta a punta en una prueba end-to-end real.

**Todavía NO existen / fuera de alcance de esta validación**:

- Ningún escenario más allá del descrito arriba tiene evidencia productiva propia: múltiples
  facturas, múltiples clientes, TRANSBANK, diferencias, otros bancos, proveedores, cargos.
- Skill conversacional: ya existe ([`conciliacion-softland`](skills/conciliacion-softland/SKILL.md)).
- Lectura automática de documentos de respaldo Transbank (email/PDF/reporte) — hoy
  `respaldo_diferencia` y `fuente_respaldo` solo se completan si un paso futuro o una
  resolución humana guiada enriquece el `Movimiento` antes de `validate.py`.

## Por qué no decide estados en normalize.py

El diseño de este plugin separa deliberadamente "normalizar datos" de "decidir su tratamiento
contable". `normalize.py` nunca asigna una cuenta Softland, nunca calcula Debe/Haber, y nunca
resuelve por heurística a qué RUT pertenece una factura cuando una fila trae varios RUT — solo
deja evidencia estructurada (`advertencias`, `senales_revision`, `errores_normalizacion`) para que
`validate.py` decida el `estado_motor`. A su vez, `estado_motor` y `estado_humano` (aprobación)
son dos fuentes de datos completamente separadas: `APTO` no significa `APROBADO`, y un movimiento
en `REVISION` o `ERROR` nunca puede quedar `APROBADO` — `approval.py` lo rechaza explícitamente.

## Reglas de negocio centralizadas

- [`rules/taxtic.json`](rules/taxtic.json) — cuentas contables confirmadas, auxiliares fijos,
  plantillas de glosa y tolerancia monetaria.
- [`rules/softland-columns.json`](rules/softland-columns.json) — las 61 columnas oficiales de la
  Captura de Movimientos Mensuales de Softland (ficha 03-08-2026), sin inventar contenido. Refleja
  **exclusivamente** el PDF oficial (perfil `OFICIAL_61`); permanece intacto desde su creación.
- [`rules/validation-rules.json`](rules/validation-rules.json) — patrones de normalización
  (separador multivalor, textos no-factura, detección de boletas) y campos esenciales.
- [`rules/softland-layouts.json`](rules/softland-layouts.json) — **perfiles de layout físico**
  para `export_softland.py`, deliberadamente separado de `softland-columns.json`:
  - **`OFICIAL_61`** (perfil por defecto) — 61 columnas, delimitador `;`, BOM UTF-8,
    sin campo final vacío, fechas `DD/MM/AAAA`, refleja `softland-columns.json` (PDF oficial) para
    las columnas 1–61. `formato_importador_validado: true` (coincide campo a campo con
    un archivo de carga real vigente + la estructura oficial exportada de Softland, y el
    propio Capturador de Transacciones aceptó realmente los archivos generados por este plugin) y
    `conciliacion_bancaria_validada: true` **escopeado** al escenario base confirmado (ver
    tabla de alcance más abajo y `_nota_estados_validacion` en el JSON).
  - **`OPERATIVO_62`** — hipótesis histórica basada en `captura.csv`, un archivo real
    pero de **otro** contenido contable (compras). Contradicha por evidencia más
    directa: la estructura real usa 61 columnas/`;`/BOM, no 62/`,`/sin BOM. Los 5 intentos reales
    con este perfil fallaron. `formato_importador_validado: false`. Se mantiene en el
    código solo como referencia histórica — no se elimina sin necesidad, pero no debe usarse.

## Fuentes de verdad (no intercambiables)

| Categoría | Fuente | Qué define |
|---|---|---|
| Reglas contables | Confirmaciones de Contabilidad | Cuentas, auxiliares (RUT sin DV), glosas, reglas Transbank, Debe/Haber |
| Formato físico vigente | `SOFTLAND.csv` (carga real vigente) + estructura oficial "Estructura Arch." de Softland, y cargas reales directas de este plugin | 61 columnas, delimitador `;`, BOM UTF-8, sin campo final vacío, CRLF, fecha `DD/MM/AAAA`, S/N en posiciones 37/38 |
| Layout oficial | `estructura softland.pdf` / PDF "Estructura Arch." (columnas 1–61) | Significado y posición de las 61 columnas documentadas |
| Escenario contable validado | Prueba end-to-end confirmada por Contabilidad | Banco BCI + un cliente + `SIMPLE` + una factura + diferencia `0` queda efectivamente contabilizado en Softland |

Ninguna de estas fuentes reemplaza a otra. En particular:
- `formato_importador_validado=true` (formato físico aceptado por el Capturador) **no implica**
  `conciliacion_bancaria_validada=true` (que un escenario contable específico termine
  efectivamente contabilizado) — son dos afirmaciones independientes, representadas por separado
  en `rules/softland-layouts.json`.
- `conciliacion_bancaria_validada=true` para `OFICIAL_61` está **escopeado exactamente** al
  escenario base confirmado (ver arriba) — no se extiende automáticamente a múltiples
  facturas/clientes, TRANSBANK, diferencias, otros bancos, proveedores ni cargos.

## Contratos de datos

- [`schemas/movimiento.schema.json`](schemas/movimiento.schema.json) — forma de `Movimiento` +
  `Asignacion` producida por `normalize.py`. Incluye `respaldo_diferencia` (`null` o
  `{tipo, referencia, verificado}`) y `Asignacion.fuente_respaldo` — representación mínima y
  estructurada de un respaldo Transbank ya verificado por un paso anterior; `validate.py` nunca
  abre ni comprueba ningún documento externo, solo confía en esta marca.
- [`schemas/resultado-validacion.schema.json`](schemas/resultado-validacion.schema.json) —
  contrato de salida de `validate.py`: `estado_motor`, `tipo_pago`, `motivos[]`, `advertencias[]`,
  `validaciones`, `montos`.
- [`schemas/aprobaciones.schema.json`](schemas/aprobaciones.schema.json) — contrato de
  persistencia interna de `approval.py` (`AprobacionLote` con `lote_id` + `decisiones[]`). Es un
  detalle de implementación, **no** una interfaz que Contabilidad edite manualmente.
- [`schemas/linea-softland.schema.json`](schemas/linea-softland.schema.json) — contrato de salida
  de `transform.py`: `LineaSoftland` con vista semántica + `campos_1_a_61` (las 61 posiciones
  oficiales). Todavía no es el archivo físico final.
- [`schemas/exportacion-softland.schema.json`](schemas/exportacion-softland.schema.json) — contrato
  de `rules/softland-layouts.json` (forma de un `PerfilLayout`).
- [`schemas/excel-layout.schema.json`](schemas/excel-layout.schema.json) — contrato de
  `rules/excel-layouts.json` (los perfiles de lectura de Excel que consume `read_excel.py`).

## Uso

```text
python scripts/read_excel.py <conciliacion.xlsx> --out movimientos_raw.json
python scripts/normalize.py movimientos_raw.json --out movimientos.json
python scripts/validate.py movimientos.json --out resultados_validacion.json
python scripts/transform.py movimientos.json resultados_validacion.json --preview --out preview.json
python scripts/approval.py preparar movimientos.json resultados_validacion.json <movimiento_id>
python scripts/approval.py decidir movimientos.json resultados_validacion.json <lote_id> <movimiento_id> APROBADO "<revisor>"
python scripts/transform.py movimientos.json resultados_validacion.json <lote_id> --out lineas_softland.json
python scripts/export_softland.py lineas_softland.json --out captura_generada.csv
```

`export_softland.py` usa el perfil `OFICIAL_61` por defecto (validado end-to-end); puede
indicarse otro con `--perfil OPERATIVO_62` (histórico, sin evidencia real de éxito, ver tabla de
perfiles arriba).

El Excel de entrada nunca se modifica: todos los scripts abren en modo lectura y solo escriben los
archivos JSON indicados en `--out` (o imprimen a stdout si se omite). `approval.py decidir`
persiste internamente en `aprobaciones-<lote_id>.json`; las decisiones son por lote/corrida, no un
histórico acumulativo global, y ese archivo no está pensado para edición manual.

## Requisitos

```text
pip install -r requirements.txt
```

(`openpyxl`, `pytest`).

## Reglas contables confirmadas (usadas por transform.py)

- **Línea Banco**: cuenta resuelta desde `rules/taxtic.json` (`10-01-003` para BCI en el MVP);
  Debe=`monto_abono`, Haber=0; Tipo Docto. Conciliación=`TB`; Nro. Docto. Conciliación=
  `Movimiento.numero_conciliacion` (columna `N°` del Excel — corresponde exactamente a la
  columna 18 oficial de Softland); Auxiliar/Tipo Documento/Nro
  Documento/fechas = `0` (no utilizados operacionalmente en esta línea). Glosa (dos variantes
  según cuántos clientes distintos hay en el movimiento):
  - **Un solo cliente** (todas las `Asignacion` comparten el mismo `rut_cliente`):
    `PAGO CLIENTE {NOMBRE_CLIENTE} F{FACTURAS}` (ej. `PAGO CLIENTE CLIENTE ABC F32007-33100`).
  - **Multicliente** (más de un `rut_cliente` distinto, ej. Transbank multi-RUT ya resuelto por
    respaldo): `PAGO CLIENTE F{FACTURAS}` — **sin ningún nombre de cliente** (ej.
    `PAGO CLIENTE F34053-34052-34008`). No se usa ningún separador de nombres porque
    simplemente no se incluyen.

  En ambos casos, `{FACTURAS}` concatena los folios en el orden de las `Asignacion` separados por
  `-` (ej. `F32007-33100`) — nunca se ordenan, deduplican, ni se interpretan como rango numérico.
- **Línea Cliente** (una por `Asignacion`, nunca un Banco repetido por factura): Cuenta=
  `10-02-001`; Debe=0, Haber=`monto_aplicado`; Auxiliar=`rut_cliente` ya normalizado (sin puntos
  ni guion), **sin dígito verificador** (regla confirmada por Contabilidad con evidencia real de
  Softland); Tipo Documento=`20`; Nro Documento=`numero_documento`; Fecha Emisión/Vencimiento=
  `fecha_pago` del Movimiento en `DD/MM/AAAA`; Glosa=`PAGO F {factura}` (pago normal) o
  `PAGO CLIENTES F {factura}` (Transbank).
- **Línea Diferencia Transbank** (solo si el movimiento ya fue validado `APTO` como Transbank
  respaldado con diferencia > 0): Cuenta=`10-04-001`; Debe=`diferencia`, Haber=0; Auxiliar=
  `96689310`; Tipo Documento/Nro Documento/Tipo y Nro Docto. Conciliación=0 (sin `TB`); Glosa fija
  `DIFERENCIA POR COBRO COMISION TRANSBANK`.

Ver [`rules/taxtic.json`](rules/taxtic.json) para los valores exactos.

## Limitaciones conocidas

- `normalize.py` no resuelve la atribución RUT-factura cuando una fila Transbank agrupa a varios
  clientes sin respaldo externo — queda marcada con `senales_revision`. `validate.py`/`approval.py`/
  `transform.py` ya saben representar, aprobar y transformar el caso cuando un paso futuro
  enriquece el `Movimiento` con `rut_cliente` y `fuente_respaldo` resueltos, pero **la experiencia
  de resolución/enriquecimiento del respaldo Transbank real (lectura de email/PDF/reporte) todavía
  no está diseñada**.
- El checksum de `ResultadoValidacion` (para invalidar una aprobación si el movimiento cambió
  después de validarse) queda fuera del MVP, tal como fue decidido explícitamente.
- **Historial de intentos reales de carga en Softland** (evidencia acumulada sobre un mismo
  movimiento de prueba):
  - Un primer grupo de intentos con el perfil `OPERATIVO_62` (hipótesis basada en `captura.csv`)
    **falló completamente** — errores sucesivos de "Graba el detalle de libro (S/N)" y luego de
    valores numéricos no válidos, con fallas de importación y excepciones internas. Se descartaron
    como causa el desplazamiento de columnas, el encoding, el relimitador/separador decimal/miles,
    y el CRLF, comparando bytes reales contra `captura.csv`; también se corrigió el relleno
    genérico y el tratamiento de Debe/Haber/Auxiliar no aplicables. Ninguna corrección resolvió el
    error numérico genérico.
  - **El hallazgo que reconcilió todo lo anterior**: se obtuvo (a) un archivo de carga real
    **vigente** (`SOFTLAND.csv`, 42 filas de pago a proveedores, confirmado por el usuario que hoy
    funciona en Softland) y (b) la estructura oficial exportada directamente desde la pantalla
    "Estructura Arch." de Softland (PDF, 91 columnas documentadas para "Captura de Movimientos
    Mensuales"). Ambos coinciden entre sí, campo a campo, en una estructura de **61 columnas** —
    completamente distinta de lo que `OPERATIVO_62` asumía: delimitador **`;`** (no `,`), **BOM UTF-8**
    (no sin BOM), **sin campo final vacío** (no trailing comma), S/N de "Graba detalle libro"/
    "Documento Nulo" en las **posiciones 37/38** (no 40/41), fechas `DD/MM/AAAA` (coincide). Se
    reconfirmó además, de forma independiente, que el lado no usado de Debe/Haber y el Auxiliar
    cuando no aplica son siempre vacíos — y se descubrió que **`Documento Nulo` es literal `"N"`**
    (nunca vacío).
  - **`OFICIAL_61` pasa a ser el perfil por defecto**, respaldado por esta evidencia real directa
    (`formato_importador_validado: true`). **`OPERATIVO_62` pierde esa marca**
    (`formato_importador_validado: false`): ninguno de sus intentos reales tuvo éxito, y su
    estructura física quedó contradicha. Se mantiene disponible solo por historial.
  - **`conciliacion_bancaria_validada` permanece `false`** en ambos perfiles mientras el único
    archivo real disponible era de pago a proveedores, no de conciliación bancaria. No se declaró
    ningún perfil "totalmente validado" hasta que una carga real de conciliación bancaria fue
    aceptada de punta a punta (ver más abajo).
  - **Primer archivo aceptado por Softland, con avisos de negocio**: un intento con el perfil
    `OFICIAL_61` corregido fue el primero **aceptado** por el capturador de Softland, con 5 avisos
    por atributo de cuenta. Confirmado por Contabilidad: `CLIENTE.Auxiliar` debe ser el **RUT sin
    dígito verificador** — el auxiliar configurado en Softland no incluye el DV (implementado vía
    un helper `_rut_sin_dv()` en `transform.py`, exclusivo para ese campo). Para los otros 4 avisos
    (`BANCO.Auxiliar`, `BANCO.Tipo de Documento`, `BANCO.Tipo de Documento de Referencia`,
    `CLIENTE.Documento de Conciliación Bancaria`) se probaron sucesivamente distintos valores
    (`"TB"`, luego vacío) hasta encontrar la combinación correcta:
    - `"TB"` resultó **confirmado bloqueante** en un intento real posterior.
    - Una auditoría del catálogo oficial reveló que cada "atributo" reportado por Softland es en
      realidad un **par Tipo+Nro** (Documento de Conciliación Bancaria = 17+18; Tipo Documento =
      20+21; Tipo Docto Referencia = 24+25) — un intento anterior solo vació la mitad "Tipo" de
      cada par, dejando la mitad "Nro" en el relleno genérico, por lo que nunca representó una
      ausencia real del atributo.
    - Al vaciar también las mitades "Nro", **confirmado en Softland real**: los 3 avisos de "Tipo
      de Documento"/"Tipo de Documento de Referencia" (Banco) y "Documento de Conciliación
      Bancaria" (Cliente) **desaparecieron**. Solo quedó el aviso de `BANCO.Auxiliar` (posición 19).
    - Al vaciar también la posición 19 de Banco, ese archivo (identificado internamente como V10)
      fue probado en Softland real y el área confirmó **"Pasó"**, sin observaciones de
      forma/estructura/atributos — el único inconveniente fue que la factura de prueba ya estaba
      contabilizada previamente (un hecho de negocio, no de formato).
      `OFICIAL_61.formato_importador_validado` queda **doblemente confirmado**: por la
      coincidencia estructural con un archivo real de otro contenido, y porque el propio Softland
      aceptó V10, generado por este plugin. `SOFTLAND_V10_PRUEBA.csv` queda **congelado como
      golden de formato real aceptado** — SHA-256
      `ce7eacf73f8acc8dc5d1095af2fec5e4b379ed0deb9b286bb640b30f61eb5eb1` (324 bytes). No modificar
      este archivo.
  - **Prueba end-to-end confirmada, `conciliacion_bancaria_validada=true` (escopeado)**:
    Contabilidad liberó el mismo documento de prueba (permitiendo recontabilizarlo) y se ejecutó
    el pipeline completo desde cero (`read_excel → normalize → validate → NUEVA aprobación humana
    → transform → cuadratura → export OFICIAL_61`), generando un archivo con formato físico
    idéntico al de V10. Contabilidad confirmó tras la carga real: **"está bien, procede a lo que
    sigue"** — la transacción quedó efectivamente contabilizada. `OFICIAL_61.conciliacion_bancaria_validada`
    pasa a `true`, **escopeado exclusivamente** a: banco BCI, abono de un cliente,
    `tipo_pago=SIMPLE`, una factura, diferencia `0`, cuentas `10-01-003`/`10-02-001`. **No se
    extiende** a múltiples facturas/clientes, TRANSBANK, diferencias, otros bancos, proveedores ni
    cargos — esos siguen sin evidencia productiva propia.
- `graba_detalle_libro='N'` sigue siendo una **hipótesis** para nuestro flujo (cobro/conciliación
  de cliente, sin detalle de libro que declarar): el archivo real usado como referencia de formato
  usa `'S'`, pero para un caso de negocio distinto (compras con detalle de libro real), por lo que
  no es evidencia a favor ni en contra para nuestro caso específico.
- Cada perfil declara explícitamente su propio `delimitador`, `con_bom` y `trailing_delimitador`
  en `rules/softland-layouts.json` — nada de esto está hardcodeado en `export_softland.py`.

## Versión

0.3.0 — lectura, normalización, validación, previsualización determinística de líneas contables,
aprobación humana, transformación a `LineaSoftland` y exportación CSV por perfiles
OFICIAL_61/OPERATIVO_62, con validación calendárica real de fechas y verificación determinista de
consistencia preview↔transform (`verificar_consistencia.py`) antes de exportar. Perfil `OFICIAL_61` validado
end-to-end en Softland real para el escenario base banco BCI + un cliente + SIMPLE + una factura +
diferencia 0. Alcance pendiente: extender la validación productiva a otros escenarios — múltiples
facturas/clientes, TRANSBANK, diferencias, otros bancos, proveedores, cargos.
