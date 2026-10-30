"""
Motor de Cálculo y Análisis de Auditoría de Producción.
Compara la jornada laboral teórica de 8,5 horas diarias con los registros reales de EqualRP.
Calcula índices de cumplimiento, identifica omisiones y baches intradía, y genera estadísticas consolidadas.
"""

import datetime
from django.utils import timezone
from .erp_service import (
    get_registros_produccion_por_fecha,
    get_registros_produccion_por_rango,
    get_all_taller_concepts_from_erp,
)
from control_produccion.models import OperarioTaller, NotaAuditoria
from control_produccion.constants import (
    JORNADA_TEORICA_HORAS,
    MINUTOS_TEORICOS_JORNADA,
    HORA_INICIO_TURNO,
    HORA_FIN_TURNO,
    TOLERANCIA_BACHE_MINUTOS,
    PORCENTAJE_ADOPCION_MINIMO,
    HORAS_MINIMAS_ADOPCION,
)


OPERARIOS_14_DEFAULT = [
    {"id_concepto": "97", "nombre": "BARTET NICOLAS EZEQUIEL", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "57", "nombre": "CACERES FABIAN", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "65", "nombre": "COSTA JAVIER ALEJANDRO", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "39", "nombre": "CREPALDI, NAHUEL C. ALB.", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "92", "nombre": "DARRIGAN GASTON", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "86", "nombre": "FERNANDEZ EZEQUIEL", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "17", "nombre": "FERREYRA DAMIAN", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "99", "nombre": "MASERA ANIBAL EZEQUIEL", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "100", "nombre": "MASERA NICOLAS", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "13", "nombre": "MOLINARI LUCAS", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "48", "nombre": "ROJAS, MARIO ALBERTO", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "995", "nombre": "SCARINCI NICOLAS", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "83", "nombre": "SOSA ROBERTO CARLOS", "categoria": "PRODUCCIÓN", "es_mensual": False},
    {"id_concepto": "66", "nombre": "TABORDA DANIEL GERMAN", "categoria": "PRODUCCIÓN", "es_mensual": False},
]


def sincronizar_operarios_taller():
    """
    Carga y sincroniza la nómina exclusivamente contra la Base de Datos Local
    con los 14 operarios activos confirmados de planta. Sin llamadas de red externas.
    """
    esquema_base = {
        'lunes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
        'martes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
        'miercoles': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
        'jueves': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
        'viernes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
        'sabado': {'activo': False, 'inicio': '07:00', 'fin': '12:00'},
        'domingo': {'activo': False, 'inicio': '07:00', 'fin': '12:00'},
    }
    for op_data in OPERARIOS_14_DEFAULT:
        obj, created = OperarioTaller.objects.get_or_create(
            id_concepto=op_data['id_concepto'],
            defaults={
                'nombre': op_data['nombre'],
                'categoria': op_data['categoria'],
                'es_mensual': op_data['es_mensual'],
                'activo': True,
                'horario_rotativo': esquema_base,
            }
        )
        if not created and not obj.activo:
            obj.activo = True
            obj.save(update_fields=['activo'])

    return OperarioTaller.objects.filter(activo=True).order_by('nombre')


def parse_fecha(fecha):
    """
    Convierte un string 'YYYY-MM-DD' o date a datetime.date.
    """
    if isinstance(fecha, (datetime.date, datetime.datetime)):
        return fecha.date() if isinstance(fecha, datetime.datetime) else fecha
    try:
        return datetime.datetime.strptime(str(fecha).strip(), '%Y-%m-%d').date()
    except Exception:
        return datetime.date.today()


def es_registro_descanso(reg):
    """
    Determina línea por línea si un registro específico corresponde al concepto de DESCANSO en EqualRP.
    Verifica con precisión sin asumir restas fijas ni confundir con términos como 'DESBASTE':
    - Orden de trabajo 4848 (orden interna de descanso en ABBAMAT)
    - Descripción de artículo (Articulod) contiene 'DESCANSO'
    - Código de artículo (Articulo) contiene 'DESCANSO'
    - Operación contiene 'DESCANSO'
    - Observaciones contiene 'DESCANSO'
    """
    if not reg:
        return False
    id_orden = str(reg.get('id_orden', '')).strip()
    if id_orden == '4848':
        return True
    art_desc = str(reg.get('articulo_desc', '')).strip().upper()
    if 'DESCANSO' in art_desc:
        return True
    art = str(reg.get('articulo', '')).strip().upper()
    if 'DESCANSO' in art:
        return True
    op = str(reg.get('operacion', '')).strip().upper()
    if 'DESCANSO' in op:
        return True
    obs = str(reg.get('observaciones', '')).strip().upper()
    if 'DESCANSO' in obs:
        return True
    return False


