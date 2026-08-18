# softland-conciliacion

Plugin para automatizar el procesamiento de conciliaciones bancarias de TAXTIC (banco BCI)
y generar movimientos compatibles con la Captura de Movimientos Mensuales de Softland.

Es un plugin **nuevo e independiente**: no reutiliza, modifica ni depende de
`contabilidad-conciliacion` ni de ningún otro plugin del marketplace.

## Estado actual: Fase 1 a 8.16 (validado end-to-end en Softland real para el escenario base)

El pipeline determinista implementado hasta ahora:

1. **`scripts/read_excel.py`** — lee el Excel de conciliacion fila por fila, sin interpretar
   significado de negocio. Detecta y separa filas fuera de alcance (CARGO, fila `Total`,
   filas de control/saldo, filas vacias, columnas huerfanas con datos) de los movimientos
   candidatos.
2. **`scripts/normalize.py`** — convierte cada movimiento candidato en un `Movimiento` con sus
   `Asignacion[]` canonicas: normaliza fecha, montos y RUT; detecta uno o varios RUT por fila;
   extrae el folio de cada asignacion conservando siempre el texto original; marca (sin decidir)
   los casos que requieren revision humana o contable posterior.
3. **`scripts/validate.py`** — toma cada `Movimiento` normalizado y produce un
   `ResultadoValidacion` **separado** (nunca modifica el `Movimiento`) con `estado_motor`
   (`APTO`/`REVISION`/`ERROR`). Aplica las reglas del MVP (cuadratura exacta, diferencia
   Transbank con respaldo estructurado, textos especiales, boletas, RUT multiple sin asociar)
   con precedencia `ERROR > REVISION > APTO`.
4. **`scripts/approval.py`** — capa de aprobacion humana entre `validate.py` y `transform.py`.
   `preparar_revision()` arma el objeto que una futura Skill mostrara al usuario (sin recalcular
   reglas); `registrar_decision()` valida y persiste una decision `APROBADO`/`RECHAZADO` por
   lote/corrida. La capa de decision humana **solo aplica a `APTO`**: ni `APROBADO` ni `RECHAZADO`
   pueden registrarse sobre un movimiento `REVISION` o `ERROR`.
5. **`scripts/transform.py`** — toma `Movimiento` + `ResultadoValidacion` + `DecisionHumana` y
   produce `LineaSoftland[]` (1 `BANCO` + N `CLIENTE` + 0/1 `DIFERENCIA_TRANSBANK`), **solo** para
   `estado_motor == "APTO"` **y** `estado_humano == "APROBADO"` — cualquier otra combinacion falla
   explicitamente, nunca se excluye en silencio. Cada linea incluye tanto la vista semantica
   (`cuenta`/`debe`/`haber`/`glosa`/...) como la vista posicional (`campos_1_a_61`, las 61
   posiciones oficiales de Softland). La cuenta del Banco se resuelve siempre desde
   `rules/taxtic.json`; un banco no configurado produce `BANCO_NO_CONFIGURADO`, nunca un fallback
   silencioso a BCI. Verifica `sum(debe) == sum(haber)` antes de devolver cualquier resultado.

6. **`scripts/export_softland.py`** — toma `LineaSoftland[]` ya transformadas (`APTO`+`APROBADO`,
   nunca reconstruye esa aprobacion) y las serializa al formato fisico de un **perfil de layout**
   (`rules/softland-layouts.json`). No decide cuentas, Debe/Haber, auxiliares ni glosas — solo
   convierte la forma semantica de `LineaSoftland` en una fila fisica y la escribe. Perfil por
   defecto: **`OFICIAL_61`** (ver más abajo). Vuelve a verificar `sum(debe) == sum(haber)` por
   `movimiento_id` como defensa redundante antes de escribir cualquier archivo, y escribe siempre
   de forma atomica (temporal + rename) para nunca dejar un CSV parcial ante un error.

