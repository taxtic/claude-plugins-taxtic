# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Plugin `contabilidad-rendiciones`: skill `/extractor-rendiciones` (PDFs de caja chica → CSV + Excel, con columna `Pagina`, hojas resumen usadas como control, filas `NO_PROCESADO` para PDFs ilegibles) y agente `auditor-rendiciones` (resumen global + CRÍTICO/ADVERTENCIA/INFO sobre el CSV).
- `contabilidad-rendiciones` v0.2.0: agente `extractor-rendicion-pdf` (procesa un PDF en contexto aislado, lectura página por página vía split con `pypdf`) y el skill `/extractor-rendiciones` pasa a orquestador (un agente por PDF). Evita saturar el contexto y el límite de 32 MB por request con escaneos pesados.
- Plugin `asesoria-informe-tributario`: skill `/informe-tributario` que genera informe .docx + anexo .xlsx desde F29/F22/balance/ficha/malla con extracción determinista en Python. Reconciliaciones exactas balance↔F22, alertas deterministas, trazabilidad por dato, garantía anti-alucinación por placeholders.
- Plugin `contabilidad-softland`: skill `/conciliacion-softland` que procesa un Excel de conciliación bancaria BCI y genera un CSV compatible con la Captura de Movimientos Mensuales de Softland (perfil OFICIAL_61). Pipeline determinista (lectura → normalización → validación → previsualización de líneas contables → aprobación humana obligatoria → transformación → exportación), donde la previsualización y la transformación final comparten la misma implementación y se comparan estructuralmente antes de exportar. Escenario banco BCI + un cliente + `SIMPLE` + una factura + diferencia `0` efectivamente validado end-to-end en Softland real; el resto de los escenarios (múltiples facturas/clientes, TRANSBANK, otros bancos) queda fuera de esa validación y no se asume equivalente.
- `contabilidad-softland` v0.3.0: script `verificar_consistencia.py` que reemplaza la comparación manual preview↔transform descrita en `SKILL.md` por un gate determinista — compara la estructura completa de cada `LineaSoftland` (incluido `campos_1_a_61`, sin excepciones) para un movimiento, y falla con código estable (`PREVIEW_INVALIDO`/`TRANSFORM_INVALIDO`/`MOVIMIENTO_NO_ENCONTRADO_EN_*`/`SIN_LINEAS_*`/`LINEAS_DIFERENTES`) ante archivos invertidos, movimientos ausentes, listas vacías o cualquier diferencia estructural, localizando la primera discrepancia (campo, número de línea en numeración 1-based, valor preview, valor transform) -- incluida la identificación explícita de la primera línea ausente de un lado cuando ambas listas tienen distinta cantidad de líneas. `approval.py preparar` incorpora un `--preview` opcional que agrega `lineas_previstas` (copiadas verbatim, sin recalcular) al objeto de revisión existente, sin duplicarlo; falla duro sin generar salida si el preview es inválido, el movimiento no está, o tiene cero líneas. `SKILL.md` ya no explica cómo comparar preview/transform a mano: solo invoca los scripts.

## [0.1.0] - 2026-05-25

### Added
- Marketplace `plugins-taxtic` con 5 plugins.
- Plugin `comun-anonimizacion`: skill `/anonimizar` (RUTs/nombres/montos) + hook UserPromptSubmit y PostToolUse para detección de RUTs reales (módulo 11) en prompts y archivos editados.
- Plugin `contabilidad-facturas`: skills `/extractor-facturas` (PDFs → CSV con campos estándar) y `/clasificar-cuentas` (PUC chileno mínimo); agente `auditor-facturas` (CRÍTICO/ADVERTENCIA/INFO sobre CSV extraído).
- Plugin `contabilidad-conciliacion` (MVP): skill `/conciliacion-bancaria` (cartola vs libro) y agente `detector-anomalias` (outliers estadísticos, descripciones genéricas).
- Plugin `rrhh-planilla` (MVP): skills `/validar-planilla` (estructura, aritmética, descuentos legales) y `/comparar-planillas` (mes vs mes con umbral).
- Plugin `asesoria-normativa` (MVP): skills `/resumen-circular-sii` (PDF/URL → resumen estructurado) y `/checklist-f29` (checklist pre-envío por giro y régimen); agente `consultor-tributario` (Q&A normativa chilena).
- 10 PDFs sintéticos de facturas en `assets/samples/facturas-octubre/` + script generador (`generador_facturas.py` con `reportlab`).

### Fixed
- Marketplace renombrado de `claude-plugins-taxtic` a `plugins-taxtic` (Claude Code rechaza prefijo "claude" por conflicto con namespace oficial Anthropic).
- Hook `comun-anonimizacion` ahora citea path `${CLAUDE_PLUGIN_ROOT}/hooks/detect_rut.py` para soportar usuarios Windows con espacios en el nombre.
