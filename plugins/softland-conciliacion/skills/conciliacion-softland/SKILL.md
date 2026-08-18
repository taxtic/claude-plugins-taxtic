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
  → [PARADA OBLIGATORIA — mostrar resumen y esperar decisión humana]
  → approval.py decidir (estado_humano: APROBADO / RECHAZADO, por movimiento)
  → transform.py        (LineaSoftland[]: BANCO + CLIENTE[] + Diferencia opcional)
  → [verificación de cuadratura: sum(debe) == sum(haber)]
  → export_softland.py --perfil OFICIAL_61
  → [ENTREGA — el usuario carga el CSV manualmente en Softland]
```

Ejecutar cada script con `--out <archivo>.json` (nunca importar los módulos entre sí, ni asumir
estado compartido en memoria) y encadenar los JSON intermedios de un directorio de trabajo nuevo
por corrida.

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

Después de `validate.py`, antes de ejecutar `approval.py decidir`, **muestra siempre** al usuario:
- el movimiento normalizado (fecha, banco, monto, RUT, cliente, factura(s), monto(s));
- el resultado de `validate.py` (`estado_motor`, motivos, cuadratura);
- las líneas contables que se generarían (cuenta, Debe/Haber, glosa) — como previsualización, sin
  ejecutar `transform.py` todavía (requiere una decisión humana ya registrada).

Espera una respuesta explícita tipo `APROBADO` o `RECHAZADO` del usuario antes de continuar. Nunca
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
