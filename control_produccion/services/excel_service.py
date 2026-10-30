"""
Generador de Reportes Analíticos en Formato Excel (.xlsx) para Auditoría de Producción.
Diseño ejecutivo y corporativo para ABBAMAT con formato condicional y desglose por pestañas.
"""

import io
import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def generar_excel_auditoria_produccion(datos_auditoria):
    """
    Toma el resultado de auditar_jornada_produccion() y genera un archivo Excel en memoria.
    Retorna los bytes del archivo .xlsx listo para ser descargado en HTTP Response.
    """
    resumen = datos_auditoria['resumen']
    operarios = datos_auditoria['operarios']
    fecha_str = resumen['fecha_formateada']

    wb = openpyxl.Workbook()

    # Estilos ABBAMAT
    font_titulo = Font(name='Segoe UI', size=16, bold=True, color='1E293B')
    font_subtitulo = Font(name='Segoe UI', size=11, italic=True, color='64748B')
    font_header = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    font_bold = Font(name='Segoe UI', size=10, bold=True, color='1E293B')
    font_data = Font(name='Segoe UI', size=10, color='334155')
    font_kpi_label = Font(name='Segoe UI', size=9, bold=True, color='475569')
    font_kpi_val = Font(name='Segoe UI', size=14, bold=True, color='0F172A')

    fill_header_navy = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid')
    fill_header_slate = PatternFill(start_color='334155', end_color='334155', fill_type='solid')
    fill_kpi_card = PatternFill(start_color='F1F5F9', end_color='F1F5F9', fill_type='solid')

    fill_verde = PatternFill(start_color='DCFCE7', end_color='DCFCE7', fill_type='solid')
    fill_amarillo = PatternFill(start_color='FEF9C3', end_color='FEF9C3', fill_type='solid')
    fill_naranja = PatternFill(start_color='FFEDD5', end_color='FFEDD5', fill_type='solid')
    fill_rojo = PatternFill(start_color='FEE2E2', end_color='FEE2E2', fill_type='solid')

    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # -------------------------------------------------------------
    # PESTAÑA 1: Resumen de Auditoría y Cumplimiento de Jornada
    # -------------------------------------------------------------
    ws1 = wb.active
    ws1.title = "Control y Cumplimiento"
    ws1.views.sheetView[0].showGridLines = True

    # Encabezado
    ws1['A1'] = "ABBAMAT S.A. - CONTROL Y AUDITORÍA DE PRODUCCIÓN"
    ws1['A1'].font = font_titulo
    ws1['A2'] = f"Jornada Auditada: {fecha_str} | Base Teórica: {resumen['jornada_teorica_hs']} hs (510 min) | Extracción en Directo desde EqualRP"
    ws1['A2'].font = font_subtitulo

    # Tarjetas KPI (Filas 4 y 5)
    kpis = [
        ("COBERTURA GLOBAL", f"{resumen['indice_cobertura_global']}%"),
        ("TASA ADOPCIÓN", f"{resumen['tasa_adopcion_registro']}%"),
        ("HS REGISTRADAS", f"{resumen['horas_totales_registradas']} hs"),
        ("HS TEÓRICAS", f"{resumen['horas_totales_teoricas']} hs"),
        ("OPERARIOS REGISTRO", f"{resumen['operarios_con_registro']} / {resumen['total_nomina']}"),
        ("OMISIÓN TOTAL", f"{resumen['operarios_omision_total']}"),
        ("TOTAL BACHES", f"{resumen['total_baches_count']}"),
        ("REND. TÉCNICO", f"{resumen['rendimiento_tecnico_global']}%"),
    ]

    col = 1
    for label, val in kpis:
        cell_lbl = ws1.cell(row=4, column=col, value=label)
        cell_lbl.font = font_kpi_label
        cell_lbl.fill = fill_kpi_card
        cell_lbl.alignment = Alignment(horizontal='center', vertical='center')
        cell_lbl.border = border_thin

        cell_val = ws1.cell(row=5, column=col, value=val)
        cell_val.font = font_kpi_val
        cell_val.fill = fill_kpi_card
        cell_val.alignment = Alignment(horizontal='center', vertical='center')
        cell_val.border = border_thin
        col += 1

    # Tabla de Operarios (Fila 7)
    headers_ws1 = [
        "Legajo / ID", "Nombre Operario", "Puesto / Sector", "Cant. Reg.",
        "Horas Reales", "Horas Teóricas", "Desvío (hs)", "Cumplimiento (%)",
        "Rango Horario", "Hs Estándar", "Eficiencia (%)", "Baches", "Hs en Baches", "Estado Auditoría"
    ]

    row_idx = 7
    for col_idx, h in enumerate(headers_ws1, 1):
        cell = ws1.cell(row=row_idx, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header_navy
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = border_thin

    ws1.row_dimensions[row_idx].height = 26

    for op in operarios:
        row_idx += 1
        ws1.row_dimensions[row_idx].height = 20

        # Formato de celda por estado
        if op['estado'] == 'CUMPLIDO':
            fill_estado = fill_verde
        elif op['estado'] == 'PARCIAL':
            fill_estado = fill_amarillo
        elif op['estado'] == 'CRITICO':
            fill_estado = fill_naranja
        else:
            fill_estado = fill_rojo

        horas_teoricas_op = op.get('horas_teoricas', resumen.get('horas_teoricas_operario', resumen.get('jornada_teorica_hs', 8.5)))
        primer_h = op.get('primer_registro', '--:--')
        ultimo_h = op.get('ultimo_registro', '--:--')

        valores = [
            op['id_concepto'],
            op['nombre'],
            op['puesto'],
            op['cantidad_registros'],
            op['horas_reales'],
            horas_teoricas_op,
            op['desvio_horas'],
            f"{op['indice_cumplimiento']}%",
            f"{primer_h} - {ultimo_h}",
            op['horas_std'],
            f"{op['eficiencia_tecnica']}%",
            op['cantidad_baches'],
            op['horas_en_baches'],
            op['estado_label']
        ]

        for col_idx, val in enumerate(valores, 1):
            cell = ws1.cell(row=row_idx, column=col_idx, value=val)
            cell.font = font_data
            cell.border = border_thin

            # Alineación
            if col_idx in [1, 4, 8, 9, 12, 14]:
                cell.alignment = Alignment(horizontal='center', vertical='center')
            elif col_idx in [5, 6, 7, 10, 11, 13]:
                cell.alignment = Alignment(horizontal='right', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='left', vertical='center')

            # Resaltar la columna de cumplimiento y estado
            if col_idx in [8, 14]:
                cell.fill = fill_estado
                cell.font = font_bold

    # -------------------------------------------------------------
    # PESTAÑA 2: Detalle de Tareas de Producción
    # -------------------------------------------------------------
    ws2 = wb.create_sheet(title="Detalle de Tareas")
    ws2.views.sheetView[0].showGridLines = True

    headers_ws2 = [
        "Legajo", "Operario", "ID Orden", "Artículo", "Descripción Artículo",
        "Operación", "Máquina", "Inicio", "Fin", "Minutos", "Horas", "Piezas", "Std (Hs)", "Observaciones"
    ]

    ws2['A1'] = "REGISTROS DETALLADOS DE PRODUCCIÓN (EqualRP)"
    ws2['A1'].font = font_titulo
    ws2['A2'] = f"Fecha: {fecha_str} | Registros en taller"
    ws2['A2'].font = font_subtitulo

    row_idx2 = 4
    ws2.row_dimensions[row_idx2].height = 24
    for col_idx, h in enumerate(headers_ws2, 1):
        cell = ws2.cell(row=row_idx2, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header_slate
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border_thin

    for op in operarios:
        for r in op['registros']:
            row_idx2 += 1
            ws2.row_dimensions[row_idx2].height = 19
            fila = [
                op['id_concepto'],
                op['nombre'],
                r.get('id_orden'),
                r.get('articulo'),
                r.get('articulo_desc'),
                r.get('operacion'),
                r.get('maquina'),
                r.get('hora_inicio_str'),
                r.get('hora_fin_str'),
                r.get('tiempo_minutos'),
                r.get('tiempo_horas'),
                r.get('cantidad_producida'),
                r.get('tiempo_cotizado'),
                r.get('observaciones')
            ]
            for col_idx, val in enumerate(fila, 1):
                cell = ws2.cell(row=row_idx2, column=col_idx, value=val)
                cell.font = font_data
                cell.border = border_thin
                if col_idx in [1, 3, 7, 8, 9]:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                elif col_idx in [10, 11, 12, 13]:
                    cell.alignment = Alignment(horizontal='right', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='left', vertical='center')

    # -------------------------------------------------------------
    # PESTAÑA 3: Baches y Omisiones Auditadas
    # -------------------------------------------------------------
    ws3 = wb.create_sheet(title="Baches y Omisiones")
    ws3.views.sheetView[0].showGridLines = True

    headers_ws3 = [
        "Legajo", "Operario", "Tipo de Anomalía", "Hora Inicio", "Hora Fin", "Duración (min)", "Duración (hs)", "Detalle / Diagnóstico"
    ]

    ws3['A1'] = "AUDITORÍA DE BACHES U OMISIONES TEMPORALES"
    ws3['A1'].font = font_titulo
    ws3['A2'] = f"Fecha: {fecha_str} | Intervalos sin producción mayor a {resumen['tolerancia_bache_minutos']} min"
    ws3['A2'].font = font_subtitulo

    row_idx3 = 4
    ws3.row_dimensions[row_idx3].height = 24
    for col_idx, h in enumerate(headers_ws3, 1):
        cell = ws3.cell(row=row_idx3, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header_navy
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border_thin

    for op in operarios:
        for b in op['baches']:
            row_idx3 += 1
            ws3.row_dimensions[row_idx3].height = 19
            tipo_label = {
                'OMISION_TOTAL': 'OMISIÓN TOTAL DE JORNADA',
                'BACHE_INICIAL': 'INICIO DEMORADO',
                'INTRADIA': 'BACHE ENTRE TAREAS',
                'BACHE_FINAL': 'CIERRE ANTICIPADO'
            }.get(b.get('tipo'), b.get('tipo'))

            fila = [
                op['id_concepto'],
                op['nombre'],
                tipo_label,
                b.get('inicio'),
                b.get('fin'),
                b.get('duracion_minutos'),
                round(b.get('duracion_minutos', 0) / 60.0, 2),
                b.get('descripcion')
            ]

            fill_bache = fill_rojo if b.get('tipo') == 'OMISION_TOTAL' else fill_naranja

            for col_idx, val in enumerate(fila, 1):
                cell = ws3.cell(row=row_idx3, column=col_idx, value=val)
                cell.font = font_data
                cell.border = border_thin
                if col_idx in [1, 3, 4, 5]:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                elif col_idx in [6, 7]:
                    cell.alignment = Alignment(horizontal='right', vertical='center')
                else:
                    cell.alignment = Alignment(horizontal='left', vertical='center')

                if col_idx == 3:
                    cell.fill = fill_bache
                    cell.font = font_bold

    # Auto-ajuste de ancho de columnas para todas las hojas
    for ws in [ws1, ws2, ws3]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value or '')
                if '\n' in val_str:
                    val_str = max(val_str.split('\n'), key=len)
                if len(val_str) > max_len and cell.row > 2:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
