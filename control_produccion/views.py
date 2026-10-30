"""
Vistas para el Módulo de Control y Auditoría de Producción ABBAMAT.
Cruza la jornada laboral teórica de 8,5 horas con los registros reales de producción del ERP.
"""

import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import OperarioTaller, NotaAuditoria
from .services.analytics_service import (
    auditar_jornada_produccion,
    auditar_periodo_produccion,
    sincronizar_operarios_taller,
    parse_fecha,
)
from .services.excel_service import generar_excel_auditoria_produccion


def _obtener_fecha_filtro(request):
    """Helper para extraer y validar la fecha seleccionada en el request."""
    fecha_param = request.GET.get('fecha')
    if fecha_param:
        try:
            return datetime.datetime.strptime(fecha_param, '%Y-%m-%d').date()
        except Exception:
            pass
    # Por defecto, hoy
    return datetime.date.today()


def _obtener_rango_fechas(request):
    """
    Helper para extraer y validar el intervalo de fechas (Desde / Hasta) en el request.
    Soporta:
    1. fecha_desde y fecha_hasta explícitos
    2. fecha única (?fecha=YYYY-MM-DD)
    3. Si no se provee nada, por defecto hoy
    """
    hoy = datetime.date.today()
    fecha_desde_param = request.GET.get('fecha_desde')
    fecha_hasta_param = request.GET.get('fecha_hasta')
    fecha_unica_param = request.GET.get('fecha')

    if fecha_desde_param and fecha_hasta_param:
        try:
            f_desde = datetime.datetime.strptime(fecha_desde_param.strip(), '%Y-%m-%d').date()
        except Exception:
            f_desde = hoy
        try:
            f_hasta = datetime.datetime.strptime(fecha_hasta_param.strip(), '%Y-%m-%d').date()
        except Exception:
            f_hasta = f_desde
    elif fecha_desde_param:
        try:
            f_desde = datetime.datetime.strptime(fecha_desde_param.strip(), '%Y-%m-%d').date()
        except Exception:
            f_desde = hoy
        f_hasta = f_desde
    elif fecha_hasta_param:
        try:
            f_hasta = datetime.datetime.strptime(fecha_hasta_param.strip(), '%Y-%m-%d').date()
        except Exception:
            f_hasta = hoy
        f_desde = f_hasta
    elif fecha_unica_param:
        try:
            f_unica = datetime.datetime.strptime(fecha_unica_param.strip(), '%Y-%m-%d').date()
        except Exception:
            f_unica = hoy
        f_desde = f_unica
        f_hasta = f_unica
    else:
        f_desde = hoy
        f_hasta = hoy

    if f_desde > f_hasta:
        f_desde, f_hasta = f_hasta, f_desde

    return f_desde, f_hasta


