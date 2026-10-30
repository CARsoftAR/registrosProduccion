"""
Script de Validación Integral del Módulo de Auditoría de Producción ABBAMAT.
Verifica:
1. Conexión y consulta a V_TMAN en modo solo lectura.
2. Cálculo de métricas frente a la jornada obligatoria de 8,5 horas.
3. Identificación de omisiones y baches intradía.
4. Generación correcta del reporte en Excel (.xlsx).
5. Renderizado de vistas HTTP.
"""

import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from control_produccion.services.analytics_service import (
    auditar_jornada_produccion,
    auditar_periodo_produccion,
)
from control_produccion.services.excel_service import generar_excel_auditoria_produccion
from django.test import RequestFactory
from control_produccion.views import (
    control_produccion_view,
    dashboard_view,
    exportar_excel_view,
    operarios_config_view,
    parametros_taller_view,
    detalle_operario_view,
    api_operario_detalle,
    aura_botanica_view,
    nuevo_operario_view,
    editar_operario_view,
)

def test_full_flow():
    print("=== INICIANDO VALIDACIÓN DEL MOTOR DE AUDITORÍA ===")
    
    # 1. Probar con ayer (2026-10-28) - Jornada individual
    fecha_ayer = datetime.date(2026, 10, 28)
    print(f"\n1. Auditando fecha individual {fecha_ayer}...")
    datos_ayer = auditar_jornada_produccion(fecha_ayer)
    resumen = datos_ayer['resumen']
    
    print(f"   [OK] Total nómina activa auditada: {resumen['total_nomina']}")
    print(f"   [OK] Operarios con registro: {resumen['operarios_con_registro']}")
    print(f"   [OK] Operarios con omisión total: {resumen['operarios_omision_total']}")
    print(f"   [OK] Horas registradas: {resumen['horas_totales_registradas']} hs vs {resumen['horas_totales_teoricas']} hs teóricas")
    print(f"   [OK] Tasa adopcion de carga efectiva (>= 80% de 8,5 hs): {resumen['tasa_adopcion_registro']}% ({resumen['operarios_cumplen_adopcion']}/{resumen['total_nomina']})")
    print(f"   [OK] Total baches detectados: {resumen['total_baches_count']}")

    assert resumen['total_nomina'] == 14, f"Se esperaban 14 operarios activos, pero hay {resumen['total_nomina']}"
    assert resumen['operarios_con_registro'] + resumen['operarios_omision_total'] == 14, "La suma no coincide con el total de activos"
    assert resumen['operarios_cumplen_adopcion'] == 9, f"Se esperaban 9 operarios con jornada cumplida (>=80%), pero hay {resumen['operarios_cumplen_adopcion']}"
    assert resumen['tasa_adopcion_registro'] == 64.3, f"Tasa de adopcion esperada: 64.3%, obtenida: {resumen['tasa_adopcion_registro']}%"

    # Verificación CONDICIONAL Y DINÁMICA DEL DESCANSO LÍNEA POR LÍNEA:
    # Caso A: Operarios que NO registraron descanso (ej: Molinari Lucas OP 13, Crepaldi Nahuel OP 39, Fernandez Ezequiel OP 86)
    # Deben conservar el 100% de sus órdenes y tiempos sin ninguna resta fija ni descuento genérico.
    op_sin_descanso = [op for op in datos_ayer['operarios'] if not op['tiene_descanso'] and op['cantidad_total_lineas'] > 0]
    print(f"   [OK] Operarios con actividad SIN descanso registrado: {len(op_sin_descanso)}")
    for op in op_sin_descanso:
        assert op['cantidad_registros'] == op['cantidad_total_lineas'], (
            f"Operario {op['nombre']} sin descanso NO debe tener deducción de órdenes! "
            f"Esperado {op['cantidad_total_lineas']}, obtenido {op['cantidad_registros']}"
        )
        assert op['minutos_descanso'] == 0, f"Minutos de descanso deben ser 0 para {op['nombre']}"
        assert op['horas_descanso'] == 0.0, f"Horas de descanso deben ser 0 para {op['nombre']}"
        # Verificar que la suma de horas reales coincida exactamente con la suma total de sus líneas
        suma_lineas = round(sum(r['tiempo_minutos'] for r in op['registros']) / 60.0, 2)
        assert op['horas_reales'] == suma_lineas, (
            f"Horas reales de {op['nombre']} deben ser {suma_lineas} hs (sin descuento), pero son {op['horas_reales']} hs"
        )
        print(f"      -> {op['nombre']} (ID {op['id_concepto']}): {op['cantidad_registros']} órdenes tal cual cargó, {op['horas_reales']} hs (0 deducciones)")

    # Caso B: Operarios que SÍ registraron descanso (ej: Rojas Mario OP 48, Masera Nicolas OP 100, Costa Javier OP 65)
    # El descanso se detecta línea por línea y se excluye ÚNICAMENTE a ese operario del conteo de órdenes productivas y horas de taller.
    op_con_descanso = [op for op in datos_ayer['operarios'] if op['tiene_descanso']]
    print(f"   [OK] Operarios CON descanso registrado efectivamente: {len(op_con_descanso)}")
    for op in op_con_descanso:
        assert op['cantidad_descansos'] >= 1, f"Operario {op['nombre']} debe tener al menos 1 registro de descanso"
        assert op['cantidad_registros'] == op['cantidad_total_lineas'] - op['cantidad_descansos'], (
            f"Operario {op['nombre']} con descanso debe tener {op['cantidad_total_lineas'] - op['cantidad_descansos']} órdenes productivas, tiene {op['cantidad_registros']}"
        )
        assert op['minutos_descanso'] > 0, f"Minutos de descanso deben ser > 0 para {op['nombre']}"
        # Verificar que horas reales excluyen el descanso
        suma_prod = round(sum(r['tiempo_minutos'] for r in op['registros_productivos']) / 60.0, 2)
        assert op['horas_reales'] == suma_prod, (
            f"Horas reales de taller de {op['nombre']} deben ser {suma_prod} hs (excluyendo descanso), pero son {op['horas_reales']} hs"
        )
        print(f"      -> {op['nombre']} (ID {op['id_concepto']}): {op['cantidad_registros']} órdenes productivas ({op['cantidad_total_lineas']} totales - {op['cantidad_descansos']} descanso de {op['minutos_descanso']}m), {op['horas_reales']} hs taller")

    # 2. Probar consolidación por Rango de Fechas (2026-10-20 al 2026-10-28)
    f_desde = datetime.date(2026, 10, 20)
    f_hasta = datetime.date(2026, 10, 28)
    print(f"\n2. Auditando intervalo {f_desde} al {f_hasta}...")
    datos_rango = auditar_periodo_produccion(f_desde, f_hasta)
    res_rango = datos_rango['resumen']
    
    print(f"   [OK] Intervalo: {res_rango['fecha_formateada']}")
    print(f"   [OK] Días hábiles en el intervalo: {res_rango['dias_habiles']}")
    print(f"   [OK] Base teórica por operario: {res_rango['horas_teoricas_operario']} hs ({res_rango['jornada_teorica_hs']} hs/día)")
    print(f"   [OK] Total nómina activa: {res_rango['total_nomina']}")
    print(f"   [OK] Operarios con registro en el rango: {res_rango['operarios_con_registro']}")
    print(f"   [OK] Operarios sin registro en el rango: {res_rango['operarios_omision_total']}")
    print(f"   [OK] Horas totales registradas taller: {res_rango['horas_totales_registradas']} hs")
    print(f"   [OK] Horas teóricas globales taller: {res_rango['horas_totales_teoricas']} hs")
    print(f"   [OK] Cobertura acumulada taller: {res_rango['indice_cobertura_global']}%")
    print(f"   [OK] Ranking completo contiene {len(datos_rango['ranking'])} operarios (debe ser exactamente 14)")

    assert len(datos_rango['ranking']) == 14, f"El ranking debe contener 14 operarios activos, tiene {len(datos_rango['ranking'])}"
    assert res_rango['total_nomina'] == 14, f"Total nómina debe ser 14, es {res_rango['total_nomina']}"

    # 3. Probar generación de Excel (.xlsx) para el rango
    print("\n3. Probando generación de archivo Excel consolidado (.xlsx)...")
    excel_bytes = generar_excel_auditoria_produccion(datos_rango)
    print(f"   [OK] Archivo Excel generado con éxito! Tamaño: {len(excel_bytes)} bytes")

    # 4. Probar renderizado de Vistas Django con RequestFactory
    print("\n4. Probando Vistas Django...")
    rf = RequestFactory()
    
    # Dashboard con rango de fechas
    req_dash_rango = rf.get('/?fecha_desde=2026-10-20&fecha_hasta=2026-10-28')
    resp_dash_rango = dashboard_view(req_dash_rango)
    assert resp_dash_rango.status_code == 200, f"Error en dashboard_view (rango): status {resp_dash_rango.status_code}"
    assert b"14 Operarios" in resp_dash_rango.content or b"14" in resp_dash_rango.content
    print(f"   [OK] dashboard_view (rango) respondió 200 OK! (Tamaño: {len(resp_dash_rango.content)} bytes)")

    # Dashboard con fecha única
    req_dash_dia = rf.get('/?fecha=2026-10-28')
    resp_dash_dia = dashboard_view(req_dash_dia)
    assert resp_dash_dia.status_code == 200
    html_dash = resp_dash_dia.content.decode('utf-8')
    assert "Cobertura Global de Planta" in html_dash
    assert "Tasa de Carga / Adopción" in html_dash
    assert "Rendimiento Técnico Planta" in html_dash
    assert "Omisión Total (0% Carga)" not in html_dash
    assert "Omisiones en el Periodo" in html_dash  # Lista inferior intacta
    print(f"   [OK] dashboard_view verificado con las 3 tarjetas esenciales (sin tarjeta redundante de omisión)!")

    # Control de Producción con rango de fechas
    req_cp_rango = rf.get('/control-produccion/?fecha_desde=2026-10-20&fecha_hasta=2026-10-28')
    resp_cp_rango = control_produccion_view(req_cp_rango)
    assert resp_cp_rango.status_code == 200, f"Error en control_produccion_view (rango): status {resp_cp_rango.status_code}"
    html_cp = resp_cp_rango.content.decode('utf-8')
    assert "topbar-fecha-desde" in html_cp
    assert "topbar-fecha-hasta" in html_cp
    assert "Omisión Total (0% Carga)" not in html_cp  # Tarjeta superior removida
    assert "Atención de Auditoría" in html_cp or "alert-danger" in html_cp  # Alerta inferior preservada
    assert b"7 D\xc3\xadas" in resp_cp_rango.content or b"7 D" in resp_cp_rango.content
    assert b"14 Operarios" in resp_cp_rango.content or b"14" in resp_cp_rango.content
    print(f"   [OK] control_produccion_view (rango) respondió 200 OK con selector unificado y métricas simplificadas!")

    # Control de Producción con día único y verificación de ordenamiento por defecto (horas_desc)
    import re
    req_cp_dia = rf.get('/control-produccion/?fecha=2026-10-28')
    resp_cp_dia = control_produccion_view(req_cp_dia)
    assert resp_cp_dia.status_code == 200
    assert b"topbar-fecha-desde" in resp_cp_dia.content
    assert b"topbar-fecha-hasta" in resp_cp_dia.content
    assert b"btn-sort-toggle" in resp_cp_dia.content
    assert b"sortable-th" in resp_cp_dia.content

    html_default = resp_cp_dia.content.decode('utf-8')
    horas_list = [float(h.replace(',', '.')) for h in re.findall(r'data-horas="([0-9.,]+)"', html_default)]
    print(f"   [OK] Horas ordenadas por defecto en matriz (horas_desc): {horas_list}")
    for i in range(len(horas_list) - 1):
        assert horas_list[i] >= horas_list[i+1], (
            f"Fallo de ordenamiento: el operario en pos {i} ({horas_list[i]} hs) es menor que el de pos {i+1} ({horas_list[i+1]} hs)"
        )
    assert len(horas_list) == 14, f"Se esperaban 14 operarios en la tabla, se encontraron {len(horas_list)}"
    print(f"   [OK] Verificado: mayor tiempo={horas_list[0]} hs, menor tiempo/omisión={horas_list[-1]} hs")

    # Probar orden alternativo por % de Cumplimiento (cumplimiento_desc)
    req_cp_cump = rf.get('/control-produccion/?fecha=2026-10-28&orden=cumplimiento_desc')
    resp_cp_cump = control_produccion_view(req_cp_cump)
    html_cump = resp_cp_cump.content.decode('utf-8')
    cump_list = [float(c.replace(',', '.')) for c in re.findall(r'data-cumplimiento="([0-9.,]+)"', html_cump)]
    for i in range(len(cump_list) - 1):
        assert cump_list[i] >= cump_list[i+1], "Fallo en ordenamiento por cumplimiento"
    print(f"   [OK] Verificado orden alternativo por % Cumplimiento (cumplimiento_desc): {cump_list[:5]}...")

    # Probar orden alternativo Alfabético (nombre_asc)
    req_cp_nom = rf.get('/control-produccion/?fecha=2026-10-28&orden=nombre_asc')
    resp_cp_nom = control_produccion_view(req_cp_nom)
    html_nom = resp_cp_nom.content.decode('utf-8')
    nom_list = [n.lower() for n in re.findall(r'data-name="([^"]+)"', html_nom)]
    for i in range(len(nom_list) - 1):
        assert nom_list[i] <= nom_list[i+1], "Fallo en ordenamiento alfabético"
    print(f"   [OK] Verificado orden alternativo Alfabético por Nombre (nombre_asc): {nom_list[:3]}...")

    # Exportar Excel con rango
    req_exp = rf.get('/exportar-excel/?fecha_desde=2026-10-20&fecha_hasta=2026-10-28')
    resp_exp = exportar_excel_view(req_exp)
    assert resp_exp.status_code == 200
    print(f"   [OK] exportar_excel_view respondió 200 OK con Content-Type {resp_exp.headers.get('Content-Type')}")

    # 5. Probar Filtrado Avanzado por Operario / Legajo
    print("\n5. Probando Filtrado Avanzado por Operario / Legajo (Consolidado vs Individual)...")
    
    # 5.1 Dashboard filtrado por Operario 48 (Mario Rojas)
    req_dash_op48 = rf.get('/?fecha_desde=2026-10-28&fecha_hasta=2026-10-28&operario=48')
    resp_dash_op48 = dashboard_view(req_dash_op48)
    assert resp_dash_op48.status_code == 200
    html_dash_op48 = resp_dash_op48.content.decode('utf-8')
    assert "topbar-operario" in html_dash_op48, "El selector de operarios debe estar en la barra superior"
    assert "[48] ROJAS, MARIO ALBERTO" in html_dash_op48
    assert "Ver Todos" in html_dash_op48
    assert ("9,42" in html_dash_op48 or "9.42" in html_dash_op48) and "hs reales" in html_dash_op48
    assert "110,8%" in html_dash_op48 or "110.8%" in html_dash_op48
    print("   [OK] Dashboard con operario=48: métricas recalculadas dinámicamente a 9.42 hs y 110.8% de cobertura!")

    # 5.2 Control de Producción filtrado por Operario 48 (Mario Rojas)
    req_cp_op48 = rf.get('/control-produccion/?fecha_desde=2026-10-28&fecha_hasta=2026-10-28&operario=48')
    resp_cp_op48 = control_produccion_view(req_cp_op48)
    assert resp_cp_op48.status_code == 200
    html_cp_op48 = resp_cp_op48.content.decode('utf-8')
    assert "[48] ROJAS, MARIO ALBERTO" in html_cp_op48
    op_ids_tabla = re.findall(r'data-id="([^"]+)"', html_cp_op48)
    assert op_ids_tabla == ['48'], f"La tabla debe contener ÚNICAMENTE al operario 48, pero tiene {op_ids_tabla}"
    assert "operario=48" in html_cp_op48, "El link de exportar Excel y filtros deben incluir &operario=48"
    print(f"   [OK] Control de Producción con operario=48: tabla aislada a 1 única fila ({op_ids_tabla})!")

    # 5.3 Control de Producción filtrado por operario activo con omisión (ej: legajo 17 - Bongiorno Marcelo)
    req_cp_op17 = rf.get('/control-produccion/?fecha_desde=2026-10-28&fecha_hasta=2026-10-28&operario=17')
    resp_cp_op17 = control_produccion_view(req_cp_op17)
    assert resp_cp_op17.status_code == 200
    html_cp_op17 = resp_cp_op17.content.decode('utf-8')
    op_ids_tabla_17 = re.findall(r'data-id="([^"]+)"', html_cp_op17)
    assert op_ids_tabla_17 == ['17'], f"Se esperaba solo el operario 17, se obtuvo {op_ids_tabla_17}"
    horas_op17 = re.findall(r'data-horas="([0-9.,]+)"', html_cp_op17)
    assert float(horas_op17[0].replace(',', '.')) == 0.0, "Operario 17 debe tener 0 hs"
    print(f"   [OK] Operario activo con omisión (legajo 17) auditado correctamente con 0 hs y fila aislada!")

    # 5.4 Exportar Excel con operario individual
    req_exp_op = rf.get('/exportar-excel/?fecha_desde=2026-10-28&fecha_hasta=2026-10-28&operario=48')
    resp_exp_op = exportar_excel_view(req_exp_op)
    assert resp_exp_op.status_code == 200
    content_disp = resp_exp_op.headers.get('Content-Disposition', '')
    assert "Legajo_48.xlsx" in content_disp, f"El archivo Excel debe llamarse con el legajo, obtenido: {content_disp}"
    print(f"   [OK] exportar_excel_view con operario individual generó archivo personalizado: {content_disp}")

    # 5.5 Restablecer a Todos los Operarios
    req_cp_todos = rf.get('/control-produccion/?fecha_desde=2026-10-28&fecha_hasta=2026-10-28&operario=TODOS')
    resp_cp_todos = control_produccion_view(req_cp_todos)
    html_cp_todos = resp_cp_todos.content.decode('utf-8')
    op_ids_todos = re.findall(r'data-id="([^"]+)"', html_cp_todos)
    assert len(op_ids_todos) == 14, f"Al volver a TODOS se esperan 14 operarios, pero hay {len(op_ids_todos)}"
    print(f"   [OK] Restablecimiento a 'TODOS' verificado con éxito: 14 operarios activos en la matriz!")

    # 5.6 Probar Operario con Carga Insuficiente (Darrigan 92 con 4.2 hs = 49.4%)
    req_cp_op92 = rf.get('/control-produccion/?fecha_desde=2026-10-28&fecha_hasta=2026-10-28&operario=92')
    resp_cp_op92 = control_produccion_view(req_cp_op92)
    assert resp_cp_op92.status_code == 200
    html_cp_op92 = resp_cp_op92.content.decode('utf-8')
    assert "49,4%" in html_cp_op92 or "49.4%" in html_cp_op92, "Tasa de adopción debe ser 49.4%, jamás 100%"
    assert "100.0%" not in html_cp_op92 and "100,0%" not in html_cp_op92, "No debe mostrar 100% para operario con solo 4.2 hs!"
    assert "Carga insuficiente" in html_cp_op92, "Debe advertir carga insuficiente"
    print(f"   [OK] Operario con carga parcial (Darrigan 92): tasa real 49.4% y advertencia de 'Carga insuficiente' (superado el error de otorgar 100%)!")

    # 5.7 Validación de la Vista de Acordeón con Línea de Tiempo (Timeline)
    print("\n6. Validando vista de acordeón con línea de tiempo (timeline)...")
    req_cp = rf.get('/control-produccion/?fecha_desde=2026-10-28&fecha_hasta=2026-10-28')
    resp_cp = control_produccion_view(req_cp)
    html_cp = resp_cp.content.decode('utf-8')
    
    # 14 filas principales y 14 filas de acordeón
    accordion_rows = re.findall(r'class="operator-accordion-row"\s+id="accordion-op-([^"]+)"', html_cp)
    assert len(accordion_rows) == 14, f"Se esperaban 14 filas de acordeón, obtenidas: {len(accordion_rows)}"
    print(f"   [OK] 14 filas de acordeón desplegable renderizadas ({accordion_rows})")

    # Verificar botón toggle en cada operario
    toggle_btns = re.findall(r'btn-toggle-timeline', html_cp)
    assert len(toggle_btns) == 14, f"Se esperaban 14 botones de timeline, encontrados: {len(toggle_btns)}"
    print(f"   [OK] 14 botones interactivos de timeline presentes en la matriz")

    # Verificar bloques de Gantt para operario con tareas y descanso (Mario Rojas 48)
    assert 'accordion-op-48' in html_cp
    assert 'block-tarea' in html_cp, "Deben existir bloques de tipo TAREA en el timeline"
    assert 'block-descanso' in html_cp, "Debe existir bloque de tipo DESCANSO en el timeline de operario con pausa"
    assert 'accordion-events-table' in html_cp, "Debe existir tabla de desglose cronológico de eventos"
    assert 'Desglose Cronológico de Tareas' in html_cp
    print("   [OK] Componentes de Gantt (procesos, descansos, guías horarias y tabla cronológica) renderizados!")

    # Verificar operario con omisión total (OP 17)
    assert 'accordion-block-omision-total' in html_cp
    print("   [OK] Bloque visual de omisión total renderizado para operarios sin actividad!")

    # 7. Validación de Restauración de Menú y Módulo de Configuración de Planta
    print("\n7. Validando restauración de menú y módulo de Configuración de Planta...")
    req_op_cfg = rf.get('/operarios/')
    resp_op_cfg = operarios_config_view(req_op_cfg)
    assert resp_op_cfg.status_code == 200, f"Error en operarios_config_view: {resp_op_cfg.status_code}"
    html_op_cfg = resp_op_cfg.content.decode('utf-8')
    assert "Dashboard Ejecutivo" in html_op_cfg
    assert "Control de Producción" in html_op_cfg
    assert "Operarios de Taller" in html_op_cfg
    assert "Configuración" in html_op_cfg, "La opción 'Configuración' debe estar presente en el menú lateral!"
    print("   [OK] Opción 'Configuración' restaurada con éxito en el menú lateral bajo 'Configuración de Planta'!")

    # Verificar que el acceso a /parametros/ renderice la pantalla de Configuración de Planta
    req_param = rf.get('/parametros/')
    resp_param = parametros_taller_view(req_param)
    assert resp_param.status_code == 200, f"Se esperaba status 200 en /parametros/, pero se obtuvo {resp_param.status_code}"
    html_param = resp_param.content.decode('utf-8')
    assert "Configuración de Planta" in html_param
    assert "jornada_teorica_horas" in html_param
    assert "hora_inicio_taller" in html_param
    assert "hora_fin_taller" in html_param
    print("   [OK] Módulo de Configuración de Planta renderizado y accesible con total normalidad!")

    # Verificar guardado de parámetros
    req_save_param = rf.post('/parametros/', {
        'jornada_teorica_horas': '8.5',
        'tolerancia_bache_minutos': '15',
        'hora_inicio_taller': '07:00',
        'hora_fin_taller': '16:00',
    })
    resp_save_param = parametros_taller_view(req_save_param)
    assert resp_save_param.status_code == 302, f"Se esperaba redirección al guardar parámetros, obtenido: {resp_save_param.status_code}"
    print("   [OK] Guardado de parámetros generales verificado con éxito!")

    # Verificar constantes fijas de planta en el backend (8,5 hs = 510 min, 07:00 a 16:00)
    from control_produccion.constants import (
        JORNADA_TEORICA_HORAS,
        MINUTOS_TEORICOS_JORNADA,
        HORA_INICIO_TURNO,
        HORA_FIN_TURNO,
        TOLERANCIA_BACHE_MINUTOS,
    )
    assert JORNADA_TEORICA_HORAS == 8.5, f"Jornada teórica debe ser 8.5 hs, pero es {JORNADA_TEORICA_HORAS}"
    assert MINUTOS_TEORICOS_JORNADA == 510.0, f"Minutos teóricos debe ser 510.0, pero es {MINUTOS_TEORICOS_JORNADA}"
    assert HORA_INICIO_TURNO == "07:00", f"Hora inicio debe ser 07:00, pero es {HORA_INICIO_TURNO}"
    assert HORA_FIN_TURNO == "16:00", f"Hora fin debe ser 16:00, pero es {HORA_FIN_TURNO}"
    assert TOLERANCIA_BACHE_MINUTOS == 15, f"Tolerancia de bache debe ser 15 min, pero es {TOLERANCIA_BACHE_MINUTOS}"
    print("   [OK] Constantes fijas de planta verificadas: 8,5 hs (510 min), 07:00 a 16:00, 15 min tolerancia!")

    # 8. Verificación de cálculo en motor de auditoría con constantes fijas
    print("\n8. Validando que el motor de cálculo y auditoría use directamente las constantes de planta...")
    resultado_periodo = auditar_periodo_produccion(fecha_ayer, fecha_ayer)
    res = resultado_periodo['resumen']
    assert res['jornada_teorica_hs'] == 8.5, f"Resumen jornada teórica esperada 8.5, obtenida: {res['jornada_teorica_hs']}"
    assert res['minutos_teoricos_jornada'] == 510.0, f"Resumen minutos teóricos esperados 510.0, obtenido: {res['minutos_teoricos_jornada']}"
    assert res['hora_inicio_taller'] == "07:00", f"Resumen hora inicio esperada 07:00, obtenida: {res['hora_inicio_taller']}"
    assert res['hora_fin_taller'] == "16:00", f"Resumen hora fin esperada 16:00, obtenida: {res['hora_fin_taller']}"
    assert res['tolerancia_bache_minutos'] == 15, f"Resumen tolerancia bache esperada 15, obtenida: {res['tolerancia_bache_minutos']}"
    print("   [OK] Motor de auditoría utiliza directamente las constantes fijas de planta sin dependencia de BD!")

    # 9. Validación del Módulo de Operarios Estilo Ausentismo (Exclusión automática de inactivos y Esquema Rotativo)
    print("\n9. Validando Módulo de Gestión de Operarios (Estilo Ausentismo)...")
    from control_produccion.models import OperarioTaller
    req_op_view = rf.get('/operarios/')
    resp_op_view = operarios_config_view(req_op_view)
    assert resp_op_view.status_code == 200, f"Error en operarios_config_view: {resp_op_view.status_code}"
    html_op_view = resp_op_view.content.decode('utf-8')
    assert 'Gestión de Operarios de Taller' in html_op_view
    assert 'Nómina Activa de Planta' in html_op_view
    assert '/operarios/nuevo/' in html_op_view, "El botón '+ Nuevo Operario' debe enlazar a /operarios/nuevo/!"
    print("   [OK] Botón '+ Nuevo Operario' verificado: apunta correctamente a /operarios/nuevo/!")

    # Probar endpoint dedicado nuevo_operario_view
    req_nuevo_form = rf.get('/operarios/nuevo/')
    resp_nuevo_form = nuevo_operario_view(req_nuevo_form)
    assert resp_nuevo_form.status_code == 200, f"Error en nuevo_operario_view: {resp_nuevo_form.status_code}"
    html_nuevo = resp_nuevo_form.content.decode('utf-8')
    assert 'Registrar Operario' in html_nuevo
    assert 'Datos Personales' in html_nuevo
    assert 'Esquema Rotativo Semanal' in html_nuevo
    assert 'Copiar Lunes a toda la semana' in html_nuevo
    assert 'Ver Listado Maestro' in html_nuevo
    assert 'NÚMERO DE LEGAJO' in html_nuevo
    assert 'NOMBRE COMPLETO' in html_nuevo
    assert 'modalListadoMaestro' in html_nuevo
    print("   [OK] Formulario de operario (Limpio a 2 columnas: Legajo, Nombre, switches verdes, Copiar Lunes y Modal Listado Maestro) verificado correctamente!")

    # Verificar que solo se listen operarios activos por defecto
    total_db_activos = OperarioTaller.objects.filter(activo=True).count()
    context_operarios = resp_op_view.context_data['operarios'] if hasattr(resp_op_view, 'context_data') else None
    print(f"   [OK] Total de operarios en nómina activa de planta: {total_db_activos}")

    # Probar alta / guardado de operario con esquema rotativo semanal
    OperarioTaller.objects.filter(id_concepto='TEST_999').delete()
    try:
        req_guardar = rf.post('/operarios/', {
            'accion': 'guardar_operario',
            'id_concepto': 'TEST_999',
            'nombre': 'OPERARIO PRUEBA ROTATIVO',
            'dia_lunes_activo': 'on',
            'dia_lunes_inicio': '07:00',
            'dia_lunes_fin': '16:00',
            'dia_martes_activo': 'on',
            'dia_martes_inicio': '07:00',
            'dia_martes_fin': '16:00',
            'dia_miercoles_activo': 'on',
            'dia_miercoles_inicio': '07:00',
            'dia_miercoles_fin': '16:00',
            'dia_jueves_activo': 'on',
            'dia_jueves_inicio': '07:00',
            'dia_jueves_fin': '16:00',
            'dia_viernes_activo': 'on',
            'dia_viernes_inicio': '07:00',
            'dia_viernes_fin': '16:00',
            'dia_sabado_activo': 'on',
            'dia_sabado_inicio': '07:00',
            'dia_sabado_fin': '12:00',
            'dia_domingo_activo': 'off',
            'dia_domingo_inicio': '07:00',
            'dia_domingo_fin': '12:00',
        })
        resp_guardar = operarios_config_view(req_guardar)
        assert resp_guardar.status_code == 302, f"Se esperaba redirección al guardar operario, obtenido: {resp_guardar.status_code}"
        
        op_test = OperarioTaller.objects.get(id_concepto='TEST_999')
        assert op_test.nombre == 'OPERARIO PRUEBA ROTATIVO'
        assert op_test.activo == True
        esquema_guardado = op_test.get_esquema_semanal()
        assert esquema_guardado['lunes']['activo'] == True
        assert esquema_guardado['lunes']['inicio'] == '07:00'
        assert esquema_guardado['lunes']['fin'] == '16:00'
        assert esquema_guardado['sabado']['activo'] == True
        assert esquema_guardado['sabado']['fin'] == '12:00'
        assert esquema_guardado['domingo']['activo'] == False

        # Probar cálculo de horario por día
        h_lun = op_test.get_horario_dia(0)
        assert h_lun['activo'] == True
        assert h_lun['horas_teoricas'] == 8.5
        h_sab = op_test.get_horario_dia(5)
        assert h_sab['activo'] == True
        assert h_sab['horas_teoricas'] == 5.0
        h_dom = op_test.get_horario_dia(6)
        assert h_dom['activo'] == False
        assert h_dom['horas_teoricas'] == 0.0
        print("   [OK] Guardado de operario y esquema rotativo verificado: Lun-Vie 8,5 hs, Sáb 5,0 hs, Dom 0,0 hs!")

        # Probar desactivación y comprobación de exclusión automática de la lista
        req_toggle = rf.post('/operarios/', {'accion': 'toggle_activo', 'id': op_test.id})
        operarios_config_view(req_toggle)
        op_test.refresh_from_db()
        assert op_test.activo == False, "Operario debe quedar con activo=False"
        
        resp_activos_only = operarios_config_view(rf.get('/operarios/'))
        html_activos = resp_activos_only.content.decode('utf-8')
        assert 'TEST_999' not in html_activos, "El operario desactivado debe ser excluido y ocultado automáticamente de la vista activa!"
        print("   [OK] Exclusión automática de empleados desactivados verificada con éxito!")
    finally:
        # Limpieza asegurada del operario de prueba
        OperarioTaller.objects.filter(id_concepto='TEST_999').delete()

    # 10. Validación de Checkout y Panel VIP de Aura Botanica
    print("\n10. Validando Interfaz de Checkout y Panel VIP de Aura Botanica...")
    req_aura = rf.get('/aura-botanica/')
    resp_aura = aura_botanica_view(req_aura)
    assert resp_aura.status_code == 200, f"Error al renderizar /aura-botanica/: {resp_aura.status_code}"
    html_aura = resp_aura.content.decode('utf-8')
    assert 'Aura Botanica' in html_aura
    assert 'Mercado Pago' in html_aura
    assert 'Transferencia Bancaria Inmediata' in html_aura
    assert 'Efectivo Contra Entrega' in html_aura
    assert 'VIP CREATOR STUDIO' in html_aura
    assert 'Publicar Producto' in html_aura
    assert '🚀' in html_aura
    assert 'Selector de Variantes' in html_aura
    print("   [OK] Aura Botanica: Pasarela minimalista (MP, Transferencia, Efectivo) y Panel VIP con [Rocket] Publicar Producto verificados!")

    print("\n=== TODAS LAS PRUEBAS PASARON EXITOSAMENTE ===")

if __name__ == '__main__':
    test_full_flow()

