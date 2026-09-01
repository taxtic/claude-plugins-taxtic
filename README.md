# claude-plugins-taxtic

Marketplace de plugins Claude Code para el equipo Taxtic (asesoría tributaria, contabilidad, RRHH).

## Instalación rápida

Desde Claude Code (App o CMD):

```
/plugin marketplace add taxtic/claude-plugins-taxtic
/plugin install <nombre-plugin>@plugins-taxtic
```

## Plugins disponibles

| Plugin | Para quién | Qué hace |
|---|---|---|
| `comun-anonimizacion` | Todos | Anonimiza RUTs / nombres / montos. Hook bloquea pegar RUT real. |
| `contabilidad-facturas` | Contabilidad | Extrae datos de PDFs de facturas a CSV. Clasifica cuentas. Audita coherencia. |
| `contabilidad-conciliacion` | Contabilidad | Conciliación bancaria CSV vs libro. Detecta anomalías. |
| `rrhh-planilla` | RRHH | Valida planilla remuneraciones. Compara mes vs mes. |
| `asesoria-normativa` | Asesoría | Resúmenes circulares SII. Checklist F29. Q&A normativa. |
| `contabilidad-rendiciones` | Contabilidad | Extrae rendiciones de caja chica (PDF) a CSV + Excel. Audita coherencia. |
| `asesoria-informe-tributario` | Asesoría | Informe tributario (F29, F22, balance, ficha, malla) en Word + Excel. Extracción determinista en Python; la IA no inventa cifras. |
| `contabilidad-softland` | Contabilidad | Conciliación bancaria BCI -> CSV de carga para Softland (Captura de Movimientos Mensuales, perfil OFICIAL_61). Aprobación humana obligatoria antes de exportar. |

## Soporte

Issues en este repo o canal interno Taxtic.

## Licencia

MIT.