def _aplicar_filtro_operario(datos, op_id_or_name):
    """
    Filtra los datos analíticos para un único operario y recalcula dinámicamente
    el resumen, tarjetas métricas y listas para auditar el rendimiento particular.
    """
    if not op_id_or_name or str(op_id_or_name).strip() in ('', 'TODOS'):
        return datos

    op_id_str = str(op_id_or_name).strip().lower()
    operario_encontrado = None
    for op in datos['operarios']:
        if str(op['id_concepto']).strip().lower() == op_id_str or op['nombre'].strip().lower() == op_id_str:
            operario_encontrado = op
            break

    if not operario_encontrado:
        for op in datos['operarios']:
            if op_id_str in str(op['id_concepto']).strip().lower() or op_id_str in op['nombre'].strip().lower():
                operario_encontrado = op
                break

    if not operario_encontrado:
        return datos

    res = dict(datos['resumen'])
    op = operario_encontrado

    # Recalcular métricas específicas para el operario seleccionado
    res['operario_individual'] = True
    res['operario_filtrado_id'] = op['id_concepto']
    res['operario_filtrado_nombre'] = op['nombre']
    res['operario_filtrado_puesto'] = op['puesto']
    res['operario_filtrado_estado'] = op['estado']

    res['total_nomina'] = 1
    res['operarios_con_registro'] = 1 if op['cantidad_total_lineas'] > 0 else 0
    res['operarios_omision_total'] = 1 if op['estado'] == 'SIN_REGISTRO' else 0
    res['operarios_cumplidos'] = 1 if op['estado'] == 'CUMPLIDO' else 0
    res['operarios_parciales'] = 1 if op['estado'] == 'PARCIAL' else 0
    res['operarios_criticos'] = 1 if op['estado'] == 'CRITICO' else 0

    res['horas_totales_registradas'] = op['horas_reales']
    res['minutos_totales_registrados'] = op['minutos_reales']
    
    # Meta teórica individual del periodo o día
    horas_teoricas_indiv = op.get('horas_teoricas') or res.get('horas_teoricas_operario') or (res.get('jornada_teorica_hs', 8.5) * res.get('dias_habiles', 1))
    res['horas_totales_teoricas'] = round(horas_teoricas_indiv, 2)
    res['horas_totales_estandar'] = op['horas_std']
    res['total_piezas_planta'] = op['cantidad_piezas']
    res['promedio_horas_por_operario'] = op['horas_reales']
    res['promedio_diario_por_operario'] = op.get('promedio_diario_horas', op['horas_reales'])

    res['total_baches_count'] = op['cantidad_baches']
    res['total_horas_baches'] = op.get('horas_en_baches', 0.0)

    res['indice_cobertura_global'] = op['indice_cumplimiento']
    
    # Tasa de carga / adopción real del operario individual frente a la jornada obligatoria
    UMBRAL_ADOPCION_ACEPTABLE = 80.0
    cumple_adopcion_indiv = op['indice_cumplimiento'] >= UMBRAL_ADOPCION_ACEPTABLE
    res['umbral_adopcion_porc'] = UMBRAL_ADOPCION_ACEPTABLE
    res['operarios_cumplen_adopcion'] = 1 if cumple_adopcion_indiv else 0
    res['tasa_adopcion_registro'] = round(op['indice_cumplimiento'], 1)
    
    res['rendimiento_tecnico_global'] = op['eficiencia_tecnica']

    # Máquinas individuales del operario
    maquinas_op_top = sorted(
        [{'maquina': k, 'horas': round(v / 60.0, 2)} for k, v in op.get('maquinas', {}).items()],
        key=lambda x: x['horas'],
        reverse=True
    )[:8]
    res['maquinas_top'] = maquinas_op_top

    return {
        'resumen': res,
        'operarios': [op],
        'ranking': [op],
        'omisiones': [op] if op['estado'] == 'SIN_REGISTRO' else [],
        'operario_filtrado': op,
    }