**Confirmado con carga real en Softland** (Fase 8.8 a 8.16, ver "Limitaciones conocidas" para el
historial completo V1–V10):

- El **formato físico** del perfil `OFICIAL_61` (61 columnas, delimitador `;`, BOM UTF-8, sin campo
  final vacío, fechas `DD/MM/AAAA`) fue aceptado por el Capturador de Transacciones de Softland.
- El **escenario contable base** — banco BCI, abono de un cliente, `tipo_pago=SIMPLE`, una factura,
  diferencia `0`, cuentas `10-01-003`/`10-02-001` — fue confirmado por Contabilidad como
  efectivamente contabilizado de punta a punta en una prueba end-to-end real (Fase 8.16).

**Todavia NO existen / fuera de alcance de esta validación**:

- Ningún escenario más allá del descrito arriba tiene evidencia productiva propia: múltiples
  facturas, múltiples clientes, TRANSBANK, diferencias, otros bancos, proveedores, cargos.
- Agentes y hooks (el skill conversacional [`conciliacion-softland`](skills/conciliacion-softland/SKILL.md)
  ya existe, Fase 8.16).
- Registro en el marketplace del repositorio.
- Lectura automatica de documentos de respaldo Transbank (email/PDF/reporte) — hoy
  `respaldo_diferencia` y `fuente_respaldo` solo se completan si una fase futura o una
  resolucion humana guiada enriquece el `Movimiento` antes de `validate.py`.

## Por que no decide estados en normalize.py

El diseno de este plugin separa deliberadamente "normalizar datos" de "decidir su tratamiento
contable". `normalize.py` nunca asigna una cuenta Softland, nunca calcula Debe/Haber, y nunca
resuelve por heuristica a que RUT pertenece una factura cuando una fila trae varios RUT — solo
deja evidencia estructurada (`advertencias`, `senales_revision`, `errores_normalizacion`) para que
`validate.py` decida el `estado_motor`. A su vez, `estado_motor` y `estado_humano` (aprobacion)
son dos fuentes de datos completamente separadas: `APTO` no significa `APROBADO`, y un movimiento
en `REVISION` o `ERROR` nunca puede quedar `APROBADO` — `approval.py` lo rechaza explicitamente.

## Reglas de negocio centralizadas

- [`rules/taxtic.json`](rules/taxtic.json) — cuentas contables confirmadas, auxiliares fijos,
  plantillas de glosa y tolerancia monetaria.
- [`rules/softland-columns.json`](rules/softland-columns.json) — las 61 columnas oficiales de la
  Captura de Movimientos Mensuales de Softland (ficha 03-08-2026), sin inventar contenido. Refleja
  **exclusivamente** el PDF oficial (perfil `OFICIAL_61`); permanece intacto desde su creación.
- [`rules/validation-rules.json`](rules/validation-rules.json) — patrones de normalizacion
  (separador multivalor, textos no-factura, deteccion de boletas) y campos esenciales.
- [`rules/softland-layouts.json`](rules/softland-layouts.json) — **perfiles de layout físico**
  para `export_softland.py`, deliberadamente separado de `softland-columns.json`:
  - **`OFICIAL_61`** (perfil por defecto, Fase 8.8) — 61 columnas, delimitador `;`, BOM UTF-8,
    sin campo final vacío, fechas `DD/MM/AAAA`, refleja `softland-columns.json` (PDF oficial) para
    las columnas 1–61. `formato_importador_validado: true` (Fase 8.8: coincide campo a campo con
    un archivo de carga real vigente + la estructura oficial exportada de Softland; Fase 8.16: el
    propio Capturador de Transacciones aceptó realmente los archivos generados por este plugin) y
    `conciliacion_bancaria_validada: true` **escopeado** al escenario confirmado en Fase 8.16 (ver
    tabla de alcance más abajo y `_nota_estados_validacion` en el JSON).
  - **`OPERATIVO_62`** — hipótesis histórica (Fase 5–8.7) basada en `captura.csv`, un archivo real
    pero de **otro** contenido contable (compras). Contradicha en Fase 8.8 por evidencia más
    directa: la estructura real usa 61 columnas/`;`/BOM, no 62/`,`/sin BOM. Los 5 intentos reales
    con este perfil (V1–V5) fallaron. `formato_importador_validado: false`. Se mantiene en el
    código solo como referencia histórica — no se elimina sin necesidad, pero no debe usarse.

