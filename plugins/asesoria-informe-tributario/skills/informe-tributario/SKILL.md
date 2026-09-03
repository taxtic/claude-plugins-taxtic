---
name: informe-tributario
description: Genera un informe tributario chileno (F29, F22, balance, ficha, malla) en Word + Excel de marca TAXTIC. Orquesta parsers Python deterministas; ninguna cifra la genera la IA. Palabras gatillo — "informe tributario", "arma el informe del cliente", "análisis tributario", "informe F22/F29".
---

**Idioma de respuesta:** siempre español chileno. Terminología contable/tributaria local. Todo el output en español.

# Informe tributario (orquestador — dos fases)

Cuando el usuario invoca este skill, orquestas la generación del informe. **NO leas los PDFs tú**: los parsers Python extraen los datos de forma determinista y exacta. Tú coordinas y redactas prosa, **nunca cifras**.

## Privacidad (leer primero)

Los documentos traen datos tributarios reales (RUT, montos). Procesarlos está permitido según la configuración corporativa vigente de Taxtic. Para compartir el resultado fuera de la organización, anonimizar antes con `/anonimizar` (plugin `comun-anonimizacion`).

## Inputs

Una carpeta con los documentos del cliente: F29 (mensuales), F22 (anuales), balance (PDF), ficha (`Datos*.xlsx`), malla (`Malla*.xlsx`). Si no se especifica, asumir la carpeta actual. Si hay más de un cliente, preguntar a cuál se refiere antes de procesar.

## FASE 1 — Extracción determinista (un solo comando, SIN cifras tecleadas por vos)

El ensamblado es **100% determinista**: un script corre todos los parsers, reconcilia, arma las alertas y construye `datos.json` con el bloque `tokens`. Vos **NO** transcribís ni tecleás ningún valor — eso es lo que garantiza que ninguna cifra la invente el modelo.

1. **Ejecutar** con `Bash`:
   ```
   python scripts/ensamblar_datos.py "<carpeta_cliente>" --out datos.json
   ```
   Descubre F29/F22/balance/ficha/malla por patrón, corre cada parser, corre `reconciliar` y `alertas_deterministas`, y escribe `datos.json` con: `cliente`, `malla`, `f29[]`, `f22[]`, `balance`, `reconciliaciones`, `alertas_deterministas`, y el bloque plano **`tokens`** (`{ "<token>": {"valor": int, "archivo", "pagina", "texto_cercano"} }`, ej. `"f22.2026.843"`, `"balance.saldo_caja"`, `"f29.2026-05.077"`). Los valores del bloque `tokens` salen tal cual de los parsers.
   - Si falta `pdfplumber` para el balance → avisar `pip install -r requirements.txt`; el balance queda "sin información" y su reconciliación se omite.
   - Archivos que no parsean quedan como `NO_PROCESADO`; el resto sigue.
2. **Leer el resumen** que imprime el script (cuántos F29/F22, reconciliaciones que cuadran, alertas). **NO edites `datos.json` a mano** — es la fuente de verdad determinista; si tecleás un número ahí, rompés la garantía.

## FASE 2 — Síntesis (prosa, NUNCA cifras)

6. **Redactar prosa por sección** usando **placeholders** `{{token}}`, jamás números tecleados. Cada token debe existir como clave en el bloque `datos.tokens` construido en Fase 1, ej: `{{f22.2026.843}}`, `{{balance.saldo_caja}}`. Si necesitás un monto que no está como token, agregalo primero al bloque; nunca lo tecleés en la prosa. Secciones: ficha → malla → F22 comparativo → análisis F22 → cadena IVA F29 → PPM/retenciones/recargos → balance + conciliación → inconsistencias detectadas → alertas y oportunidades → resumen ejecutivo. Sección sin datos → "sin información".
7. **Análisis por régimen** según `datos.cliente.regimen` (14A→IDPC 27% RAI/SAC; 14D-3→12,5%; 14D-8 transparente; etc.).
8. **Generar los archivos por CLI (Bash):** escribir `secciones.json` con `Write` — lista de `{titulo, prosa, tabla}`. **Tanto la prosa como las celdas de tabla usan `{{token}}` para cualquier cifra; nunca tecleés un monto.** Las celdas que son etiquetas/texto (nombres de columna, "27%", años) van como texto normal. Luego ejecutar:
   ```
   python scripts/generar_informe.py datos.json secciones.json --docx informe.docx --xlsx anexo.xlsx
   ```
   Tanto la prosa como las celdas de tabla pasan por la guardia: si hay un monto CLP literal o un token inexistente, la CLI **aborta** con `MontoLiteral`/`TokenInexistente` — corregí usando un placeholder del bloque `tokens` y reintentá. Es la garantía anti-alucinación: ninguna cifra del informe puede provenir de algo que no sea un `token` verificado.

## Reportar al usuario

- Archivos generados (`informe.docx`, `anexo.xlsx`, `datos.json`).
- Reconciliaciones: cuáles cuadraron / cuáles no.
- Alertas deterministas levantadas.
- Documentos `NO_PROCESADO`.

## Limitaciones (v1)

- No lee escritura societaria (101 págs) ni Consulta Integral SII (PNG) — v2 con agentes de visión.
- Cruces aproximados (F29↔F22 ingresos, malla↔escritura) no incluidos; requieren validación de regla contable.