def dashboard_view(request):
    """
    Vista del Menú Principal / Dashboard Ejecutivo de Producción.
    Permite seleccionar un intervalo (Desde / Hasta), filtrar por operario/legajo
    y consolida los acumulados de producción recalculando dinámicamente las métricas.
    """
    fecha_desde, fecha_hasta = _obtener_rango_fechas(request)
    filtro_operario = request.GET.get('operario', '').strip()

    datos = auditar_periodo_produccion(fecha_desde, fecha_hasta)
    nomina_activa = OperarioTaller.objects.filter(activo=True).order_by('nombre')

    if filtro_operario:
        datos = _aplicar_filtro_operario(datos, filtro_operario)

    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    primer_dia_mes = datetime.date(hoy.year, hoy.month, 1)
    hace_7_dias = hoy - datetime.timedelta(days=6)

    context = {
        'seccion_activa': 'dashboard',
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_desde_str': fecha_desde.strftime('%Y-%m-%d'),
        'fecha_hasta_str': fecha_hasta.strftime('%Y-%m-%d'),
        'fecha_desde_formateada': fecha_desde.strftime('%d/%m/%Y'),
        'fecha_hasta_formateada': fecha_hasta.strftime('%d/%m/%Y'),
        'fecha_str': fecha_hasta.strftime('%Y-%m-%d'),
        'fecha_ayer': (fecha_desde - datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'fecha_manana': (fecha_hasta + datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
        'es_mismo_dia': fecha_desde == fecha_hasta,
        'es_hoy': fecha_desde == hoy and fecha_hasta == hoy,
        'es_ayer': fecha_desde == ayer and fecha_hasta == ayer,
        'preset_hoy_desde': hoy.strftime('%Y-%m-%d'),
        'preset_hoy_hasta': hoy.strftime('%Y-%m-%d'),
        'preset_ayer_desde': ayer.strftime('%Y-%m-%d'),
        'preset_ayer_hasta': ayer.strftime('%Y-%m-%d'),
        'preset_7dias_desde': hace_7_dias.strftime('%Y-%m-%d'),
        'preset_7dias_hasta': hoy.strftime('%Y-%m-%d'),
        'preset_mes_desde': primer_dia_mes.strftime('%Y-%m-%d'),
        'preset_mes_hasta': hoy.strftime('%Y-%m-%d'),
        'resumen': datos['resumen'],
        'operarios': datos['operarios'],
        'ranking': datos['ranking'],
        'omisiones': datos['omisiones'],
        'nomina_completa_activa': nomina_activa,
        'operario_filtro': filtro_operario,
        'operario_filtrado': datos.get('operario_filtrado'),
    }
    return render(request, 'control_produccion/dashboard.html', context)


def control_produccion_view(request):
    """
    Pantalla Principal de Control y Auditoría de Producción de Taller.
    Muestra la matriz completa de cumplimiento vs jornada teórica (8,5 hs por día hábil),
    identificación de operarios con omisiones/baches, barra visual Gantt y filtros interactivos.
    Soporta filtro por intervalo (Desde / Hasta) y filtro dinámico por operario/legajo.
    """
    fecha_desde, fecha_hasta = _obtener_rango_fechas(request)
    filtro_estado = request.GET.get('estado', 'TODOS').upper()
    filtro_buscar = request.GET.get('q', '').strip().lower()
    filtro_operario = request.GET.get('operario', '').strip()

    datos = auditar_periodo_produccion(fecha_desde, fecha_hasta)
    nomina_activa = OperarioTaller.objects.filter(activo=True).order_by('nombre')

    if filtro_operario:
        datos = _aplicar_filtro_operario(datos, filtro_operario)

    lista_operarios = datos['operarios']

    # Aplicar filtros si se especificaron
    if filtro_estado != 'TODOS':
        lista_operarios = [op for op in lista_operarios if op['estado'] == filtro_estado]

    if filtro_buscar:
        lista_operarios = [
            op for op in lista_operarios 
            if filtro_buscar in op['nombre'].lower() or filtro_buscar in op['id_concepto'].lower()
        ]

    # ORDENAMIENTO DE LA MATRIZ DE PRODUCCIÓN:
    # Por defecto los operarios se ordenan de mayor a menor según las horas reales registradas.
    criterio_orden = request.GET.get('orden', 'horas_desc').lower()
    if criterio_orden == 'horas_asc':
        lista_operarios = sorted(lista_operarios, key=lambda x: (x['horas_reales'], x['indice_cumplimiento']))
    elif criterio_orden == 'cumplimiento_desc':
        lista_operarios = sorted(lista_operarios, key=lambda x: (x['indice_cumplimiento'], x['horas_reales']), reverse=True)
    elif criterio_orden == 'cumplimiento_asc':
        lista_operarios = sorted(lista_operarios, key=lambda x: (x['indice_cumplimiento'], x['horas_reales']))
    elif criterio_orden == 'nombre_asc':
        lista_operarios = sorted(lista_operarios, key=lambda x: x['nombre'].lower())
    elif criterio_orden == 'nombre_desc':
        lista_operarios = sorted(lista_operarios, key=lambda x: x['nombre'].lower(), reverse=True)
    else:
        criterio_orden = 'horas_desc'
        lista_operarios = sorted(lista_operarios, key=lambda x: (x['horas_reales'], x['indice_cumplimiento']), reverse=True)

    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    primer_dia_mes = datetime.date(hoy.year, hoy.month, 1)
    hace_7_dias = hoy - datetime.timedelta(days=6)

    context = {
        'seccion_activa': 'control_produccion',
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_desde_str': fecha_desde.strftime('%Y-%m-%d'),
        'fecha_hasta_str': fecha_hasta.strftime('%Y-%m-%d'),
        'fecha_desde_formateada': fecha_desde.strftime('%d/%m/%Y'),
        'fecha_hasta_formateada': fecha_hasta.strftime('%d/%m/%Y'),
        'fecha': fecha_hasta,
        'fecha_str': fecha_hasta.strftime('%Y-%m-%d'),
        'es_mismo_dia': fecha_desde == fecha_hasta,
        'es_hoy': fecha_desde == hoy and fecha_hasta == hoy,
        'es_ayer': fecha_desde == ayer and fecha_hasta == ayer,
        'preset_hoy_desde': hoy.strftime('%Y-%m-%d'),
        'preset_hoy_hasta': hoy.strftime('%Y-%m-%d'),
        'preset_ayer_desde': ayer.strftime('%Y-%m-%d'),
        'preset_ayer_hasta': ayer.strftime('%Y-%m-%d'),
        'preset_7dias_desde': hace_7_dias.strftime('%Y-%m-%d'),
        'preset_7dias_hasta': hoy.strftime('%Y-%m-%d'),
        'preset_mes_desde': primer_dia_mes.strftime('%Y-%m-%d'),
        'preset_mes_hasta': hoy.strftime('%Y-%m-%d'),
        'resumen': datos['resumen'],
        'operarios': lista_operarios,
        'total_filtrados': len(lista_operarios),
        'filtro_estado': filtro_estado,
        'filtro_buscar': filtro_buscar,
        'criterio_orden': criterio_orden,
        'omisiones_count': len(datos['omisiones']),
        'nomina_completa_activa': nomina_activa,
        'operario_filtro': filtro_operario,
        'operario_filtrado': datos.get('operario_filtrado'),
    }
    return render(request, 'control_produccion/control_produccion.html', context)


def detalle_operario_view(request, id_concepto):
    """
    Ficha Técnica Individual de Auditoría de un Operario para la fecha seleccionada.
    Desglose orden por orden, máquinas, tiempos reales y estándar, y análisis de baches.
    """
    fecha = _obtener_fecha_filtro(request)
    datos = auditar_jornada_produccion(fecha)

    # Buscar el operario en el resultado
    op_seleccionado = None
    for op in datos['operarios']:
        if str(op['id_concepto']).strip() == str(id_concepto).strip():
            op_seleccionado = op
            break

    if not op_seleccionado:
        op_db = OperarioTaller.objects.filter(id_concepto=str(id_concepto).strip()).first()
        if op_db and not op_db.activo:
            messages.warning(request, f"El operario {op_db.nombre} (ID: {id_concepto}) se encuentra INACTIVO y está excluido de la nómina de planta.")
        else:
            messages.error(request, f"No se encontró al operario con ID {id_concepto} en la nómina activa de taller.")
        return redirect('control_produccion:control_produccion')

    # Historial de notas de auditoría del operario
    notas_previas = NotaAuditoria.objects.filter(id_concepto=id_concepto).order_by('-fecha')[:10]

    context = {
        'seccion_activa': 'control_produccion',
        'fecha': fecha,
        'fecha_str': fecha.strftime('%Y-%m-%d'),
        'operario': op_seleccionado,
        'resumen': datos['resumen'],
        'notas_previas': notas_previas,
    }
    return render(request, 'control_produccion/detalle_operario.html', context)


@require_POST
def guardar_nota_auditoria(request):
    """
    Registra o actualiza una nota de auditoría para un operario en una fecha determinada.
    """
    id_concepto = request.POST.get('id_concepto')
    fecha_str = request.POST.get('fecha')
    motivo = request.POST.get('motivo', 'OMISION_CARGA')
    detalle = request.POST.get('detalle', '').strip()

    if not id_concepto or not fecha_str or not detalle:
        messages.error(request, "Todos los campos de la nota son obligatorios.")
        return redirect(request.META.get('HTTP_REFERER', 'control_produccion:control_produccion'))

    fecha = parse_fecha(fecha_str)

    NotaAuditoria.objects.update_or_create(
        fecha=fecha,
        id_concepto=id_concepto,
        defaults={
            'motivo': motivo,
            'detalle': detalle,
        }
    )

    messages.success(request, f"Justificación de auditoría guardada correctamente para el operario {id_concepto}.")
    return redirect(request.META.get('HTTP_REFERER', 'control_produccion:control_produccion'))


def _safe_message(request, level, text):
    try:
        if level == 'success':
            messages.success(request, text)
        elif level == 'error':
            messages.error(request, text)
        elif level == 'info':
            messages.info(request, text)
        elif level == 'warning':
            messages.warning(request, text)
    except Exception:
        pass


def operarios_config_view(request):
    """
    Gestión de Nómina de Operarios del Taller (Estilo Ausentismo).
    Excluye y oculta automáticamente a todos los empleados desactivados,
    mostrando únicamente la nómina activa de planta.
    Permite alta y edición con datos personales y esquema rotativo semanal día por día.
    """
    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'sincronizar':
            sincronizar_operarios_taller()
            _safe_message(request, 'success', "Nómina sincronizada con éxito desde la tabla TMAN014 del ERP.")
            return redirect('control_produccion:operarios_config')

        if accion == 'guardar_operario':
            id_concepto = request.POST.get('id_concepto', '').strip()
            nombre = request.POST.get('nombre', '').strip().upper()

            if not id_concepto or not nombre:
                _safe_message(request, 'error', "Debe ingresar el Número de Legajo y el Nombre Completo.")
                return redirect('control_produccion:operarios_config')

            # Esquema rotativo semanal
            dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
            esquema = {}
            for d in dias:
                activo_d = request.POST.get(f'dia_{d}_activo') in ['on', 'true', '1']
                inicio_d = request.POST.get(f'dia_{d}_inicio', '07:00').strip() or '07:00'
                fin_d = request.POST.get(f'dia_{d}_fin', '16:00').strip() or '16:00'
                esquema[d] = {
                    'activo': activo_d,
                    'inicio': inicio_d,
                    'fin': fin_d,
                }

            categoria = request.POST.get('categoria', 'PRODUCCIÓN').strip() or 'PRODUCCIÓN'
            es_mensual = request.POST.get('es_mensual') in ['on', 'true', '1']

            op, created = OperarioTaller.objects.get_or_create(
                id_concepto=id_concepto,
                defaults={
                    'nombre': nombre,
                    'categoria': categoria,
                    'es_mensual': es_mensual,
                    'activo': True,
                    'horario_rotativo': esquema,
                }
            )
            if not created:
                op.nombre = nombre
                op.categoria = categoria
                op.es_mensual = es_mensual
                op.horario_rotativo = esquema
                op.activo = True
                op.save(update_fields=['nombre', 'categoria', 'es_mensual', 'horario_rotativo', 'activo'])

            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
                return JsonResponse({'status': 'ok', 'id_concepto': op.id_concepto, 'nombre': op.nombre})

            _safe_message(request, 'success', f"Operario {op.nombre} (Legajo: {op.id_concepto}) y su esquema semanal fueron guardados correctamente.")
            return redirect('control_produccion:operarios_config')

        if accion == 'toggle_activo':
            op_id = request.POST.get('id')
            op = get_object_or_404(OperarioTaller, pk=op_id)
            op.activo = not op.activo
            op.save(update_fields=['activo'])
            if op.activo:
                _safe_message(request, 'success', f"Operario {op.nombre} activado e incorporado a la nómina de planta.")
            else:
                _safe_message(request, 'info', f"Operario {op.nombre} desactivado y excluido automáticamente de la nómina activa.")
            return redirect('control_produccion:operarios_config')

        if accion == 'eliminar_operario':
            op_id = request.POST.get('id')
            op = get_object_or_404(OperarioTaller, pk=op_id)
            nombre_del = op.nombre
            op.delete()
            _safe_message(request, 'success', f"Operario {nombre_del} eliminado correctamente.")
            return redirect('control_produccion:operarios_config')

    # EXCLUSIÓN Y OCULTAMIENTO AUTOMÁTICO DE INACTIVOS:
    # Se obtienen y muestran ÚNICAMENTE los operarios activos en la nómina de planta
    ver_inactivos = request.GET.get('ver_inactivos') == '1'
    if ver_inactivos:
        operarios = OperarioTaller.objects.all().order_by('nombre')
    else:
        operarios = OperarioTaller.objects.filter(activo=True).order_by('nombre')

    total_activos = OperarioTaller.objects.filter(activo=True).count()
    total_inactivos = OperarioTaller.objects.filter(activo=False).count()

    sectores = [
        'DTO. INFORMATICA',
        'DPTO. INGENIERIA',
        'PRODUCCIÓN',
        'SUPERVISOR',
        'DPTO. CALIDAD',
        'ADMINISTRACION',
        'ALMACEN',
        'AUXILIAR',
    ]

    context = {
        'seccion_activa': 'configuracion',
        'operarios': operarios,
        'total_activos': total_activos,
        'total_inactivos': total_inactivos,
        'ver_inactivos': ver_inactivos,
        'sectores': sectores,
        'dias_semana': [
            {'key': 'lunes', 'nombre': 'Lunes', 'corto': 'LUN', 'default_activo': True, 'default_inicio': '07:00', 'default_fin': '16:00'},
            {'key': 'martes', 'nombre': 'Martes', 'corto': 'MAR', 'default_activo': True, 'default_inicio': '07:00', 'default_fin': '16:00'},
            {'key': 'miercoles', 'nombre': 'Miércoles', 'corto': 'MIÉ', 'default_activo': True, 'default_inicio': '07:00', 'default_fin': '16:00'},
            {'key': 'jueves', 'nombre': 'Jueves', 'corto': 'JUE', 'default_activo': True, 'default_inicio': '07:00', 'default_fin': '16:00'},
            {'key': 'viernes', 'nombre': 'Viernes', 'corto': 'VIE', 'default_activo': True, 'default_inicio': '07:00', 'default_fin': '16:00'},
            {'key': 'sabado', 'nombre': 'Sábado', 'corto': 'SÁB', 'default_activo': False, 'default_inicio': '07:00', 'default_fin': '12:00'},
            {'key': 'domingo', 'nombre': 'Domingo', 'corto': 'DOM', 'default_activo': False, 'default_inicio': '07:00', 'default_fin': '12:00'},
        ],
    }
    return render(request, 'control_produccion/operarios_config.html', context)


def nuevo_operario_view(request):
    """
    Formulario de Alta de Operario (Estilo Ausentismo).
    1. Datos Personales: Número de Legajo, Nombre Completo, Casilla de Liquidación Mensual, y Cuadrícula de Sectores en 2 columnas.
    2. Esquema Rotativo Semanal: Lunes a Domingo con switches verdes/gris, horas 07:00 a 16:00 y botón 'Copiar Lunes a toda la semana'.
    3. Modal con Listado Maestro de Operarios completo.
    """
    if request.method == 'POST':
        id_concepto = request.POST.get('id_concepto', '').strip()
        nombre = request.POST.get('nombre', '').strip().upper()
        categoria = request.POST.get('categoria', 'PRODUCCIÓN').strip() or 'PRODUCCIÓN'
        es_mensual = request.POST.get('es_mensual') in ['on', 'true', '1']

        if not id_concepto or not nombre:
            _safe_message(request, 'error', "Debe ingresar el Número de Legajo y el Nombre Completo.")
            return redirect('control_produccion:nuevo_operario')

        dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        esquema = {}
        for d in dias:
            activo_d = request.POST.get(f'dia_{d}_activo') in ['on', 'true', '1']
            inicio_d = request.POST.get(f'dia_{d}_inicio', '07:00').strip() or '07:00'
            fin_d = request.POST.get(f'dia_{d}_fin', '16:00').strip() or '16:00'
            esquema[d] = {
                'activo': activo_d,
                'inicio': inicio_d,
                'fin': fin_d,
            }

        op, created = OperarioTaller.objects.get_or_create(
            id_concepto=id_concepto,
            defaults={
                'nombre': nombre,
                'categoria': categoria,
                'es_mensual': es_mensual,
                'activo': True,
                'horario_rotativo': esquema,
            }
        )
        if not created:
            op.nombre = nombre
            op.categoria = categoria
            op.es_mensual = es_mensual
            op.horario_rotativo = esquema
            op.activo = True
            op.save(update_fields=['nombre', 'categoria', 'es_mensual', 'horario_rotativo', 'activo'])

        _safe_message(request, 'success', f"Operario {op.nombre} (Legajo: {op.id_concepto}) creado e incorporado a la nómina activa.")
        return redirect('control_produccion:operarios_config')

    dias_semana = [
        {'key': 'lunes', 'nombre': 'Lunes', 'corto': 'LUN', 'activo': True, 'inicio': '07:00', 'fin': '16:00', 'horas': '8,5 hs'},
        {'key': 'martes', 'nombre': 'Martes', 'corto': 'MAR', 'activo': True, 'inicio': '07:00', 'fin': '16:00', 'horas': '8,5 hs'},
        {'key': 'miercoles', 'nombre': 'Miércoles', 'corto': 'MIÉ', 'activo': True, 'inicio': '07:00', 'fin': '16:00', 'horas': '8,5 hs'},
        {'key': 'jueves', 'nombre': 'Jueves', 'corto': 'JUE', 'activo': True, 'inicio': '07:00', 'fin': '16:00', 'horas': '8,5 hs'},
        {'key': 'viernes', 'nombre': 'Viernes', 'corto': 'VIE', 'activo': True, 'inicio': '07:00', 'fin': '16:00', 'horas': '8,5 hs'},
        {'key': 'sabado', 'nombre': 'Sábado', 'corto': 'SÁB', 'activo': False, 'inicio': '07:00', 'fin': '12:00', 'horas': '0,0 hs'},
        {'key': 'domingo', 'nombre': 'Domingo', 'corto': 'DOM', 'activo': False, 'inicio': '07:00', 'fin': '12:00', 'horas': '0,0 hs'},
    ]

    sectores = [
        'DTO. INFORMATICA',
        'DPTO. INGENIERIA',
        'PRODUCCIÓN',
        'SUPERVISOR',
        'DPTO. CALIDAD',
        'ADMINISTRACION',
        'ALMACEN',
        'AUXILIAR',
    ]

    operarios_maestro = OperarioTaller.objects.filter(activo=True).order_by('nombre')
    total_activos = operarios_maestro.count()

    context = {
        'seccion_activa': 'configuracion',
        'es_edicion': False,
        'dias_semana': dias_semana,
        'sectores': sectores,
        'operarios': operarios_maestro,
        'total_activos': total_activos,
    }
    return render(request, 'control_produccion/operario_form.html', context)


def editar_operario_view(request, id_concepto):
    """
    Formulario de Edición Limpio de Operario (Estilo Ausentismo).
    Permite modificar datos personales, categoría, liquidación y el esquema rotativo semanal día por día.
    Incluye acceso al modal de Listado Maestro de Operarios.
    """
    op = get_object_or_404(OperarioTaller, id_concepto=id_concepto)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip().upper()
        categoria = request.POST.get('categoria', 'PRODUCCIÓN').strip() or 'PRODUCCIÓN'
        es_mensual = request.POST.get('es_mensual') in ['on', 'true', '1']

        if not nombre:
            _safe_message(request, 'error', "El nombre completo no puede estar vacío.")
            return redirect('control_produccion:editar_operario', id_concepto=op.id_concepto)

        dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        esquema = {}
        for d in dias:
            activo_d = request.POST.get(f'dia_{d}_activo') in ['on', 'true', '1']
            inicio_d = request.POST.get(f'dia_{d}_inicio', '07:00').strip() or '07:00'
            fin_d = request.POST.get(f'dia_{d}_fin', '16:00').strip() or '16:00'
            esquema[d] = {
                'activo': activo_d,
                'inicio': inicio_d,
                'fin': fin_d,
            }

        op.nombre = nombre
        op.categoria = categoria
        op.es_mensual = es_mensual
        op.horario_rotativo = esquema
        op.activo = True
        op.save(update_fields=['nombre', 'categoria', 'es_mensual', 'horario_rotativo', 'activo'])

        _safe_message(request, 'success', f"Operario {op.nombre} y su esquema semanal fueron actualizados correctamente.")
        return redirect('control_produccion:operarios_config')

    esquema_guardado = op.get_esquema_semanal()
    nombres_dias = {
        'lunes': ('Lunes', 'LUN'),
        'martes': ('Martes', 'MAR'),
        'miercoles': ('Miércoles', 'MIÉ'),
        'jueves': ('Jueves', 'JUE'),
        'viernes': ('Viernes', 'VIE'),
        'sabado': ('Sábado', 'SÁB'),
        'domingo': ('Domingo', 'DOM'),
    }

    dias_semana = []
    for k in ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']:
        conf = esquema_guardado.get(k, {})
        activo = conf.get('activo', k not in ['sabado', 'domingo'])
        ini = conf.get('inicio', '07:00')
        fin = conf.get('fin', '16:00' if k not in ['sabado', 'domingo'] else '12:00')
        
        # Calcular horas
        h_info = op.get_horario_dia(k)
        hs_str = f"{h_info['horas_teoricas']:.1f}".replace('.', ',') + ' hs' if activo else '0,0 hs'

        dias_semana.append({
            'key': k,
            'nombre': nombres_dias[k][0],
            'corto': nombres_dias[k][1],
            'activo': activo,
            'inicio': ini,
            'fin': fin,
            'horas': hs_str,
        })

    sectores = [
        'DTO. INFORMATICA',
        'DPTO. INGENIERIA',
        'PRODUCCIÓN',
        'SUPERVISOR',
        'DPTO. CALIDAD',
        'ADMINISTRACION',
        'ALMACEN',
        'AUXILIAR',
    ]

    operarios_maestro = OperarioTaller.objects.filter(activo=True).order_by('nombre')
    total_activos = operarios_maestro.count()

    context = {
        'seccion_activa': 'configuracion',
        'es_edicion': True,
        'operario': op,
        'dias_semana': dias_semana,
        'sectores': sectores,
        'operarios': operarios_maestro,
        'total_activos': total_activos,
    }
    return render(request, 'control_produccion/operario_form.html', context)


def api_operario_detalle(request, id_concepto):
    """
    Retorna los datos y esquema semanal de un operario en JSON para cargar el modal de edición.
    """
    op = get_object_or_404(OperarioTaller, id_concepto=id_concepto)
    return JsonResponse({
        'id': op.id,
        'id_concepto': op.id_concepto,
        'nombre': op.nombre,
        'activo': op.activo,
        'es_mensual': op.es_mensual,
        'categoria': op.categoria,
        'horario_base': op.horario_base,
        'esquema_rotativo': op.get_esquema_semanal(),
    })


def aura_botanica_view(request):
    """
    Interfaz de Checkout Minimalista y Panel VIP de Administración de Productos para 'Aura Botanica'.
    Estilo visual moderno, divertido, colorido y de alta gama (estilo app SaaS moderna),
    bordes de 24px, sombras flotantes, y acentos en azul neón, coral brillante y verde esmeralda.
    """
    return render(request, 'aura_botanica/checkout_vip.html')


def parametros_taller_view(request):
    """
    Vista eliminada: los parámetros de auditoría son fijos y estáticos en el backend
    (jornada obligatoria de 8,5 horas / 510 min, inicio a las 07:00 y fin a las 16:00).
    Redirige a la configuración de nómina de operarios para evitar configuraciones manuales.
    """
    return redirect('control_produccion:operarios_config')


def exportar_excel_view(request):
    """
    Exportación de Informe Analítico a Excel (.xlsx).
    Soporta exportación por fecha única o por intervalo de fechas, y por operario individual.
    """
    fecha_desde, fecha_hasta = _obtener_rango_fechas(request)
    filtro_operario = request.GET.get('operario', '').strip()

    if fecha_desde == fecha_hasta:
        datos = auditar_jornada_produccion(fecha_desde)
        prefix = f"ABBAMAT_Auditoria_Produccion_{fecha_desde.strftime('%Y%m%d')}"
    else:
        datos = auditar_periodo_produccion(fecha_desde, fecha_hasta)
        prefix = f"ABBAMAT_Auditoria_Produccion_{fecha_desde.strftime('%Y%m%d')}_{fecha_hasta.strftime('%Y%m%d')}"

    if filtro_operario:
        datos = _aplicar_filtro_operario(datos, filtro_operario)
        filename = f"{prefix}_Legajo_{filtro_operario}.xlsx"
    else:
        filename = f"{prefix}.xlsx"

    excel_bytes = generar_excel_auditoria_produccion(datos)

    response = HttpResponse(
        excel_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def api_auditoria_dia(request):
    """
    Endpoint JSON para refresco dinámico y consultas asíncronas de auditoría.
    """
    fecha = _obtener_fecha_filtro(request)
    datos = auditar_jornada_produccion(fecha)
    # Limpiar objetos date/datetime para serialización segura
    resumen_json = dict(datos['resumen'])
    if 'fecha' in resumen_json:
        resumen_json['fecha'] = resumen_json['fecha_str']

    operarios_json = []
    for op in datos['operarios']:
        op_dict = dict(op)
        op_dict['nota'] = op_dict['nota'].detalle if op_dict.get('nota') else None
        # Remover datetimes nativos en registros
        cleaned_regs = []
        for r in op_dict.get('registros', []):
            rc = dict(r)
            rc['fecha'] = str(rc.get('fecha'))
            rc['hora_inicio'] = rc.get('hora_inicio_str')
            rc['hora_fin'] = rc.get('hora_fin_str')
            cleaned_regs.append(rc)
        op_dict['registros'] = cleaned_regs

        cleaned_baches = []
        for b in op_dict.get('baches', []):
            bc = dict(b)
            bc.pop('dt_inicio', None)
            bc.pop('dt_fin', None)
            cleaned_baches.append(bc)
        op_dict['baches'] = cleaned_baches

        operarios_json.append(op_dict)

    return JsonResponse({
        'status': 'ok',
        'resumen': resumen_json,
        'operarios': operarios_json,
    })