## Fuentes de verdad (no intercambiables)

| Categoría | Fuente | Qué define |
|---|---|---|
| Reglas contables | Confirmaciones de Contabilidad | Cuentas, auxiliares (RUT sin DV), glosas, reglas Transbank, Debe/Haber |
| Formato físico vigente | `SOFTLAND.csv` (carga real vigente) + estructura oficial "Estructura Arch." de Softland (Fase 8.8), y V6–V10 (cargas reales directas de este plugin, Fase 8.9–8.16) | 61 columnas, delimitador `;`, BOM UTF-8, sin campo final vacío, CRLF, fecha `DD/MM/AAAA`, S/N en posiciones 37/38 |
| Layout oficial | `estructura softland.pdf` / PDF "Estructura Arch." (columnas 1–61) | Significado y posición de las 61 columnas documentadas |
| Escenario contable validado | Prueba end-to-end confirmada por Contabilidad (Fase 8.16) | Banco BCI + un cliente + `SIMPLE` + una factura + diferencia `0` queda efectivamente contabilizado en Softland |

Ninguna de estas fuentes reemplaza a otra. En particular:
- `formato_importador_validado=true` (formato físico aceptado por el Capturador) **no implica**
  `conciliacion_bancaria_validada=true` (que un escenario contable específico termine
  efectivamente contabilizado) — son dos afirmaciones independientes, representadas por separado
  en `rules/softland-layouts.json`.
- `conciliacion_bancaria_validada=true` para `OFICIAL_61` está **escopeado exactamente** al
  escenario de Fase 8.16 (ver arriba) — no se extiende automáticamente a múltiples
  facturas/clientes, TRANSBANK, diferencias, otros bancos, proveedores ni cargos.

## Contratos de datos

- [`schemas/movimiento.schema.json`](schemas/movimiento.schema.json) — forma de `Movimiento` +
  `Asignacion` producida por `normalize.py`. Incluye `respaldo_diferencia` (`null` o
  `{tipo, referencia, verificado}`) y `Asignacion.fuente_respaldo` — representacion minima y
  estructurada de un respaldo Transbank ya verificado por una fase anterior; `validate.py` nunca
  abre ni comprueba ningun documento externo, solo confia en esta marca.
- [`schemas/resultado-validacion.schema.json`](schemas/resultado-validacion.schema.json) —
  contrato de salida de `validate.py`: `estado_motor`, `tipo_pago`, `motivos[]`, `advertencias[]`,
  `validaciones`, `montos`.
- [`schemas/aprobaciones.schema.json`](schemas/aprobaciones.schema.json) — contrato de
  persistencia interna de `approval.py` (`AprobacionLote` con `lote_id` + `decisiones[]`). Es un
  detalle de implementacion, **no** una interfaz que Contabilidad edite manualmente.
- [`schemas/linea-softland.schema.json`](schemas/linea-softland.schema.json) — contrato de salida
  de `transform.py`: `LineaSoftland` con vista semantica + `campos_1_a_61` (las 61 posiciones
  oficiales). Todavia no es el archivo fisico final.
- [`schemas/exportacion-softland.schema.json`](schemas/exportacion-softland.schema.json) — contrato
  de `rules/softland-layouts.json` (forma de un `PerfilLayout`).

## Uso

