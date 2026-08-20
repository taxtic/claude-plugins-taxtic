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
  → read_excel.py       (lectura estructural, sin decidir negocio)
  → normalize.py        (Movimiento + Asignacion[] canónicos)
  → validate.py         (estado_motor: APTO / REVISION / ERROR)
  → [PARADA OBLIGATORIA — approval.py preparar + revisión humana, esperar decisión literal]
  → approval.py decidir (estado_humano: APROBADO / RECHAZADO, por movimiento)
  → si RECHAZADO: detener la corrida aquí (no continuar)
  → transform.py        (LineaSoftland[]: BANCO + CLIENTE[] + Diferencia opcional)
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

### CLI exacta (PowerShell)

```powershell
$WD = Join-Path $env:TEMP ("softland-conciliacion-" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Path $WD -Force | Out-Null

python .\scripts\read_excel.py "C:\ruta\archivo.xlsx" --out "$WD\01_raw.json"
python .\scripts\normalize.py "$WD\01_raw.json" --banco BCI --out "$WD\02_normalizado.json"
python .\scripts\validate.py "$WD\02_normalizado.json" --out "$WD\03_validado.json"
python .\scripts\approval.py preparar "$WD\02_normalizado.json" "$WD\03_validado.json" <movimiento_id> --out "$WD\03b_revision.json"
```

**PARADA HUMANA OBLIGATORIA** — ver "## 2. Parada obligatoria antes de aprobar" para qué mostrar
exactamente y qué le falta a `03b_revision.json`. Espera una respuesta **literal** `APROBADO` o
`RECHAZADO` del usuario; no la des por sentada ni la hardcodees en ningún ejemplo o script.

```powershell
python .\scripts\approval.py decidir "$WD\02_normalizado.json" "$WD\03_validado.json" <lote_id> <movimiento_id> <decision> "<revisor>" --directorio "$WD"
```

Si `<decision>` fue `RECHAZADO`: **detener la corrida aquí**. No ejecutar `transform.py` ni
`export_softland.py` para este movimiento.

Si `<decision>` fue `APROBADO`, continuar:

```powershell
python .\scripts\transform.py "$WD\02_normalizado.json" "$WD\03_validado.json" <lote_id> --directorio "$WD" --out "$WD\04_lineas.json"
python .\scripts\export_softland.py "$WD\04_lineas.json" --perfil OFICIAL_61 --out "$WD\05_softland.csv"
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

Después de `validate.py`, ejecuta `approval.py preparar` (ver bloque CLI arriba). Su JSON de salida
(`preparar_revision()`) trae: `movimiento_id`, `fecha_pago`, `monto_abono`, `origen_pago`,
`clientes` (pares rut/nombre), `asignaciones` completas, `suma_asignaciones`, `diferencia`,
`estado_motor`, `motivos`, `advertencias` y `puede_aprobar`. Úsalo como base — no reconstruyas esos
campos a mano.

**`approval.py preparar` NO trae todo lo que esta sección exige mostrar.** Verificado directamente
contra el código (`approval.py:_clientes`/`preparar_revision`): su salida **no incluye** el campo
`banco` del movimiento, **no incluye** un flag explícito de cuadratura (`validaciones.cuadratura_exacta`
vive en el JSON de `validate.py`, no se copia a `preparar_revision`), y **no incluye ninguna
previsualización de líneas contables** (`cuenta`/Debe/Haber/glosa) — `approval.py` nunca calcula
eso, por diseño ("nunca crea cuentas Softland, no genera Debe/Haber").

Por lo tanto, antes de ejecutar `approval.py decidir`, **muestra siempre** al usuario, combinando
todo lo anterior con lo que falta — cada dato con su fuente exacta, nunca inferido ni inventado:
- lo que ya trae `approval.py preparar` (`03b_revision.json`, arriba);
- `banco`: leer `movimientos[i].banco` en `02_normalizado.json`, donde `movimientos[i].movimiento_id`
  coincide con el `movimiento_id` de esta revisión — `preparar` no lo trae;
- la cuadratura explícita: leer `resultados[i].validaciones.cuadratura_exacta` en
  `03_validado.json`, donde `resultados[i].movimiento_id` coincide con el mismo `movimiento_id`;
- las líneas contables que se generarían (cuenta, Debe/Haber, glosa) — construidas únicamente a
  partir de `rules/taxtic.json` (`banco.cuenta` según `banco.codigo`, `cuentas.cliente`,
  `glosas.banco.un_cliente`/`glosas.banco.multicliente`, `glosas.cliente_normal`/`glosas.cliente_transbank`,
  regla de auxiliar sin DV) como previsualización determinística manual, **sin ejecutar
  `transform.py` todavía** (requiere una decisión humana ya registrada, y ningún script de este
  plugin genera hoy esa previsualización de forma automática).

Espera una respuesta **literal** `APROBADO` o `RECHAZADO` del usuario antes de continuar — no la
asumas, no la hardcodees en ningún ejemplo o script como si fuera el único resultado posible. Nunca
reutilices una decisión de una corrida anterior para un movimiento distinto o una nueva ejecución
del mismo movimiento — cada aprobación es específica de esa corrida.

## 3. Reglas de negocio — siempre desde `rules/`, nunca hardcodeadas en la conversación

- `rules/taxtic.json` — cuentas contables, auxiliares fijos/variables, tipos de documento, glosas.
  El **Código Auxiliar de Cliente en Softland es el RUT normalizado SIN dígito verificador**
  (confirmado con evidencia real de Softland, Fase 8.9) — `transform.py` ya aplica esta regla, no
  la repitas manualmente.
- `rules/softland-layouts.json` — perfil de exportación físico. **`OFICIAL_61` es el perfil por
  defecto y el único validado end-to-end en Softland real** (ver alcance exacto abajo). No cambies
  a `OPERATIVO_62` sin que el usuario lo pida explícitamente — es un perfil histórico sin evidencia
  real de éxito.
- `rules/validation-rules.json` — patrones de normalización y campos esenciales.
- Un banco no configurado en `rules/taxtic.json` produce un error explícito
  (`BANCO_NO_CONFIGURADO`) — nunca asumas un banco por defecto.

## 4. Alcance real validado (no generalizar)

Confirmado con carga real en Softland (Fase 8.8 a 8.16):

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
