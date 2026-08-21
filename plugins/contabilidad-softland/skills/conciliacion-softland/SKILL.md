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
  → approval.py preparar
  → [PARADA OBLIGATORIA — revisión humana con la preview determinística, esperar decisión literal]
  → approval.py decidir   (estado_humano: APROBADO / RECHAZADO, por movimiento)
  → si RECHAZADO: detener la corrida aquí (no continuar, no transformar, no exportar)
  → transform.py          (camino normal, LineaSoftland[]: BANCO + CLIENTE[] + Diferencia opcional)
  → [verificación: LineaSoftland[] del transform normal == las mostradas por --preview
     para el mismo movimiento; si difieren, detenerse antes de exportar]
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

### CLI exacta (PowerShell)

```powershell
$WD = Join-Path $env:TEMP ("contabilidad-softland-" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $WD -Force | Out-Null

python .\scripts\read_excel.py "C:\ruta\archivo.xlsx" --out "$WD\01_raw.json"
python .\scripts\normalize.py "$WD\01_raw.json" --banco BCI --out "$WD\02_normalizado.json"
python .\scripts\validate.py "$WD\02_normalizado.json" --out "$WD\03_validado.json"
python .\scripts\transform.py "$WD\02_normalizado.json" "$WD\03_validado.json" --preview --out "$WD\04_preview.json"
python .\scripts\approval.py preparar "$WD\02_normalizado.json" "$WD\03_validado.json" <movimiento_id> --out "$WD\03b_revision.json"
```

`transform.py --preview` es la **única** fuente de las líneas contables (cuenta, Debe, Haber, glosa,
auxiliar, líneas de diferencia) que se mostrarán en la revisión — ver "## 2. Parada obligatoria antes
de aprobar" para el detalle completo de qué mostrar y de dónde sale cada dato.

**PARADA HUMANA OBLIGATORIA** — espera una respuesta **literal** `APROBADO` o `RECHAZADO` del
usuario; no la des por sentada ni la hardcodees en ningún ejemplo o script.

```powershell
python .\scripts\approval.py decidir "$WD\02_normalizado.json" "$WD\03_validado.json" <lote_id> <movimiento_id> <decision> "<revisor>" --directorio "$WD"
```

Si `<decision>` fue `RECHAZADO`: **detener la corrida aquí**. No ejecutar `transform.py` (camino
normal) ni `export_softland.py` para este movimiento.

Si `<decision>` fue `APROBADO`, continuar:

```powershell
python .\scripts\transform.py "$WD\02_normalizado.json" "$WD\03_validado.json" <lote_id> --directorio "$WD" --out "$WD\05_lineas.json"
```

**Verificación de consistencia preview → transform** (ver "### Consistencia preview → transform" en
la sección 2): antes de exportar, comparar `transformados[<movimiento_id>]` en `05_lineas.json`
contra `previstos[<movimiento_id>]` en `04_preview.json` — estructura completa, no un subconjunto de
campos. Si difieren en algo: **detenerse aquí, informar la discrepancia y no ejecutar
`export_softland.py`**. Si son idénticas, continuar:

```powershell
python .\scripts\export_softland.py "$WD\05_lineas.json" --perfil OFICIAL_61 --out "$WD\06_softland.csv"
```

Valores que nunca se hardcodean como si fueran de producción:
- `<movimiento_id>`: se lee del JSON de `normalize.py`/`validate.py` de esa corrida.
- `<lote_id>`: identificador técnico único de la corrida (ej. derivado del mismo sello de tiempo
  usado para `$WD`) — se genera una vez por corrida y se **reutiliza exactamente igual** en
  `approval.py decidir` y en `transform.py`. No se lee de ningún JSON intermedio: es un dato que la
  propia orquestación de la skill decide al iniciar la corrida, no algo que `read_excel.py`,
  `normalize.py` ni `validate.py` produzcan.
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

Ejecutar cada script con `--out <archivo>.json` (nunca importar los módulos entre sí, ni asumir
estado compartido en memoria) y encadenar los JSON intermedios del directorio de trabajo `$WD` de
esa corrida.

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

Después de `validate.py`, ejecuta **`transform.py --preview`** y luego `approval.py preparar` (ver
bloque CLI arriba, en ese orden). `04_preview.json` (`transform.py --preview`) es la **única fuente
de verdad** de las líneas contables (`LineaSoftland[]`) que se mostrarán en la revisión — la skill
**NO debe calcular, reconstruir, inferir ni reinterpretar** cuentas, Debe, Haber, glosas, auxiliar,
RUT sin DV, líneas de diferencia ni ningún otro atributo Softland. Todo eso se copia **verbatim**
desde `04_preview.json`, en `previstos[<movimiento_id>]`.

En particular, **prohibido**:
- usar `descripcion_banco` como glosa;
- seleccionar manualmente `glosas.banco.*`;
- seleccionar manualmente `glosas.cliente_*`;
- quitar manualmente el dígito verificador del RUT;
- calcular manualmente Debe/Haber;
- cualquier otra reconstrucción de reglas de `rules/taxtic.json` que `transform.py --preview` ya
  resolvió por su cuenta.