```
python scripts/read_excel.py <conciliacion.xlsx> --out movimientos_raw.json
python scripts/normalize.py movimientos_raw.json --out movimientos.json
python scripts/validate.py movimientos.json --out resultados_validacion.json
python scripts/approval.py preparar movimientos.json resultados_validacion.json <movimiento_id>
python scripts/approval.py decidir movimientos.json resultados_validacion.json <lote_id> <movimiento_id> APROBADO "<revisor>"
python scripts/transform.py movimientos.json resultados_validacion.json <lote_id> --out lineas_softland.json
python scripts/export_softland.py lineas_softland.json --out captura_generada.csv
```

`export_softland.py` usa el perfil `OFICIAL_61` por defecto (validado end-to-end, Fase 8.16); puede
indicarse otro con `--perfil OPERATIVO_62` (histórico, sin evidencia real de éxito, ver tabla de
perfiles arriba).

El Excel de entrada nunca se modifica: todos los scripts abren en modo lectura y solo escriben los
archivos JSON indicados en `--out` (o imprimen a stdout si se omite). `approval.py decidir`
persiste internamente en `aprobaciones-<lote_id>.json`; las decisiones son por lote/corrida, no un
historico acumulativo global, y ese archivo no esta pensado para edicion manual.

## Requisitos

```
pip install -r requirements.txt
```

(`openpyxl`, `pytest`).

## Reglas contables confirmadas (usadas por transform.py)

- **Linea Banco**: cuenta resuelta desde `rules/taxtic.json` (`10-01-003` para BCI en el MVP);
  Debe=`monto_abono`, Haber=0; Tipo Docto. Conciliacion=`TB`; Nro. Docto. Conciliacion=
  `Movimiento.numero_conciliacion` (columna `N°` del Excel — **confirmado en Fase 4** que
  corresponde exactamente a la columna 18 oficial de Softland); Auxiliar/Tipo Documento/Nro
  Documento/fechas = `0` (no utilizados operacionalmente en esta linea). Glosa (**confirmada en
  Fase 4.1**, dos variantes segun cuantos clientes distintos hay en el movimiento):
  - **Un solo cliente** (todas las `Asignacion` comparten el mismo `rut_cliente`):
    `PAGO CLIENTE {NOMBRE_CLIENTE} F{FACTURAS}` (ej. `PAGO CLIENTE CLIENTE ABC F32007-33100`).
  - **Multicliente** (mas de un `rut_cliente` distinto, ej. Transbank multi-RUT ya resuelto por
    respaldo): `PAGO CLIENTE F{FACTURAS}` — **sin ningun nombre de cliente** (ej.
    `PAGO CLIENTE F34053-34052-34008`). No se usa ningun separador de nombres porque
    simplemente no se incluyen.

  En ambos casos, `{FACTURAS}` concatena los folios en el orden de las `Asignacion` separados por
  `-` (ej. `F32007-33100`) — nunca se ordenan, deduplican, ni se interpretan como rango numerico.
- **Linea Cliente** (una por `Asignacion`, nunca un Banco repetido por factura): Cuenta=
  `10-02-001`; Debe=0, Haber=`monto_aplicado`; Auxiliar=`rut_cliente` ya normalizado (sin puntos
  ni guion); Tipo Documento=`20`; Nro Documento=`numero_documento`; Fecha Emision/Vencimiento=
  `fecha_pago` del Movimiento en `DD/MM/AAAA`; Glosa=`PAGO F {factura}` (pago normal) o
  `PAGO CLIENTES F {factura}` (Transbank).
- **Linea Diferencia Transbank** (solo si el movimiento ya fue validado `APTO` como Transbank
  respaldado con diferencia > 0): Cuenta=`10-04-001`; Debe=`diferencia`, Haber=0; Auxiliar=
  `96689310`; Tipo Documento/Nro Documento/Tipo y Nro Docto. Conciliacion=0 (sin `TB`); Glosa fija
  `DIFERENCIA POR COBRO COMISION TRANSBANK`.

