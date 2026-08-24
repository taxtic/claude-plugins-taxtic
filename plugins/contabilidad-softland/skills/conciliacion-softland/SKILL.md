---
name: conciliacion-softland
description: Procesa un Excel de conciliación bancaria BCI y genera un CSV compatible con la Captura de Movimientos Mensuales de Softland (perfil OFICIAL_61). Lee, normaliza, valida, requiere aprobación humana explícita por movimiento, transforma a líneas contables y exporta. Nunca aprueba por el usuario ni carga directamente en Softland.
---

**Idioma de respuesta:** siempre en español chileno. Terminología contable local. Solo cambiar de
idioma si el usuario lo pide explícitamente.

# Conciliación bancaria → Softland

Cuando el usuario invoca este skill (palabras gatillo: "concilia con Softland", "genera el CSV de
Softland", "procesa la conciliación bancaria"), aplica el flujo determinista descrito abajo.

## Principio obligatorio

> **La automatización propone, transforma y valida. La persona responsable aprueba. Softland
> contabiliza.**

Nunca:
- inventar cuentas contables, RUT, facturas, montos, asociaciones factura↔cliente o diferencias;
- aprobar un movimiento en nombre del usuario o Contabilidad;
- cargar o contabilizar directamente en Softland (la carga es siempre manual, dentro de Softland,
  hecha por una persona).

Si un dato requerido no está en el Excel o no puede derivarse determinísticamente de una regla ya
confirmada en `rules/`, **detente y pregunta** — no lo completes por inferencia ni "sentido común".

## Flujo (cada paso es un script standalone, ejecutado con `python`, no importado)

```
Excel de conciliación
  → read_excel.py         (lectura estructural, sin decidir negocio)
  → normalize.py          (Movimiento + Asignacion[] canónicos)
  → validate.py           (estado_motor: APTO / REVISION / ERROR)
  → transform.py --preview (LineaSoftland[] PREVISTAS -- exige solo APTO, nunca aprobación)
  → approval.py preparar --preview --out-texto (arma 03b_revision.json y el bloque de texto ya listo)
  → [PARADA OBLIGATORIA — mostrar 03c_revision.txt verbatim, esperar decisión literal]
  → approval.py decidir   (estado_humano: APROBADO / RECHAZADO, por movimiento)
  → si RECHAZADO: detener la corrida aquí (no continuar, no transformar, no exportar)
  → transform.py          (camino normal, LineaSoftland[]: BANCO + CLIENTE[] + Diferencia opcional)
  → verificar_consistencia.py (gate determinista preview vs transform; si falla, detenerse)
  → [verificación de cuadratura: sum(debe) == sum(haber)]
  → export_softland.py --perfil OFICIAL_61
  → [ENTREGA — el usuario carga el CSV manualmente en Softland]
```

### Precondición: entorno Python

Antes de ejecutar cualquier script de esta skill, comprobar:

```powershell
python --version
python -c "import openpyxl; print(openpyxl.__version__)"
```

Si cualquiera de los dos falla: **detenerse**, informar al usuario que Python o sus dependencias
no están disponibles en este entorno, y pedirle que lo resuelva. Nunca improvisar rutas de
instalación, buscar ejecutables alternativos por el sistema de archivos, ni construir comandos de
búsqueda extensos para "encontrar" un Python funcional.

### Windows/PowerShell: shell consistente

En Windows, usar **PowerShell de forma consistente durante toda la corrida** — no mezclar sintaxis
de otra shell dentro de la misma ejecución. PowerShell también usa variables con `$` (ej. `$WD`,
`$env:TEMP`), así que `$VAR` no es en sí mismo un indicio de Bash. Lo que sí es sintaxis de otra
shell y debe evitarse en PowerShell:
- `VAR="valor"` o `export VAR="valor"` (asignación estilo Bash) — usar `$WD = "valor"`.
- `mkdir -p` — usar `New-Item -ItemType Directory -Path $WD -Force`.
- `ls -la` — usar `Get-ChildItem` (o su alias `ls`, sin flags de Bash).
- `&&` para encadenar comandos — usar `;` o líneas separadas, o `if ($?) { ... }` si el segundo
  comando debe depender del éxito del primero.

**No ejecutar `Remove-Item`, `del`, `erase`, `rm`, `rmdir` ni ningún otro comando de borrado o
limpieza como parte de este flujo.** El directorio temporal de la corrida (`$WD`) no necesita
limpiarse durante la ejecución. No improvisar comandos que no sean estrictamente necesarios para el
pipeline documentado en esta sección.

### Una invocación de shell por etapa — nunca agrupar el pipeline en un solo comando

**Cada script de esta skill (`read_excel.py`, `normalize.py`, `validate.py`, `transform.py`,
`approval.py`, `verificar_consistencia.py`, `export_softland.py`) se ejecuta en su propia llamada de
herramienta de shell, una a la vez — nunca combinados en un único comando**, aunque en este documento
varios aparezcan uno debajo del otro dentro del mismo bloque de código de ejemplo. Ver uno debajo de
otro en la documentación no significa que deban pegarse juntos en una sola invocación real.

**Las variables de PowerShell/Bash (`$WD`, `$pluginDir`, o cualquier otra) NO persisten entre
llamadas de herramienta independientes — cada llamada arranca una sesión de shell nueva, sin memoria
de asignaciones anteriores.** Lo único que sí persiste entre llamadas es el **directorio de trabajo
(cwd)**: un `Set-Location` hecho en una llamada sigue vigente en la siguiente. Por lo tanto:
- **Nunca** asumir que `$WD` o `$pluginDir`, definidos en un comando, seguirán existiendo como
  variables en el comando siguiente — en una llamada nueva, esas variables simplemente no están
  definidas (`$null`), y cualquier ruta construida con ellas quedaría rota (ej. `\01_raw.json` en vez
  de la ruta real).
- La ruta del directorio temporal de la corrida se resuelve **una sola vez**, se registra como texto
  (ver "CLI exacta" abajo), y a partir de ahí se **repite como ruta literal** en cada comando
  siguiente — nunca como referencia a `$WD`.
- El único elemento del que sí se puede depender entre llamadas es el `Set-Location` a la raíz del
  plugin (ver más abajo) — por eso las rutas relativas `.\scripts\...` siguen funcionando en
  comandos posteriores sin tener que repetir la ruta absoluta del plugin cada vez.

En concreto:
- **No** unir `read_excel.py` + `normalize.py` + `validate.py` (+ `transform.py --preview`, etc.) en
  un mismo comando con `;` o saltos de línea dentro de una sola llamada de herramienta — cada uno es
  una llamada independiente.
- Mantener cada comando **corto**: una sola invocación de `python .\scripts\...` con sus argumentos,
  nada más. No envolver los comandos en bloques `try`/`catch`/`if` de manejo de errores adicionales,
  más allá de las comprobaciones `Test-Path` ya documentadas explícitamente en esta skill.
- **No crear `session.json` ni ningún otro archivo de estado auxiliar** para "recordar" rutas o
  progreso entre pasos — la ruta literal del directorio temporal, ya conocida como texto, es
  suficiente; no se necesita ningún mecanismo adicional de persistencia.
- No repetir encabezados, comentarios ni bloques de configuración en cada comando — cada invocación
  se limita a la línea de `python` correspondiente.
- Después de cada etapa, revisar su resultado (código de salida / mensaje impreso) antes de
  continuar — **detenerse inmediatamente** si una etapa falla, sin intentar encadenar ni recuperar
  automáticamente el resto del pipeline en el mismo comando.

Un comando de shell demasiado largo puede ser rechazado directamente por el entorno antes de
ejecutarse (por longitud) — la forma de evitarlo no es acortar el texto de un comando gigante, sino
no construirlo: un script, una llamada.

### Directorio de ejecución: raíz del plugin

Todos los comandos `.\scripts\...` deben ejecutarse desde la **raíz del plugin**
`contabilidad-softland` — el directorio que contiene `scripts\`, `rules\`, `schemas\` y `skills\`.
La carpeta `skills\conciliacion-softland\` (donde vive este `SKILL.md`) **no** es el directorio de
ejecución de los scripts, solo contiene la documentación de la skill.

Si se conoce la ruta de la carpeta que contiene este `SKILL.md`, la raíz del plugin está exactamente
dos niveles arriba (`skills\conciliacion-softland\` → `..\..`).

```powershell
$pluginDir = <raíz de contabilidad-softland resuelta para esta corrida>   # no hardcodear una ruta fija
Set-Location $pluginDir

if (-not (Test-Path "$pluginDir\scripts\read_excel.py")) { <detenerse aquí> }
if (-not (Test-Path "$pluginDir\rules\taxtic.json")) { <detenerse aquí> }
```

Ambas comprobaciones deben devolver `True` antes de continuar con cualquier otro paso. Si
`$pluginDir` no se puede resolver de forma inequívoca para esta corrida: **detenerse**, informar al
usuario y pedirle la ruta — nunca buscar rutas arbitrariamente por el sistema de archivos, nunca
ejecutar desde `skills\conciliacion-softland\`, y nunca improvisar otra ubicación. No existe una
ruta de Windows fija válida para todas las instalaciones — no hardcodear una ruta local específica
como regla general de esta skill.

Este `Set-Location` es intencional: es el único mecanismo del que la skill depende entre llamadas
de shell separadas (el directorio de trabajo persiste; las variables no — ver sección anterior). No
hace falta repetirlo en cada comando siguiente.

### CLI exacta (PowerShell)

Preparación del directorio de trabajo (una sola llamada). Dentro de **esta** llamada sí se puede usar
una variable (`$WD`) porque vive y se resuelve en el mismo proceso — lo que no persiste es esta
variable *hacia la siguiente llamada*. Por eso el paso final imprime la ruta ya resuelta: el valor
impreso (`<WD>`, un texto literal como `C:\Users\...\Temp\contabilidad-softland-20260824_114455`) es
lo que se copia, tal cual, dentro de cada comando posterior — nunca `$WD`:

```powershell
$WD = Join-Path $env:TEMP ("contabilidad-softland-" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $WD -Force | Out-Null
Write-Output $WD
```

A partir de aquí, **cada bloque siguiente es una llamada de herramienta separada** — nunca las
pegues todas en un mismo comando — y cada una usa `<WD>` como **texto literal** (la ruta impresa
arriba), nunca como `$WD`:

```powershell
python .\scripts\read_excel.py "C:\ruta\archivo.xlsx" --out "<WD>\01_raw.json"
```

```powershell
python .\scripts\normalize.py "<WD>\01_raw.json" --banco BCI --out "<WD>\02_normalizado.json"
```

```powershell
python .\scripts\validate.py "<WD>\02_normalizado.json" --out "<WD>\03_validado.json"
```

```powershell
python .\scripts\transform.py "<WD>\02_normalizado.json" "<WD>\03_validado.json" --preview --out "<WD>\04_preview.json"
```

```powershell
python .\scripts\approval.py preparar "<WD>\02_normalizado.json" "<WD>\03_validado.json" <movimiento_id> --preview "<WD>\04_preview.json" --out "<WD>\03b_revision.json" --out-texto "<WD>\03c_revision.txt"
```

`transform.py --preview` es la **única** fuente de las líneas contables (cuenta, Debe, Haber, glosa,
auxiliar, líneas de diferencia). `approval.py preparar --preview --out-texto` hace dos cosas: incorpora
esas líneas, tal cual, en `03b_revision.json` (clave `lineas_previstas`), y además escribe en
`03c_revision.txt` el **bloque de texto ya armado y listo para mostrar** — ver "## 2. Parada
obligatoria antes de aprobar" para qué contiene exactamente. Si `--preview` falla (archivo sin la
estructura esperada, movimiento ausente, o cero líneas), `approval.py` **no genera ninguna salida**
(ni `03b_revision.json` ni `03c_revision.txt`) — detenerse aquí, informar el error tal cual lo
imprime el script, y no continuar.

**PARADA HUMANA OBLIGATORIA** — espera una respuesta **literal** `APROBADO` o `RECHAZADO` del
usuario; no la des por sentada ni la hardcodees en ningún ejemplo o script.

```powershell
python .\scripts\approval.py decidir "<WD>\02_normalizado.json" "<WD>\03_validado.json" <lote_id> <movimiento_id> <decision> "<revisor>" --directorio "<WD>"
```

Si `<decision>` fue `RECHAZADO`: **detener la corrida aquí**. No ejecutar `transform.py` (camino
normal) ni `export_softland.py` para este movimiento.

Si `<decision>` fue `APROBADO`, continuar:

```powershell
python .\scripts\transform.py "<WD>\02_normalizado.json" "<WD>\03_validado.json" <lote_id> --directorio "<WD>" --out "<WD>\05_lineas.json"
```

**Verificación de consistencia preview → transform** (ver "### Consistencia preview → transform" en
la sección 2): antes de exportar, ejecutar el gate determinista —

```powershell
python .\scripts\verificar_consistencia.py "<WD>\04_preview.json" "<WD>\05_lineas.json" <movimiento_id>
```

Si el comando termina con código de salida distinto de `0`: **detenerse aquí, mostrar el mensaje de
error tal cual lo imprime el script (trae el campo/línea/valores exactos de la discrepancia), y no
ejecutar `export_softland.py`**. Si termina con código `0`, continuar:

```powershell
python .\scripts\export_softland.py "<WD>\05_lineas.json" --perfil OFICIAL_61 --out "<WD>\06_softland.csv"
```

Valores que nunca se hardcodean como si fueran de producción:
- `<WD>`: la ruta literal del directorio temporal, impresa una sola vez al inicio de la corrida (ver
  arriba) — se repite tal cual, como texto, en cada comando siguiente. Nunca se referencia como
  `$WD` fuera de la llamada donde se creó, porque esa variable no sobrevive a la siguiente llamada.
- `<movimiento_id>`: se lee del JSON de `normalize.py`/`validate.py` de esa corrida.
- `<lote_id>`: identificador técnico único de la corrida (ej. derivado del mismo sello de tiempo
  usado para `<WD>`) — se genera una vez por corrida y se **reutiliza exactamente igual, como texto
  literal,** en `approval.py decidir` y en `transform.py`. No se lee de ningún JSON intermedio: es un
  dato que la propia orquestación de la skill decide al iniciar la corrida, no algo que
  `read_excel.py`, `normalize.py` ni `validate.py` produzcan.
- `<revisor>`: identidad de quien aprueba/rechaza. Si la corrida tiene una identidad de usuario ya
  conocida en ese contexto, úsala; si no, **pregúntala explícitamente al usuario** antes de llamar
  `approval.py decidir`. Nunca se infiere del sistema operativo ni se inventa un valor de ejemplo.

### Reglas negativas de CLI (evitar errores de invocación)

- **`read_excel.py`**: el Excel es argumento **posicional** (no existe `--archivo`). No acepta
  `--banco` — ese flag no existe en este script.
- **`normalize.py`**: `raw_json` es posicional. `--banco` se usa aquí (no en `read_excel.py`).
- **`transform.py`**: `movimientos_json` y `resultados_json` son posicionales; `lote_id` es
  posicional **opcional** (`nargs="?"`) — solo se omite cuando se usa `--preview` (que no lee ni
  escribe `aprobaciones-<lote_id>.json`, así que `lote_id` no aplica). Sin `--preview`, `lote_id`
  sigue siendo obligatorio, igual que antes.
- **`export_softland.py`**: `lineas_json` es posicional. `--out` es **obligatorio** (falla sin él).
  Para este flujo, usar siempre `--perfil OFICIAL_61`.
- **`approval.py preparar`**: `--preview` es opcional, pero si se entrega y falla (estructura
  inválida, movimiento ausente, o cero líneas), el comando **no genera ninguna salida** — no hay
  fallback a `null`. `--out-texto` escribe el bloque de texto ya armado
  (`formatear_revision_humana()`) — para este flujo, úsalo siempre junto con `--preview`, y muestra
  ese archivo verbatim en vez de interpretar `03b_revision.json`.
- **`verificar_consistencia.py`**: recibe exactamente `preview_json transform_json movimiento_id`
  (posicionales, en ese orden — invertirlos produce un error explícito, no un falso positivo). No
  tiene `--out` ni ningún flag que genere archivos; su única salida es el código de retorno y un
  mensaje en stderr si falla. Solo verifica **un** `movimiento_id` por invocación, no un lote.

Ejecutar cada script con `--out <archivo>.json` (nunca importar los módulos entre sí, ni asumir
estado compartido en memoria) y encadenar los JSON intermedios del directorio de trabajo `<WD>`
(ruta literal, no variable — ver "Una invocación de shell por etapa" arriba) de esa corrida.

## 1. Estados — dos máquinas de estado independientes

**Motor** (`validate.py`, nunca lo decide una persona):
- `APTO` — cuadra, sin motivo de bloqueo.
- `REVISION` — requiere corrección humana antes de continuar (ej. RUT múltiple sin resolver).
- `ERROR` — dato faltante o inconsistente que impide procesar.

**Humano** (`approval.py`, nunca lo decide el motor):
- `PENDIENTE` (implícito: sin decisión registrada aún).
- `APROBADO` — una persona con responsabilidad contable confirmó explícitamente el movimiento.
- `RECHAZADO`.

`APTO != APROBADO`. Solo aplica decisión humana a un movimiento `APTO` — un `REVISION` o `ERROR`
nunca puede quedar `APROBADO` (debe corregirse y volver a pasar por `validate.py`).

**Solo `APTO` + `APROBADO` + cuadratura verificada puede llegar a `export_softland.py`.**

## 2. Parada obligatoria antes de aprobar

Después de `validate.py`, ejecuta **`transform.py --preview`** y luego `approval.py preparar
--preview` (ver bloque CLI arriba, en ese orden). `04_preview.json` (`transform.py --preview`) es la
**única fuente de verdad** de las líneas contables (`LineaSoftland[]`) — la skill **NO debe calcular,
reconstruir, inferir ni reinterpretar** cuentas, Debe, Haber, glosas, auxiliar, RUT sin DV, líneas de
diferencia ni ningún otro atributo Softland. `approval.py preparar --preview` ya se encarga de
incorporarlas, verbatim, al objeto de revisión bajo la clave `lineas_previstas` — nunca las leas ni
las reconstruyas por tu cuenta.

En particular, **prohibido**:
- usar `descripcion_banco` como glosa;
- seleccionar manualmente `glosas.banco.*`;
- seleccionar manualmente `glosas.cliente_*`;
- quitar manualmente el dígito verificador del RUT;
- calcular manualmente Debe/Haber;
- cualquier otra reconstrucción de reglas de `rules/taxtic.json` que `transform.py --preview` ya
  resolvió por su cuenta.

**`03c_revision.txt` (salida de `approval.py preparar --preview --out-texto`) es el bloque de
revisión YA ARMADO — la única acción de la skill en este paso es mostrarlo verbatim al usuario,
tal cual, dentro de un bloque de código.** Ese texto ya incluye `movimiento_id`, `fecha_pago`,
`banco`, `monto_abono`, `origen_pago`, `descripcion_banco`, `estado_motor`, `tipo_pago`,
`cuadratura_exacta`, `suma_asignaciones`, `diferencia`, `puede_aprobar`, los clientes (con el aviso
correcto si el nombre no viene informado), y cada línea contable prevista con `cuenta`, `debe`,
`haber`, `glosa`, `auxiliar` y los campos de documento — todo ya formateado por
`formatear_revision_humana()` en `approval.py`, sin que la skill tenga que decidir cómo presentarlo.

**Prohibido explícitamente** al llegar a este paso:
- abrir `03b_revision.json` con `ConvertFrom-Json` (ni con `python -c`, ni con ninguna otra
  herramienta) para reconstruir la presentación a partir del JSON;
- usar `Write-Host` en un bucle sobre `clientes`/`asignaciones`/`lineas_previstas` para armar la
  tabla o el resumen a mano;
- decidir en la conversación cómo formatear cuentas, Debe/Haber, glosas o auxiliares;
- construir cualquier presentación alternativa a la de `03c_revision.txt`.

Si por algún motivo `--out-texto` no se usó y solo existe `03b_revision.json`: **detenerse** y
volver a ejecutar `approval.py preparar` con `--out-texto` — no improvisar el formato a mano como
sustituto.

Espera una respuesta **literal** `APROBADO` o `RECHAZADO` del usuario antes de continuar — no la
asumas, no la hardcodees en ningún ejemplo o script como si fuera el único resultado posible. Antes
de esa respuesta explícita: no ejecutar `approval.py decidir`, `transform.py` (camino normal) ni
`export_softland.py`. Nunca reutilices una decisión de una corrida anterior para un movimiento
distinto o una nueva ejecución del mismo movimiento — cada aprobación es específica de esa corrida.

Si la respuesta es `RECHAZADO`: registrar `RECHAZADO` mediante `approval.py decidir`, detener el
flujo — no transformar (camino normal), no exportar.

Si la respuesta es `APROBADO`: registrar `APROBADO` mediante `approval.py decidir`, ejecutar
`transform.py` (camino normal) y, tras la verificación de consistencia (ver abajo), `export_softland.py`.

### No editorializar sobre datos ausentes

Al mostrar la revisión, si el nombre del cliente viene `null`: no afirmar ni insinuar que el cliente
existe en Softland, que está identificado por RUT, ni que la ausencia del nombre es "normal" —
ninguna fuente de la corrida (`02_normalizado.json`, `03_validado.json`, `03b_revision.json`) da
evidencia de eso. Limitar la advertencia exactamente a los hechos verificables en esas fuentes:
- `nombre_cliente` no viene en el Excel;
- no fue inferido desde la descripción bancaria (`n_cheque_transferencia`/`descripcion_banco`);
- si se aprueba, la glosa Banco se generará sin nombre del cliente (tal como ya lo muestra, verbatim,
  el bloque de `03c_revision.txt`).

### Verbatim obligatorio

El contenido completo de `03c_revision.txt` se muestra **carácter por carácter, exactamente como lo
escribió `formatear_revision_humana()`**, dentro de un bloque de código (nunca reformateado en una
tabla Markdown, ni resumido, ni re-tipeado). No aplicar `Trim()`, `TrimStart()`, `TrimEnd()`,
`-replace '\s+'`, normalización de espacios, concatenación manual, ni ningún reformateo — ni al
archivo completo, ni a ninguna línea o campo individual dentro de él. El motivo es el mismo que antes
(una glosa puede traer espacios consecutivos reales, ej. `PAGO CLIENTE  F34174` con nombre de cliente
vacío) — solo que ahora es responsabilidad de `approval.py`, nunca de la skill, decidir cómo se ve
ese texto.

### Consistencia preview → transform

Después de `APROBADO`, la skill **no vuelve a calcular ni a modificar** las líneas contables, y
**nunca compara `04_preview.json` contra `05_lineas.json` por su cuenta** — ni leyendo el JSON en
PowerShell, ni por inspección visual, ni de ninguna otra forma manual. Esa comparación la hace
exclusivamente `verificar_consistencia.py` (ver bloque CLI arriba): recibe `04_preview.json`,
`05_lineas.json` y el `movimiento_id`, y compara la estructura completa de cada `LineaSoftland` —
todos los campos, incluido `campos_1_a_61`, sin excepciones.

Si el script termina con código de salida distinto de `0`: **detenerse antes de exportar**, mostrar
al usuario el mensaje de error exacto que imprime el script (ya trae el movimiento, el campo y los
valores concretos que difieren) y **no generar un CSV para carga**. No intentar "corregir" ninguna de
las dos salidas manualmente — una discrepancia aquí indica un problema real que debe investigarse,
no algo que la skill deba resolver por su cuenta.

## 3. Reglas de negocio — siempre desde `rules/`, nunca hardcodeadas en la conversación

- `rules/taxtic.json` — cuentas contables, auxiliares fijos/variables, tipos de documento, glosas.
  El **Código Auxiliar de Cliente en Softland es el RUT normalizado SIN dígito verificador**
  (confirmado con evidencia real de Softland) — `transform.py` ya aplica esta regla, no
  la repitas manualmente.
- `rules/softland-layouts.json` — perfil de exportación físico. **`OFICIAL_61` es el perfil por
  defecto y el único validado end-to-end en Softland real** (ver alcance exacto abajo). No cambies
  a `OPERATIVO_62` sin que el usuario lo pida explícitamente — es un perfil histórico sin evidencia
  real de éxito.
- `rules/validation-rules.json` — patrones de normalización y campos esenciales.
- Un banco no configurado en `rules/taxtic.json` produce un error explícito
  (`BANCO_NO_CONFIGURADO`) — nunca asumas un banco por defecto.

## 4. Alcance real validado (no generalizar)

Confirmado con carga real en Softland:

- Formato físico del perfil `OFICIAL_61`: 61 columnas, delimitador `;`, BOM UTF-8, sin campo final
  vacío, CRLF, fechas `DD/MM/AAAA`.
- Escenario contable: banco BCI, abono de **un** cliente, `tipo_pago=SIMPLE`, **una** factura,
  diferencia `0`, cuentas `10-01-003` (Banco) / `10-02-001` (Cliente) — confirmado efectivamente
  contabilizado en Softland por Contabilidad.

**Sin evidencia productiva propia todavía** (no asumir que funcionan igual sin advertir al
usuario): múltiples facturas en un mismo movimiento, múltiples clientes (RUT distintos),
`TRANSBANK`/diferencias, otros bancos, proveedores, cargos. Si el Excel trae uno de estos casos,
adviértelo explícitamente antes de generar el CSV final.

## 5. Entrega final

El CSV generado por `export_softland.py` es el entregable — el usuario lo carga manualmente en
Softland. Nunca automatices ni simules esa carga. Si el usuario pide "cárgalo en Softland", explica
que esa acción es manual y fuera del alcance de este skill.

## Privacidad

Los archivos de conciliación contienen RUT, montos y nombres de clientes — información financiera
sensible. No la compartas fuera de la organización ni la incluyas en resúmenes que salgan del
contexto de esta conversación.