def calcular_timeline_visual(registros, baches, fecha, hora_inicio_taller=HORA_INICIO_TURNO, hora_fin_taller=HORA_FIN_TURNO):
    """
    Construye los bloques porcentuales para la barra de línea de tiempo visual (Gantt diario).
    Ventana de referencia visual: de 06:00 a 17:30 (690 minutos).
    """
    try:
        h_ini_dt = datetime.datetime.strptime(hora_inicio_taller, "%H:%M").time()
    except Exception:
        h_ini_dt = datetime.time(7, 0)

    # Punto base visual: 06:30 (para dar aire a los que entran temprano)
    base_minutos = 6 * 60 + 30  # 390 min desde medianoche
    total_minutos_escala = 11 * 60  # 660 min (hasta las 17:30)

    bloques = []

    # Bloques de tareas trabajadas y descansos
    colores_paleta = [
        '#3b82f6', '#06b6d4', '#10b981', '#6366f1', 
        '#8b5cf6', '#ec4899', '#14b8a6', '#f59e0b'
    ]

    for idx, reg in enumerate(registros):
        h_ini = reg.get('hora_inicio')
        h_fin = reg.get('hora_fin')
        if not h_ini or not h_fin:
            continue

        mins_ini = h_ini.hour * 60 + h_ini.minute
        mins_fin = h_fin.hour * 60 + h_fin.minute
        dur = max(mins_fin - mins_ini, 1)

        left_pct = max(0.0, min(100.0, ((mins_ini - base_minutos) / total_minutos_escala) * 100))
        width_pct = max(0.8, min(100.0 - left_pct, (dur / total_minutos_escala) * 100))

        es_desc = es_registro_descanso(reg)
        if es_desc:
            color = '#64748b'  # Gris azulado para descansos
            tipo_bloque = 'DESCANSO'
            titulo_bloque = f"Descanso ({int(dur)} min)"
        else:
            color = colores_paleta[idx % len(colores_paleta)]
            tipo_bloque = 'TAREA'
            id_orden = reg.get('id_orden', '')
            desc = reg.get('articulo_desc') or reg.get('operacion') or 'Tarea de taller'
            titulo_bloque = f"OT {id_orden} - {desc}"

        bloques.append({
            'tipo': tipo_bloque,
            'titulo': titulo_bloque,
            'id_orden': reg.get('id_orden', '--'),
            'articulo': reg.get('articulo', ''),
            'articulo_desc': reg.get('articulo_desc') or reg.get('operacion', ''),
            'operacion': reg.get('operacion', ''),
            'maquina': reg.get('maquina', 'Sin Máquina'),
            'hora_inicio': reg.get('hora_inicio_str', ''),
            'hora_fin': reg.get('hora_fin_str', ''),
            'duracion_min': round(dur, 1),
            'duracion_hs': round(dur / 60.0, 2),
            'cantidad_producida': reg.get('cantidad_producida', 0),
            'left_pct': round(left_pct, 2),
            'width_pct': round(width_pct, 2),
            'color': color,
            'es_descanso': es_desc,
        })

    # Bloques de baches / omisiones
    for b in baches:
        b_ini = b.get('dt_inicio')
        b_fin = b.get('dt_fin')
        dur = b.get('duracion_minutos', 0)
        if b_ini and b_fin and dur > 0:
            mins_ini = b_ini.hour * 60 + b_ini.minute
            mins_fin = b_fin.hour * 60 + b_fin.minute
            left_pct = max(0.0, min(100.0, ((mins_ini - base_minutos) / total_minutos_escala) * 100))
            width_pct = max(0.8, min(100.0 - left_pct, (dur / total_minutos_escala) * 100))

            es_omision_total = b.get('tipo') == 'OMISION_TOTAL'
            bloques.append({
                'tipo': 'BACHE',
                'titulo': f"Bache inactivo: {int(dur)} min ({b.get('inicio')} - {b.get('fin')})",
                'id_orden': '--',
                'articulo': '',
                'articulo_desc': b.get('descripcion', 'Bache sin actividad registrada'),
                'operacion': 'Bache / Inactividad',
                'maquina': 'Sin máquina',
                'hora_inicio': b.get('inicio', ''),
                'hora_fin': b.get('fin', ''),
                'duracion_min': round(dur, 1),
                'duracion_hs': round(dur / 60.0, 2),
                'cantidad_producida': 0,
                'left_pct': round(left_pct, 2),
                'width_pct': round(width_pct, 2),
                'color': '#ef4444' if es_omision_total else '#f97316',
                'es_descanso': False,
                'es_omision': es_omision_total,
            })

    # Ordenar cronológicamente los bloques de toda la jornada
    bloques.sort(key=lambda b: (b.get('left_pct', 0), b.get('hora_inicio', '')))
    return bloques


def detectar_baches_operario(registros, fecha, hora_inicio_str="07:00", hora_fin_str="16:30", tolerancia_min=15):
    """
    Detecta los baches u omisiones temporales de un operario:
    1. Si no tiene registros: Bache completo / Omisión total de la jornada.
    2. Si tiene registros:
       - Bache inicial si arranca significativamente después de hora_inicio_str (> tolerancia_min).
       - Baches intradía entre el fin de una tarea y el inicio de la siguiente (> tolerancia_min).
       - Bache final si termina significativamente antes de hora_fin_str (> tolerancia_min).
    """
    baches = []
    if not registros:
        # Omisión total de toda la jornada
        baches.append({
            'tipo': 'OMISION_TOTAL',
            'inicio': hora_inicio_str,
            'fin': hora_fin_str,
            'duracion_minutos': 510.0,  # 8.5 horas
            'descripcion': 'Omisión total: El operario no registró ninguna actividad de producción en la jornada.',
            'dt_inicio': datetime.datetime.combine(fecha, datetime.time(7, 0)),
            'dt_fin': datetime.datetime.combine(fecha, datetime.time(16, 30)),
        })
        return baches

    # Ordenar registros por hora de inicio cronológica
    regs_ordenados = sorted(
        [r for r in registros if r.get('hora_inicio') and r.get('hora_fin')],
        key=lambda x: x['hora_inicio']
    )

    if not regs_ordenados:
        return baches

    # Parse horario teórico de turno
    try:
        t_ini_parts = [int(p) for p in hora_inicio_str.split(':')]
        dt_turno_inicio = datetime.datetime.combine(fecha, datetime.time(t_ini_parts[0], t_ini_parts[1]))
    except Exception:
        dt_turno_inicio = datetime.datetime.combine(fecha, datetime.time(7, 0))

    try:
        t_fin_parts = [int(p) for p in hora_fin_str.split(':')]
        dt_turno_fin = datetime.datetime.combine(fecha, datetime.time(t_fin_parts[0], t_fin_parts[1]))
    except Exception:
        dt_turno_fin = datetime.datetime.combine(fecha, datetime.time(16, 30))

    # 1. Bache Inicial (desde inicio de turno hasta la primera tarea)
    primera_tarea = regs_ordenados[0]
    primera_hora_d = primera_tarea['hora_inicio']

    if primera_hora_d > dt_turno_inicio:
        diff_inicio_mins = (primera_hora_d - dt_turno_inicio).total_seconds() / 60.0
        if diff_inicio_mins >= tolerancia_min:
            baches.append({
                'tipo': 'BACHE_INICIAL',
                'inicio': dt_turno_inicio.strftime('%H:%M'),
                'fin': primera_hora_d.strftime('%H:%M'),
                'duracion_minutos': round(diff_inicio_mins, 1),
                'descripcion': f'Inicio demorado: {int(diff_inicio_mins)} min transcurridos antes de la 1ª orden registrada.',
                'dt_inicio': dt_turno_inicio,
                'dt_fin': primera_hora_d,
            })

    # 2. Baches Intradía (entre tareas consecutivas)
    for i in range(len(regs_ordenados) - 1):
        actual_fin = regs_ordenados[i]['hora_fin']
        siguiente_ini = regs_ordenados[i+1]['hora_inicio']

        if siguiente_ini > actual_fin:
            diff_mins = (siguiente_ini - actual_fin).total_seconds() / 60.0
            if diff_mins >= tolerancia_min:
                baches.append({
                    'tipo': 'INTRADIA',
                    'inicio': actual_fin.strftime('%H:%M'),
                    'fin': siguiente_ini.strftime('%H:%M'),
                    'duracion_minutos': round(diff_mins, 1),
                    'descripcion': f'Bache intradía de {int(diff_mins)} min sin producción registrada entre tareas.',
                    'dt_inicio': actual_fin,
                    'dt_fin': siguiente_ini,
                })

    # 3. Bache Final (desde el fin de la última tarea hasta el fin de turno)
    ultima_tarea = regs_ordenados[-1]
    ultima_hora_h = ultima_tarea['hora_fin']

    # Solo considerar bache final si el día auditado ya pasó o ya pasó la hora de fin
    ahora = datetime.datetime.now()
    if fecha < ahora.date() or (fecha == ahora.date() and ahora > dt_turno_fin):
        if ultima_hora_h < dt_turno_fin:
            diff_fin_mins = (dt_turno_fin - ultima_hora_h).total_seconds() / 60.0
            if diff_fin_mins >= tolerancia_min:
                baches.append({
                    'tipo': 'BACHE_FINAL',
                    'inicio': ultima_hora_h.strftime('%H:%M'),
                    'fin': dt_turno_fin.strftime('%H:%M'),
                    'duracion_minutos': round(diff_fin_mins, 1),
                    'descripcion': f'Cierre anticipado: {int(diff_fin_mins)} min restantes hasta el fin de jornada.',
                    'dt_inicio': ultima_hora_h,
                    'dt_fin': dt_turno_fin,
                })

    return baches