Ver [`rules/taxtic.json`](rules/taxtic.json) para los valores exactos.

## Limitaciones conocidas

- `normalize.py` no resuelve la atribucion RUT-factura cuando una fila Transbank agrupa a varios
  clientes sin respaldo externo — queda marcada con `senales_revision`. `validate.py`/`approval.py`/
  `transform.py` ya saben representar, aprobar y transformar el caso cuando una fase futura
  enriquece el `Movimiento` con `rut_cliente` y `fuente_respaldo` resueltos, pero **la experiencia
  de resolucion/enriquecimiento del respaldo Transbank real (lectura de email/PDF/reporte) todavia
  no esta disenada**.
- El checksum de `ResultadoValidacion` (para invalidar una aprobacion si el movimiento cambio
  despues de validarse) queda fuera del MVP, tal como fue decidido explicitamente.
- **Historial de intentos reales de carga en Softland, mov-000003 (Fase 8 a 8.8)**:
  - V1-V5 (perfil `OPERATIVO_62`, hipótesis basada en `captura.csv`): los 5 intentos reales
    **fallaron**. V1 (pos.40=`0`) y V2 (pos.40 vacía) fueron rechazados con
    `El registro 'Graba el detalle de libro (S/N)' es incorrecto`. V3 (pos.40=`N`) hizo desaparecer
    ese error, pero apareció uno nuevo: `Si usted incorporó valores no numéricos o muy grandes en un
    campo numérico`, con falla al importar el archivo temporal y una excepción interna
    (`NullReferenceException`). Fase 8.3 descartó desplazamiento de columnas y encoding como causa;
    Fase 8.4 corrigió el relleno genérico (V4); Fase 8.5 descartó delimitador/separador
    decimal/miles/CRLF comparando bytes reales contra `captura.csv`; Fase 8.6 encontró que el lado de
    Debe/Haber no usado y el Auxiliar cuando no aplica son siempre vacíos en `captura.csv`; Fase 8.7
    corrigió eso (V5). **V5 también falló**, con el mismo error numérico genérico.
  - **Fase 8.8 — hallazgo que reconcilia todo lo anterior**: se obtuvo (a) un archivo de carga real
    **vigente** (`SOFTLAND.csv`, 42 filas de pago a proveedores, confirmado por el usuario que hoy
    funciona en Softland) y (b) la estructura oficial exportada directamente desde la pantalla
    "Estructura Arch." de Softland (PDF, 91 columnas documentadas para "Captura de Movimientos
    Mensuales"). Ambos coinciden entre sí, campo a campo, en una estructura de **61 columnas** —
    completamente distinta de lo que `OPERATIVO_62` asumía: delimitador **`;`** (no `,`), **BOM UTF-8**
    (no sin BOM), **sin campo final vacío** (no trailing comma), S/N de "Graba detalle libro"/
    "Documento Nulo" en las **posiciones 37/38** (no 40/41), fechas `DD/MM/AAAA` (coincide). Se
    reconfirmó además, de forma independiente, que el lado no usado de Debe/Haber y el Auxiliar
    cuando no aplica son siempre vacíos — y se descubrió que **`Documento Nulo` es literal `"N"`**
    (nunca vacío, corrigiendo lo asumido hasta Fase 8.7).
  - **`OFICIAL_61` pasa a ser el perfil por defecto**, respaldado por esta evidencia real directa
    (`formato_importador_validado: true`). **`OPERATIVO_62` pierde esa marca**
    (`formato_importador_validado: false`): ninguno de sus 5 intentos reales tuvo éxito, y su
    estructura física quedó contradicha. Se mantiene disponible solo por historial.
  **`conciliacion_bancaria_validada` permanece `false`** en ambos perfiles — el archivo real de
  Fase 8.8 es de pago a proveedores, no de conciliación bancaria. No se declara ningún perfil
  "totalmente validado" hasta que una carga real de conciliación bancaria sea aceptada de punta a
  punta.
  - **Fase 8.9 — primer archivo ACEPTADO por Softland, con avisos de negocio**: V6 (perfil
    `OFICIAL_61` corregido) fue el primer intento **aceptado** por el capturador de Softland. El
    "Resultado Operaciones del Capturador de Transacciones" mostró 5 avisos por atributo de cuenta.
    Confirmado por Contabilidad: `CLIENTE.Auxiliar` debe ser el **RUT sin dígito verificador**
    (`77495793`, no `774957936`) — el auxiliar configurado en Softland no incluye el DV (implementado
    vía un nuevo helper `_rut_sin_dv()` en `transform.py`, exclusivo para ese campo). Para los otros 4
    avisos (`BANCO.Auxiliar`, `BANCO.Tipo de Documento`, `BANCO.Tipo de Documento de Referencia`,
    `CLIENTE.Documento de Conciliación Bancaria`) se probó inicialmente `"TB"` (posiciones 20/24 de
    Banco, 17 de Cliente) vía el nuevo mecanismo `valores_fijos_por_posicion` — **pero esto quedó
    contradicho en Fase 8.10** (ver abajo). `DIFERENCIA_TRANSBANK` y `OPERATIVO_62` no fueron tocados.
  - **Fase 8.10 — `"TB"` confirmado bloqueante; se prueba vacío**: al probar V7 real, el aviso de
    "cuenta que no maneja este atributo" persistió (solo cambió el valor mostrado de `"0"` a `"TB"`) y
    esta vez sí se confirmó que **bloqueaba el guardado** de la transacción. Se cambiaron
    `BANCO.20`/`BANCO.24`/`CLIENTE.17` de `"TB"` a **vacío** (`""`) como siguiente hipótesis — el único
    estado sin probar, pendiente de confirmación real (V8).
  - **Fase 8.11 — auditoría: V8 estaba incompleto**: el catálogo oficial (`rules/softland-columns.json`)
    confirma que cada "atributo" que Softland reporta es en realidad un **par Tipo+Nro**: Documento de
    Conciliación Bancaria = 17(Tipo)+18(Nro); Tipo Documento = 20(Tipo)+21(Nro); Tipo Docto Referencia
    = 24(Tipo)+25(Nro). V8 solo vació la mitad "Tipo" de cada par — la mitad "Nro" (`BANCO.21`,
    `BANCO.25`, `CLIENTE.18`) seguía en el relleno genérico `"0"` (esas posiciones no están mapeadas en
    absoluto para ese `tipo_linea`), por lo que V8 nunca representó una ausencia real del atributo.
    **Corrección de una afirmación previa**: `BANCO.Auxiliar` (posición 19, sin campo "Nro" pareado en
    el catálogo) semánticamente no se usa para la cuenta `10-01-003` (por eso `"0"` es el valor
    correcto según Contabilidad), pero el aviso de Softland para esa posición específica **nunca fue
    aislado ni confirmado como no bloqueante** — todos los intentos reales fallaron por las otras 3
    posiciones inconsistentes al mismo tiempo, así que no hay evidencia de que ese aviso por sí solo
    sea inofensivo.
  - **Fase 8.12 — V9: ausencia completa (Tipo+Nro) CONFIRMADA real**: se vaciaron también las mitades
    "Nro" (`BANCO.21`, `BANCO.25`, `CLIENTE.18`). **Confirmado en Softland real (Fase 8.13)**: los 3
    avisos de "Tipo de Documento"/"Tipo de Documento de Referencia" (Banco) y "Documento de
    Conciliación Bancaria" (Cliente) **desaparecieron**. Solo quedó el aviso de `BANCO.Auxiliar` (19).
  - **Fase 8.13 — V10: aislar BANCO.Auxiliar**: único aviso restante tras V9. Se vació también la
    posición 19 de Banco (`"0"` → `""`) como siguiente hipótesis — pendiente de confirmación real.
  - **Fase 8.14 — FORMATO V10 VALIDADO por Softland real; `conciliacion_bancaria_validada` sigue en
    `false`**: V10 fue probado en Softland real y el área confirmó **"Pasó"**, sin observaciones de
    forma/estructura/atributos — el único inconveniente fue que la factura de prueba ya estaba
    contabilizada previamente (un hecho de negocio, no de formato). `OFICIAL_61.formato_importador_validado`
    queda **doblemente confirmado**: Fase 8.8 (coincidencia estructural con un archivo real de otro
    contenido) + Fase 8.14 (el propio Softland aceptó V10, generado por este plugin, para
    mov-000003). No se declara `conciliacion_bancaria_validada=true`: falta demostrar que un
    documento **no contabilizado previamente** termina efectivamente registrado de punta a punta.
    El modelo ya distinguía estos dos estados desde Fase 6.1 (`formato_importador_validado` /
    `conciliacion_bancaria_validada`) — no se agregó ningún flag nuevo.
    `SOFTLAND_V10_PRUEBA.csv` queda **congelado como golden de formato real aceptado** — SHA-256
    `ce7eacf73f8acc8dc5d1095af2fec5e4b379ed0deb9b286bb640b30f61eb5eb1` (324 bytes), verificado
    idéntico en `scratchpad/fase8_13/` y en la copia de `Downloads`. No modificar este archivo.
  - **Fase 8.15/8.16 — PRUEBA END-TO-END CONFIRMADA, `conciliacion_bancaria_validada=true`
    (escopeado)**: Contabilidad liberó el mismo documento de prueba (permitiendo recontabilizarlo) y
    se ejecutó el pipeline completo desde cero (`read_excel → normalize → validate → NUEVA
    aprobación humana → transform → cuadratura → export OFICIAL_61`) para `mov-000003`, generando
    `SOFTLAND_PRUEBA_END_TO_END.csv` (formato físico idéntico al de V10). Contabilidad confirmó tras
    la carga real: **"está bien, procede a lo que sigue"** — la transacción quedó efectivamente
    contabilizada. `OFICIAL_61.conciliacion_bancaria_validada` pasa a `true`, **escopeado
    exclusivamente** a: banco BCI, abono de un cliente, `tipo_pago=SIMPLE`, una factura,
    diferencia `0`, cuentas `10-01-003`/`10-02-001`. **No se extiende** a múltiples
    facturas/clientes, TRANSBANK, diferencias, otros bancos, proveedores ni cargos — esos siguen
    sin evidencia productiva propia.
- `graba_detalle_libro='N'` sigue siendo una **hipótesis** para nuestro flujo (cobro/conciliación de
  cliente, sin detalle de libro que declarar): el archivo real de Fase 8.8 usa `'S'`, pero para un
  caso de negocio distinto (compras con detalle de libro real), por lo que no es evidencia a favor ni
  en contra para nuestro caso específico.
- Cada perfil declara ahora explícitamente su propio `delimitador`, `con_bom` y `trailing_delimitador`
  en `rules/softland-layouts.json` — nada de esto está hardcodeado en `export_softland.py`.

## Version

0.2.0 (Fase 1 a 8.16 — lectura, normalizacion, validacion, aprobacion humana, transformacion a
LineaSoftland y exportacion CSV por perfiles OFICIAL_61/OPERATIVO_62, con validacion calendarica
real de fechas. Perfil OFICIAL_61 validado end-to-end en Softland real para el escenario base
banco BCI + un cliente + SIMPLE + una factura + diferencia 0. Pendiente: extender la validacion
productiva a otros escenarios -- multiples facturas/clientes, TRANSBANK, diferencias, otros
bancos, proveedores, cargos.)
