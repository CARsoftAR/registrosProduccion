# ABBAMAT - Sistema de Control y Auditoría de Producción (Taller)

Módulo 100% independiente y autónomo desarrollado para auditar el cumplimiento de la **jornada laboral teórica de 8,5 horas diarias (510 minutos)** frente a los registros reales de tiempos y órdenes de fabricación extraídos en directo de la base de datos del ERP (**EqualRP**).

---

## 🎯 Objetivos y Alcance del Módulo

1. **Aislamiento Total**: No interactúa ni comparte tablas, vistas ni código con los sistemas de presentismo, ausentismo ni fichadas de RRHH.
2. **Acceso de Solo Lectura al ERP**: Se conecta a la base de datos `EqualRP_Prod_Master` exclusivamente mediante consultas `SELECT` parametrizadas en modo solo lectura (`ReadOnly=1`) sobre las vistas y tablas de manufactura (`V_TMAN`, `TMAN014`, `TMAN054`).
3. **Cruce Teórico vs Real (Base: 8,5 horas diarias)**:
   - **Índice de Cumplimiento Diario (%)**: `(Tiempo Real Registrado / 8.5 hs) * 100`.
   - **Diferencial / Desvío**: Variación en horas y minutos frente a las 8,5 horas teóricas.
   - **Detección de Omisiones y Baches**:
     - **Omisión Total (0% de carga)**: Operarios de la nómina que no registraron ninguna actividad en la jornada.
     - **Baches Intradía**: Períodos sin actividad registrada superiores a la tolerancia configurada (15 min) entre tareas consecutivas, inicio demorado o cierre anticipado.
4. **Línea de Tiempo Visual (Gantt Intradía)**: Barra visual diaria (de 06:30 a 17:30) que mapea en colores cada orden trabajada y resalta los baches en franjas rayadas de advertencia.
5. **Estadísticas Consolidadas de Cobertura de Planta**:
   - Cobertura Global de Planta (%)
   - Tasa de Adopción / Carga de Datos en Taller (%)
   - Contador de Omisiones Críticas
   - Horas Totales Registradas vs Horas Teóricas
   - Rendimiento Técnico Global (Tiempo Cotizado Estándar vs Tiempo Real)
6. **Reporte Analítico en Excel**: Generador directo de archivos `.xlsx` ejecutivos con formato corporativo ABBAMAT, fórmulas y tres hojas (Resumen de Cumplimiento, Detalle de Tareas y Auditoría de Baches).

---

## 🚀 Puesta en Marcha

### Inicio Rápido (Un Clic)
Haga doble clic en el archivo:
```bat
iniciar_servidor.bat
```
El script aplicará migraciones locales, sincronizará la nómina de operarios desde el ERP y levantará el servidor web en:
👉 **`http://127.0.0.1:8080/`**

---

## 🌐 Estructura de Rutas y Navegación

| Ruta | Descripción |
| :--- | :--- |
| **`/control-produccion/`** | **Pantalla Principal de Control de Producción**: Matriz de cumplimiento vs 8,5 hs, semáforo de estados, baches y barra visual Gantt. |
| **`/`** | **Dashboard Ejecutivo**: Resumen de KPIs globales, gráficos interactivos Chart.js y ranking de cumplimiento. |
| **`/operario/<id_concepto>/`** | **Ficha Técnica Individual**: Desglose tarea por tarea de EqualRP, análisis de baches intradía y módulo de justificaciones. |
| **`/operarios/`** | **Nómina de Taller**: Activación/desactivación de operarios en auditoría y sincronización directa con `TMAN014`. |
| **`/parametros/`** | **Parámetros de Taller**: Ajuste de jornada teórica (8.5 hs) y tolerancia de baches. |
| **`/exportar-excel/`** | **Descarga de Reporte**: Exportación analítica en formato `.xlsx`. |
| **`/api/auditoria-dia/`** | **API JSON**: Endpoint para refresco dinámico y consultas asíncronas. |

---

## ⚙️ Configuración (`.env`)

```env
ERP_DB_HOST=192.168.88.12
ERP_DB_NAME=EqualRP_Prod_Master
ERP_DB_USER=tablero
ERP_DB_PASS=tablero2019
ERP_DB_DRIVER=SQL Server Native Client 11.0

JORNADA_TEORICA_HORAS=8.5
TOLERANCIA_BACHE_MINUTOS=15
HORA_INICIO_TURNO=07:00
HORA_FIN_TURNO=16:30
```