def auditar_jornada_produccion(fecha_input=None):
    """
    Función principal de auditoría analítica.
    Cruza la jornada laboral teórica de 8,5 horas con los registros reales de EqualRP.
    Retorna toda la matriz individual de cumplimiento, baches y métricas consolidadas.
    """
    fecha = parse_fecha(fecha_input)
    jornada_teorica_hs = JORNADA_TEORICA_HORAS
    minutos_teoricos_jornada = MINUTOS_TEORICOS_JORNADA
    tolerancia_bache = TOLERANCIA_BACHE_MINUTOS

    # 1. Asegurar catálogo EXCLUSIVO de operarios ACTIVOS en planta
    operarios_activos = OperarioTaller.objects.filter(activo=True)
    if not operarios_activos.exists():
        operarios_activos = sincronizar_operarios_taller()

    # Mapear ÚNICAMENTE operarios activos por id_concepto (excluye al 100% los inactivos)
    mapa_operarios = {op.id_concepto.strip(): op for op in operarios_activos}

    # 2. Consultar registros reales del ERP en modo solo lectura para la fecha
    registros_erp = get_registros_produccion_por_fecha(fecha)

    # Agrupar registros EXCLUSIVAMENTE para los operarios activos
    registros_por_op = {cid: [] for cid in mapa_operarios.keys()}
    for reg in registros_erp:
        cid = reg['id_concepto'].strip()
        # Descartar por completo cualquier registro de operarios no activos o dados de baja
        if cid in mapa_operarios:
            registros_por_op[cid].append(reg)

    # 3. Procesar individualmente a cada operario activo
    analisis_operarios = []
    notas_db = {
        n.id_concepto: n for n in NotaAuditoria.objects.filter(fecha=fecha)
    }

    # Acumuladores consolidados
    total_horas_registradas_planta = 0.0
    total_minutos_registrados_planta = 0.0
    total_horas_estandar_planta = 0.0
    total_piezas_planta = 0.0
    total_baches_planta_count = 0
    total_minutos_baches_planta = 0.0

    maquinas_utilizadas = {}
    operaciones_realizadas = {}

    for cid, op_obj in sorted(mapa_operarios.items(), key=lambda x: x[1].nombre):
        regs = registros_por_op.get(cid, [])

        # VALIDACIÓN CONDICIONAL Y DINÁMICA DEL DESCANSO LÍNEA POR LÍNEA:
        # Nunca se asume una resta fija. Se verifica línea por línea si el operario registró descanso.
        regs_productivos = []
        regs_descanso = []
        for r in regs:
            es_desc = es_registro_descanso(r)
            r['es_descanso'] = es_desc
            if es_desc:
                regs_descanso.append(r)
            else:
                regs_productivos.append(r)

        tiene_descanso = len(regs_descanso) > 0
        cant_descansos = len(regs_descanso)
        mins_descanso = sum(r['tiempo_minutos'] for r in regs_descanso)
        horas_descanso = round(mins_descanso / 60.0, 2)

        if tiene_descanso:
            # Si EXISTE el registro de descanso, se lo excluye únicamente a ese operario
            # del conteo de órdenes productivas y de las métricas de taller:
            cant_registros = len(regs_productivos)
            mins_reales = sum(r['tiempo_minutos'] for r in regs_productivos)
            horas_reales = round(mins_reales / 60.0, 2)
            horas_std = sum(r['tiempo_cotizado'] for r in regs_productivos)
            cant_piezas = sum(r['cantidad_producida'] for r in regs_productivos)
            regs_taller = regs_productivos
        else:
            # Si NO lo registró, sus órdenes y tiempos se calculan TAL CUAL COMO LOS CARGÓ,
            # sin aplicar ningún descuento genérico ni restas fijas:
            cant_registros = len(regs)
            mins_reales = sum(r['tiempo_minutos'] for r in regs)
            horas_reales = round(mins_reales / 60.0, 2)
            horas_std = sum(r['tiempo_cotizado'] for r in regs)
            cant_piezas = sum(r['cantidad_producida'] for r in regs)
            regs_taller = regs

        # Horario personalizado del operario según su esquema semanal rotativo
        horario_op_dia = op_obj.get_horario_dia(fecha.weekday()) if op_obj else None
        h_inicio_op = horario_op_dia.get('inicio', HORA_INICIO_TURNO) if horario_op_dia else HORA_INICIO_TURNO
        h_fin_op = horario_op_dia.get('fin', HORA_FIN_TURNO) if horario_op_dia else HORA_FIN_TURNO
        mins_teoricos_op = horario_op_dia.get('minutos_teoricos', minutos_teoricos_jornada) if horario_op_dia else minutos_teoricos_jornada
        horas_teoricas_op = horario_op_dia.get('horas_teoricas', jornada_teorica_hs) if horario_op_dia else jornada_teorica_hs

        # Rango horario registrado en planta
        primer_h = regs[0]['hora_inicio_str'] if regs else '--:--'
        ultimo_h = regs[-1]['hora_fin_str'] if regs else '--:--'

        # Índice de cumplimiento diario frente a su jornada teórica
        base_mins_calc = mins_teoricos_op if mins_teoricos_op > 0 else minutos_teoricos_jornada
        base_horas_calc = horas_teoricas_op if horas_teoricas_op > 0 else jornada_teorica_hs
        indice_cumplimiento = round((mins_reales / base_mins_calc) * 100.0, 1) if base_mins_calc > 0 else 0.0
        desvio_mins = round(mins_reales - base_mins_calc, 1)
        desvio_horas = round(horas_reales - base_horas_calc, 2)

        # Eficiencia técnica (Tiempo Estándar vs Tiempo Real de taller)
        eficiencia_tecnica = round((horas_std / horas_reales) * 100.0, 1) if horas_reales > 0 else 0.0

        # Detección de baches u omisiones (utiliza horario personalizado del operario para la jornada)
        baches = detectar_baches_operario(
            regs, 
            fecha, 
            hora_inicio_str=h_inicio_op, 
            hora_fin_str=h_fin_op, 
            tolerancia_min=tolerancia_bache
        )
        mins_en_baches = sum(b['duracion_minutos'] for b in baches)

        # Estado de auditoría
        if len(regs) == 0 or (cant_registros == 0 and not tiene_descanso):
            estado = 'SIN_REGISTRO'
            estado_label = 'Sin Registro (Omisión Total)'
            estado_badge_class = 'badge-danger'
            badge_icon = 'bi-x-circle-fill'
        elif indice_cumplimiento >= 95.0:
            estado = 'CUMPLIDO'
            estado_label = 'Jornada Cumplida'
            estado_badge_class = 'badge-success'
            badge_icon = 'bi-check-circle-fill'
        elif indice_cumplimiento >= 60.0:
            estado = 'PARCIAL'
            estado_label = 'Carga Parcial'
            estado_badge_class = 'badge-warning'
            badge_icon = 'bi-exclamation-triangle-fill'
        else:
            estado = 'CRITICO'
            estado_label = 'Carga Crítica / Baja'
            estado_badge_class = 'badge-orange'
            badge_icon = 'bi-exclamation-octagon-fill'

        # Construcción de timeline visual para la vista
        timeline_bloques = calcular_timeline_visual(
            regs, 
            baches, 
            fecha, 
            hora_inicio_taller=h_inicio_op, 
            hora_fin_taller=h_fin_op
        )

        nota_obj = notas_db.get(cid)

        # Métricas individuales de máquinas de taller (excluyen descanso de máquinas productivas)
        maquinas_op = {}
        for r in regs_taller:
            m = r.get('maquina', 'Sin Máquina')
            maquinas_op[m] = maquinas_op.get(m, 0.0) + r.get('tiempo_minutos', 0.0)
            maquinas_utilizadas[m] = maquinas_utilizadas.get(m, 0.0) + r.get('tiempo_minutos', 0.0)

            op_nombre = r.get('operacion', 'Operación')
            operaciones_realizadas[op_nombre] = operaciones_realizadas.get(op_nombre, 0.0) + r.get('tiempo_minutos', 0.0)

        item = {
            'id_concepto': cid,
            'nombre': op_obj.nombre,
            'puesto': op_obj.puesto_area or 'Operario Taller',
            'activo': op_obj.activo,
            'cantidad_registros': cant_registros,
            'cantidad_total_lineas': len(regs),
            'tiene_descanso': tiene_descanso,
            'minutos_descanso': round(mins_descanso, 1),
            'horas_descanso': horas_descanso,
            'cantidad_descansos': cant_descansos,
            'minutos_reales': mins_reales,
            'horas_reales': horas_reales,
            'horas_std': round(horas_std, 2),
            'eficiencia_tecnica': eficiencia_tecnica,
            'cantidad_piezas': cant_piezas,
            'primer_registro': primer_h,
            'ultimo_registro': ultimo_h,
            'indice_cumplimiento': indice_cumplimiento,
            'desvio_minutos': desvio_mins,
            'desvio_horas': desvio_horas,
            'estado': estado,
            'estado_label': estado_label,
            'estado_badge_class': estado_badge_class,
            'badge_icon': badge_icon,
            'baches': baches,
            'cantidad_baches': len(baches),
            'minutos_en_baches': round(mins_en_baches, 1),
            'horas_en_baches': round(mins_en_baches / 60.0, 2),
            'timeline_bloques': timeline_bloques,
            'registros': regs,
            'registros_productivos': regs_productivos,
            'registros_descanso': regs_descanso,
            'maquinas': maquinas_op,
            'nota': nota_obj,
        }

        analisis_operarios.append(item)

        # Acumular a totales de planta
        total_horas_registradas_planta += horas_reales
        total_minutos_registrados_planta += mins_reales
        total_horas_estandar_planta += horas_std
        total_piezas_planta += cant_piezas
        total_baches_planta_count += len(baches)
        total_minutos_baches_planta += mins_en_baches

    # 4. Estadísticas Consolidadas de Cobertura de Planta
    total_nomina = len(analisis_operarios)
    operarios_con_registro = sum(1 for op in analisis_operarios if op['cantidad_total_lineas'] > 0)
    operarios_omision_total = sum(1 for op in analisis_operarios if op['estado'] == 'SIN_REGISTRO')
    operarios_cumplidos = sum(1 for op in analisis_operarios if op['estado'] == 'CUMPLIDO')
    operarios_parciales = sum(1 for op in analisis_operarios if op['estado'] == 'PARCIAL')
    operarios_criticos = sum(1 for op in analisis_operarios if op['estado'] == 'CRITICO')

    horas_teoricas_planta = total_nomina * jornada_teorica_hs
    minutos_teoricos_planta = total_nomina * minutos_teoricos_jornada

    # Índice de cobertura global de planta (%)
    cobertura_global_porc = round(
        (total_minutos_registrados_planta / minutos_teoricos_planta) * 100.0, 1
    ) if minutos_teoricos_planta > 0 else 0.0

    # Tasa de adopción / carga efectiva de jornada obligatoria (≥ 80% de cumplimiento frente a 8,5 hs)
    UMBRAL_ADOPCION_ACEPTABLE = 80.0
    operarios_cumplen_adopcion = sum(1 for op in analisis_operarios if op['indice_cumplimiento'] >= UMBRAL_ADOPCION_ACEPTABLE)
    tasa_adopcion_porc = round(
        (operarios_cumplen_adopcion / total_nomina) * 100.0, 1
    ) if total_nomina > 0 else 0.0

    # Rendimiento técnico consolidado
    rendimiento_tecnico_global = round(
        (total_horas_estandar_planta / total_horas_registradas_planta) * 100.0, 1
    ) if total_horas_registradas_planta > 0 else 0.0

    promedio_horas_por_operario = round(
        total_horas_registradas_planta / operarios_con_registro, 2
    ) if operarios_con_registro > 0 else 0.0

    # Rankings
    ranking_cumplimiento = sorted(analisis_operarios, key=lambda x: x['indice_cumplimiento'], reverse=True)
    ranking_omisiones = [op for op in ranking_cumplimiento if op['estado'] == 'SIN_REGISTRO']

    # Top máquinas
    maquinas_top = sorted(
        [{'maquina': k, 'horas': round(v / 60.0, 2)} for k, v in maquinas_utilizadas.items()],
        key=lambda x: x['horas'],
        reverse=True
    )[:8]

    # Consolidado final
    resumen_consolidado = {
        'fecha': fecha,
        'fecha_str': fecha.strftime('%Y-%m-%d'),
        'fecha_formateada': fecha.strftime('%d/%m/%Y'),
        'jornada_teorica_hs': JORNADA_TEORICA_HORAS,
        'minutos_teoricos_jornada': MINUTOS_TEORICOS_JORNADA,
        'tolerancia_bache_minutos': TOLERANCIA_BACHE_MINUTOS,
        'hora_inicio_taller': HORA_INICIO_TURNO,
        'hora_fin_taller': HORA_FIN_TURNO,
        
        # Totales Nómina y Estados
        'total_nomina': total_nomina,
        'operarios_con_registro': operarios_con_registro,
        'operarios_omision_total': operarios_omision_total,
        'operarios_cumplidos': operarios_cumplidos,
        'operarios_parciales': operarios_parciales,
        'operarios_criticos': operarios_criticos,
        
        # Tiempos Totales
        'horas_totales_registradas': round(total_horas_registradas_planta, 2),
        'minutos_totales_registrados': round(total_minutos_registrados_planta, 1),
        'horas_totales_teoricas': round(horas_teoricas_planta, 2),
        'horas_totales_estandar': round(total_horas_estandar_planta, 2),
        'total_piezas_planta': total_piezas_planta,
        'promedio_horas_por_operario': promedio_horas_por_operario,
        
        # Baches Totales
        'total_baches_count': total_baches_planta_count,
        'total_horas_baches': round(total_minutos_baches_planta / 60.0, 2),
        
        # Indicadores Clave de Rendimiento (KPIs)
        'indice_cobertura_global': cobertura_global_porc,
        'tasa_adopcion_registro': tasa_adopcion_porc,
        'operarios_cumplen_adopcion': operarios_cumplen_adopcion,
        'umbral_adopcion_porc': UMBRAL_ADOPCION_ACEPTABLE,
        'rendimiento_tecnico_global': rendimiento_tecnico_global,
        
        # Desglose por máquinas
        'maquinas_top': maquinas_top,
    }

    return {
        'resumen': resumen_consolidado,
        'operarios': analisis_operarios,
        'ranking': ranking_cumplimiento,
        'omisiones': ranking_omisiones,
    }