`03b_revision.json` (`approval.py preparar`) trae: `movimiento_id`, `fecha_pago`, `monto_abono`,
`origen_pago`, `clientes` (pares rut/nombre), `asignaciones` completas, `suma_asignaciones`,
`diferencia`, `estado_motor`, `motivos`, `advertencias` y `puede_aprobar`. Úsalo como base para esos
campos — no los reconstruyas a mano. **No trae** `banco` ni un flag explícito de cuadratura, ni (por
diseño) ninguna línea contable — para eso existen `02_normalizado.json`/`03_validado.json` y, ahora,
`04_preview.json`.

Antes de ejecutar `approval.py decidir`, **muestra siempre** al usuario, cada dato con su fuente
exacta, nunca inferido ni inventado:
- `movimiento_id`, `fecha_pago`, `monto_abono`, `estado_motor`, datos de asignación/cliente — de
  `03b_revision.json`;
- `banco`: leer `movimientos[i].banco` en `02_normalizado.json`, donde `movimientos[i].movimiento_id`
  coincide con el `movimiento_id` de esta revisión;
- la cuadratura explícita: leer `resultados[i].validaciones.cuadratura_exacta` en
  `03_validado.json`, donde `resultados[i].movimiento_id` coincide con el mismo `movimiento_id`;
- las líneas contables **PREVISTAS**: leer `previstos[<movimiento_id>]` en `04_preview.json` —
  verbatim, sin alterar ningún valor (ver "Verbatim obligatorio" abajo). Por cada línea, mostrar
  según estén presentes en el JSON: `cuenta`, `debe`, `haber`, `glosa`, `auxiliar`, y los campos de
  documento relevantes (`tipo_documento`, `numero_documento`, fechas, `tipo_docto_conciliacion`,
  `numero_docto_conciliacion`). No inventar ni completar un campo que venga `null` o ausente.

Si `nombre_cliente` es `null` (en `clientes[].nombre` de `03b_revision.json` o en las asignaciones de
`04_preview.json`), indicar únicamente: *"El nombre del cliente no viene informado en el Excel y no
fue inferido."* No afirmar que Softland conoce al cliente por RUT, que existe en Softland, ni ninguna
otra explicación no demostrada por las fuentes de la corrida.

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
ninguna fuente de la corrida (`02_normalizado.json`, `03_validado.json`, `03b_revision.json`,
`04_preview.json`) da evidencia de eso. Limitar la advertencia exactamente a los hechos verificables
en esas fuentes:
- `nombre_cliente` no viene en el Excel;
- no fue inferido desde la descripción bancaria (`n_cheque_transferencia`/`descripcion_banco`);
- si se aprueba, la glosa Banco se generará sin nombre del cliente (tal como ya lo muestra, verbatim,
  `04_preview.json`).

### Verbatim obligatorio

Todo valor mostrado desde `04_preview.json` (glosas, y en general cualquier campo de texto) se
presenta **carácter por carácter, exactamente como viene en el JSON**. No aplicar `Trim()`,
`TrimStart()`, `TrimEnd()`, `-replace '\s+'`, normalización de espacios, concatenación manual, ni
ningún reformateo. Cuando una glosa pueda contener espacios consecutivos, mostrarla dentro de un
bloque de código (no una celda de tabla Markdown ni texto en línea) para que los espacios no se
colapsen visualmente al renderizar.

Por ejemplo, si `04_preview.json` trae `"glosa": "PAGO CLIENTE  F34174"` (con nombre de cliente
vacío), debe mostrarse exactamente así, con los dos espacios; si trae `"glosa": "PAGO F 34174"`,
igual, exactamente así. Estos son ejemplos ilustrativos de un caso ya observado, **no** valores
hardcodeados como regla de esta skill — la regla es siempre "verbatim desde `04_preview.json`",
cualquiera sea el contenido real de esa corrida.

### Consistencia preview → transform

Después de `APROBADO`, la skill **no vuelve a calcular ni a modificar** las líneas contables — el
`transform.py` normal (camino de la CLI, tras `approval.py decidir`) es la fuente real posterior a la
decisión humana. Antes de ejecutar `export_softland.py`, comparar `transformados[<movimiento_id>]`
en `05_lineas.json` (salida de ese `transform.py` normal) contra `previstos[<movimiento_id>]` en
`04_preview.json` — la estructura completa de cada `LineaSoftland`, no una comparación parcial. Esta
comparación debe ser una igualdad estructural exacta — todos los campos de cada `LineaSoftland`, en
el mismo orden — nunca por inspección visual del agente, interpretación semántica, normalización de
espacios, ni verificación de un subconjunto de campos representativos.

Si se detecta cualquier diferencia entre ambas para el mismo movimiento: **detenerse antes de
exportar**, informar la discrepancia exacta al usuario, y **no generar un CSV para carga**. No
intentar "corregir" ninguna de las dos salidas manualmente — una discrepancia aquí indica un problema
real que debe investigarse, no algo que la skill deba resolver por su cuenta.

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