def auditar_periodo_produccion(fecha_desde_input=None, fecha_hasta_input=None):
    """
    Función analítica para consolidar la producción en un intervalo de fechas (Desde / Hasta).
    Calcula horas reales acumuladas, horas teóricas basadas en días hábiles (8,5 hs/día),
    índices de cobertura global y desgloses individuales para todos los operarios activos.
    Garantiza que la nómina activa de planta completa esté incluida en el ranking sin recortes.
    """
    fecha_desde = parse_fecha(fecha_desde_input)
    fecha_hasta = parse_fecha(fecha_hasta_input) if fecha_hasta_input else fecha_desde

    if fecha_desde > fecha_hasta:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    jornada_teorica_hs = JORNADA_TEORICA_HORAS
    tolerancia_bache = TOLERANCIA_BACHE_MINUTOS

    # Calcular días hábiles (Lunes a Viernes) en el intervalo
    dias_totales = (fecha_hasta - fecha_desde).days + 1
    dias_habiles = 0
    curr = fecha_desde
    while curr <= fecha_hasta:
        if curr.weekday() < 5:  # Lunes a Viernes
            dias_habiles += 1
        curr += datetime.timedelta(days=1)
    
    # Si el intervalo es de fin de semana o 0 días hábiles, garantizar al menos 1 día como base
    if dias_habiles == 0:
        dias_habiles = max(1, dias_totales)

    # Horas teóricas por operario en el periodo
    horas_teoricas_operario = dias_habiles * jornada_teorica_hs
    minutos_teoricos_operario = horas_teoricas_operario * 60.0

    # 1. Asegurar catálogo EXCLUSIVO de operarios ACTIVOS en planta
    operarios_activos = OperarioTaller.objects.filter(activo=True)
    if not operarios_activos.exists():
        operarios_activos = sincronizar_operarios_taller()

    mapa_operarios = {op.id_concepto.strip(): op for op in operarios_activos}

    # 2. Consultar registros reales del ERP en modo solo lectura para el rango
    if fecha_desde == fecha_hasta:
        registros_erp = get_registros_produccion_por_fecha(fecha_desde)
    else:
        registros_erp = get_registros_produccion_por_rango(fecha_desde, fecha_hasta)

    # Agrupar registros EXCLUSIVAMENTE para los operarios activos
    registros_por_op = {cid: [] for cid in mapa_operarios.keys()}
    for reg in registros_erp:
        cid = reg['id_concepto'].strip()
        if cid in mapa_operarios:
            registros_por_op[cid].append(reg)

    # 3. Procesar individualmente a cada operario activo
    analisis_operarios = []
    notas_db = {
        n.id_concepto: n for n in NotaAuditoria.objects.filter(fecha__gte=fecha_desde, fecha__lte=fecha_hasta)
    }

    total_horas_registradas_planta = 0.0
    total_minutos_registrados_planta = 0.0
    total_horas_estandar_planta = 0.0
    total_piezas_planta = 0.0
    total_baches_planta_count = 0
    total_minutos_baches_planta = 0.0

    maquinas_utilizadas = {}
    operaciones_realizadas = {}

    for cid, op_obj in sorted(mapa_operarios.items(), key=lambda x: x[1].nombre):
        regs = registros_por_op.get(cid, [])

        # VALIDACIÓN CONDICIONAL Y DINÁMICA DEL DESCANSO LÍNEA POR LÍNEA:
        regs_productivos = []
        regs_descanso = []
        for r in regs:
            es_desc = es_registro_descanso(r)
            r['es_descanso'] = es_desc
            if es_desc:
                regs_descanso.append(r)
            else:
                regs_productivos.append(r)

        tiene_descanso = len(regs_descanso) > 0
        cant_descansos = len(regs_descanso)
        mins_descanso = sum(r['tiempo_minutos'] for r in regs_descanso)
        horas_descanso = round(mins_descanso / 60.0, 2)

        if tiene_descanso:
            # Si EXISTE el registro de descanso, se lo excluye únicamente a ese operario
            # del conteo de órdenes productivas y de las métricas de taller:
            cant_registros = len(regs_productivos)
            mins_reales = sum(r['tiempo_minutos'] for r in regs_productivos)
            horas_reales = round(mins_reales / 60.0, 2)
            horas_std = sum(r['tiempo_cotizado'] for r in regs_productivos)
            cant_piezas = sum(r['cantidad_producida'] for r in regs_productivos)
            regs_taller = regs_productivos
        else:
            # Si NO lo registró, sus órdenes y tiempos se calculan TAL CUAL COMO LOS CARGÓ,
            # sin aplicar ningún descuento genérico ni restas fijas:
            cant_registros = len(regs)
            mins_reales = sum(r['tiempo_minutos'] for r in regs)
            horas_reales = round(mins_reales / 60.0, 2)
            horas_std = sum(r['tiempo_cotizado'] for r in regs)
            cant_piezas = sum(r['cantidad_producida'] for r in regs)
            regs_taller = regs

        # Días con actividad registrada en el periodo
        dias_con_actividad = len(set(
            (r['fecha'].strftime('%Y-%m-%d') if hasattr(r.get('fecha'), 'strftime') else str(r.get('fecha', '')))
            for r in regs if r.get('fecha')
        ))

        # Índice de cumplimiento acumulado frente a la jornada teórica del periodo
        indice_cumplimiento = round((mins_reales / minutos_teoricos_operario) * 100.0, 1) if minutos_teoricos_operario > 0 else 0.0
        desvio_horas = round(horas_reales - horas_teoricas_operario, 2)
        desvio_mins = round(mins_reales - minutos_teoricos_operario, 1)

        # Eficiencia técnica
        eficiencia_tecnica = round((horas_std / horas_reales) * 100.0, 1) if horas_reales > 0 else 0.0

        # Baches: agrupar registros por día y detectar baches en cada día trabajado (incluye descanso para evitar baches falsos)
        baches_totales_op = []
        regs_por_dia = {}
        for r in regs:
            f_k = r['fecha'].date() if isinstance(r.get('fecha'), datetime.datetime) else r.get('fecha')
            if not f_k:
                f_k = fecha_desde
            regs_por_dia.setdefault(f_k, []).append(r)

        for f_dia, r_dia in regs_por_dia.items():
            h_op_dia = op_obj.get_horario_dia(f_dia.weekday()) if op_obj else None
            h_ini_dia = h_op_dia.get('inicio', HORA_INICIO_TURNO) if h_op_dia else HORA_INICIO_TURNO
            h_fin_dia = h_op_dia.get('fin', HORA_FIN_TURNO) if h_op_dia else HORA_FIN_TURNO
            b_dia = detectar_baches_operario(
                r_dia,
                f_dia,
                hora_inicio_str=h_ini_dia,
                hora_fin_str=h_fin_dia,
                tolerancia_min=tolerancia_bache
            )
            baches_totales_op.extend(b_dia)

        mins_en_baches = sum(b['duracion_minutos'] for b in baches_totales_op)

        # Estado de auditoría
        if len(regs) == 0 or (cant_registros == 0 and not tiene_descanso):
            estado = 'SIN_REGISTRO'
            estado_label = 'Sin Registro (Omisión)'
            estado_badge_class = 'badge-danger'
            badge_icon = 'bi-x-circle-fill'
        elif indice_cumplimiento >= 95.0:
            estado = 'CUMPLIDO'
            estado_label = 'Cumplido'
            estado_badge_class = 'badge-success'
            badge_icon = 'bi-check-circle-fill'
        elif indice_cumplimiento >= 60.0:
            estado = 'PARCIAL'
            estado_label = 'Carga Parcial'
            estado_badge_class = 'badge-warning'
            badge_icon = 'bi-exclamation-triangle-fill'
        else:
            estado = 'CRITICO'
            estado_label = 'Carga Crítica / Baja'
            estado_badge_class = 'badge-orange'
            badge_icon = 'bi-exclamation-octagon-fill'

        # Máquinas del operario (excluyen descanso de máquinas de producción)
        maquinas_op = {}
        for r in regs_taller:
            m = r.get('maquina', 'Sin Máquina')
            maquinas_op[m] = maquinas_op.get(m, 0.0) + r.get('tiempo_minutos', 0.0)
            maquinas_utilizadas[m] = maquinas_utilizadas.get(m, 0.0) + r.get('tiempo_minutos', 0.0)

            op_nombre = r.get('operacion', 'Operación')
            operaciones_realizadas[op_nombre] = operaciones_realizadas.get(op_nombre, 0.0) + r.get('tiempo_minutos', 0.0)

        timeline_bloques = []
        timelines_por_dia = []
        if fecha_desde == fecha_hasta and regs:
            timeline_bloques = calcular_timeline_visual(
                regs,
                baches_totales_op,
                fecha_desde,
                hora_inicio_taller=HORA_INICIO_TURNO,
                hora_fin_taller=HORA_FIN_TURNO
            )
        elif regs:
            # Agrupar registros y baches por día en rangos multi-día
            regs_por_dia = {}
            for r in regs:
                f_reg = r.get('fecha')
                if isinstance(f_reg, datetime.datetime):
                    f_reg = f_reg.date()
                elif isinstance(f_reg, str):
                    try:
                        f_reg = datetime.datetime.strptime(f_reg[:10], '%Y-%m-%d').date()
                    except Exception:
                        f_reg = fecha_hasta
                elif not isinstance(f_reg, datetime.date):
                    f_reg = r.get('hora_inicio').date() if r.get('hora_inicio') else fecha_hasta
                regs_por_dia.setdefault(f_reg, []).append(r)

            baches_por_dia = {}
            for b in baches_totales_op:
                f_b = b.get('fecha')
                if isinstance(f_b, datetime.datetime):
                    f_b = f_b.date()
                elif isinstance(f_b, str):
                    try:
                        f_b = datetime.datetime.strptime(f_b[:10], '%Y-%m-%d').date()
                    except Exception:
                        f_b = fecha_hasta
                elif not isinstance(f_b, datetime.date):
                    f_b = b.get('dt_inicio').date() if b.get('dt_inicio') else fecha_hasta
                baches_por_dia.setdefault(f_b, []).append(b)

            for f_d in sorted(regs_por_dia.keys(), reverse=True):
                bloques_dia = calcular_timeline_visual(
                    regs_por_dia[f_d],
                    baches_por_dia.get(f_d, []),
                    f_d,
                    hora_inicio_taller=HORA_INICIO_TURNO,
                    hora_fin_taller=HORA_FIN_TURNO
                )
                timelines_por_dia.append({
                    'fecha': f_d,
                    'fecha_str': f_d.strftime('%d/%m/%Y'),
                    'bloques': bloques_dia,
                    'total_horas': round(sum(r.get('tiempo_minutos', 0) for r in regs_por_dia[f_d] if not es_registro_descanso(r)) / 60.0, 2),
                    'cant_tareas': sum(1 for r in regs_por_dia[f_d] if not es_registro_descanso(r)),
                })
            if timelines_por_dia:
                timeline_bloques = timelines_por_dia[0]['bloques']

        promedio_diario_op = round(horas_reales / dias_habiles, 2) if dias_habiles > 0 else 0.0

        primer_h = regs[0]['hora_inicio_str'] if regs else '--:--'
        ultimo_h = regs[-1]['hora_fin_str'] if regs else '--:--'

        item = {
            'id_concepto': cid,
            'nombre': op_obj.nombre,
            'puesto': op_obj.puesto_area or 'Operario Taller',
            'activo': op_obj.activo,
            'cantidad_registros': cant_registros,
            'cantidad_total_lineas': len(regs),
            'tiene_descanso': tiene_descanso,
            'minutos_descanso': round(mins_descanso, 1),
            'horas_descanso': horas_descanso,
            'cantidad_descansos': cant_descansos,
            'minutos_reales': mins_reales,
            'horas_reales': horas_reales,
            'horas_std': round(horas_std, 2),
            'eficiencia_tecnica': eficiencia_tecnica,
            'cantidad_piezas': cant_piezas,
            'dias_con_actividad': dias_con_actividad,
            'promedio_diario_horas': promedio_diario_op,
            'horas_teoricas': round(horas_teoricas_operario, 2),
            'indice_cumplimiento': indice_cumplimiento,
            'desvio_minutos': desvio_mins,
            'desvio_horas': desvio_horas,
            'primer_registro': primer_h,
            'ultimo_registro': ultimo_h,
            'estado': estado,
            'estado_label': estado_label,
            'estado_badge_class': estado_badge_class,
            'badge_icon': badge_icon,
            'baches': baches_totales_op,
            'cantidad_baches': len(baches_totales_op),
            'minutos_en_baches': round(mins_en_baches, 1),
            'horas_en_baches': round(mins_en_baches / 60.0, 2),
            'timeline_bloques': timeline_bloques,
            'timelines_por_dia': timelines_por_dia,
            'registros': regs,
            'registros_productivos': regs_productivos,
            'registros_descanso': regs_descanso,
            'maquinas': maquinas_op,
            'nota': notas_db.get(cid),
        }
        analisis_operarios.append(item)

        total_horas_registradas_planta += horas_reales
        total_minutos_registrados_planta += mins_reales
        total_horas_estandar_planta += horas_std
        total_piezas_planta += cant_piezas
        total_baches_planta_count += len(baches_totales_op)
        total_minutos_baches_planta += mins_en_baches

    # 4. Estadísticas Consolidadas de Cobertura de Planta
    total_nomina = len(analisis_operarios)
    operarios_con_registro = sum(1 for op in analisis_operarios if op['cantidad_total_lineas'] > 0)
    operarios_omision_total = sum(1 for op in analisis_operarios if op['estado'] == 'SIN_REGISTRO')
    operarios_cumplidos = sum(1 for op in analisis_operarios if op['estado'] == 'CUMPLIDO')
    operarios_parciales = sum(1 for op in analisis_operarios if op['estado'] == 'PARCIAL')
    operarios_criticos = sum(1 for op in analisis_operarios if op['estado'] == 'CRITICO')

    horas_teoricas_planta = total_nomina * horas_teoricas_operario
    minutos_teoricos_planta = total_nomina * minutos_teoricos_operario

    cobertura_global_porc = round(
        (total_minutos_registrados_planta / minutos_teoricos_planta) * 100.0, 1
    ) if minutos_teoricos_planta > 0 else 0.0

    # Tasa de adopción / carga efectiva acumulada (≥ 80% de cumplimiento de jornada teórica acumulada)
    UMBRAL_ADOPCION_ACEPTABLE = 80.0
    operarios_cumplen_adopcion = sum(1 for op in analisis_operarios if op['indice_cumplimiento'] >= UMBRAL_ADOPCION_ACEPTABLE)
    tasa_adopcion_porc = round(
        (operarios_cumplen_adopcion / total_nomina) * 100.0, 1
    ) if total_nomina > 0 else 0.0

    rendimiento_tecnico_global = round(
        (total_horas_estandar_planta / total_horas_registradas_planta) * 100.0, 1
    ) if total_horas_registradas_planta > 0 else 0.0

    promedio_horas_por_operario = round(
        total_horas_registradas_planta / operarios_con_registro, 2
    ) if operarios_con_registro > 0 else 0.0

    promedio_diario_por_operario = round(
        promedio_horas_por_operario / dias_habiles, 2
    ) if dias_habiles > 0 else 0.0

    # Rankings completos (SIN CORTAR NINGUNO: nómina activa íntegra)
    ranking_cumplimiento = sorted(analisis_operarios, key=lambda x: (x['horas_reales'], x['indice_cumplimiento']), reverse=True)
    ranking_omisiones = [op for op in ranking_cumplimiento if op['estado'] == 'SIN_REGISTRO']

    maquinas_top = sorted(
        [{'maquina': k, 'horas': round(v / 60.0, 2)} for k, v in maquinas_utilizadas.items()],
        key=lambda x: x['horas'],
        reverse=True
    )[:8]

    fecha_formateada = f"{fecha_desde.strftime('%d/%m/%Y')} al {fecha_hasta.strftime('%d/%m/%Y')}" if fecha_desde != fecha_hasta else fecha_desde.strftime('%d/%m/%Y')

    resumen_consolidado = {
        'fecha': fecha_hasta,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'fecha_str': fecha_hasta.strftime('%Y-%m-%d'),
        'fecha_desde_str': fecha_desde.strftime('%Y-%m-%d'),
        'fecha_hasta_str': fecha_hasta.strftime('%Y-%m-%d'),
        'fecha_desde_formateada': fecha_desde.strftime('%d/%m/%Y'),
        'fecha_hasta_formateada': fecha_hasta.strftime('%d/%m/%Y'),
        'fecha_formateada': fecha_formateada,
        'es_mismo_dia': fecha_desde == fecha_hasta,
        'dias_habiles': dias_habiles,
        'dias_totales': dias_totales,
        'jornada_teorica_hs': JORNADA_TEORICA_HORAS,
        'minutos_teoricos_jornada': MINUTOS_TEORICOS_JORNADA,
        'horas_teoricas_operario': round(horas_teoricas_operario, 2),
        'minutos_teoricos_operario': round(minutos_teoricos_operario, 1),
        'tolerancia_bache_minutos': TOLERANCIA_BACHE_MINUTOS,
        'hora_inicio_taller': HORA_INICIO_TURNO,
        'hora_fin_taller': HORA_FIN_TURNO,

        'total_nomina': total_nomina,
        'operarios_con_registro': operarios_con_registro,
        'operarios_omision_total': operarios_omision_total,
        'operarios_cumplidos': operarios_cumplidos,
        'operarios_parciales': operarios_parciales,
        'operarios_criticos': operarios_criticos,

        'horas_totales_registradas': round(total_horas_registradas_planta, 2),
        'minutos_totales_registrados': round(total_minutos_registrados_planta, 1),
        'horas_totales_teoricas': round(horas_teoricas_planta, 2),
        'horas_totales_estandar': round(total_horas_estandar_planta, 2),
        'total_piezas_planta': total_piezas_planta,
        'promedio_horas_por_operario': promedio_horas_por_operario,
        'promedio_diario_por_operario': promedio_diario_por_operario,

        'total_baches_count': total_baches_planta_count,
        'total_horas_baches': round(total_minutos_baches_planta / 60.0, 2),

        'indice_cobertura_global': cobertura_global_porc,
        'tasa_adopcion_registro': tasa_adopcion_porc,
        'operarios_cumplen_adopcion': operarios_cumplen_adopcion,
        'umbral_adopcion_porc': UMBRAL_ADOPCION_ACEPTABLE,
        'rendimiento_tecnico_global': rendimiento_tecnico_global,

        'maquinas_top': maquinas_top,
    }

    return {
        'resumen': resumen_consolidado,
        'operarios': analisis_operarios,
        'ranking': ranking_cumplimiento,
        'omisiones': ranking_omisiones,
    }

