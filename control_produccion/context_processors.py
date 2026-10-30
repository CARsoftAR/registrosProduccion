import datetime


def fechas_auditoria_context(request):
    """
    Context processor global para asegurar que las variables de fecha básicas
    estén siempre disponibles en todas las plantillas que extienden base.html,
    evitando excepciones VariableDoesNotExist en pantallas como Operarios o Parámetros.
    
    Si una vista (como Dashboard o Control de Producción) inyecta sus propias fechas,
    el contexto de la vista tiene precedencia y sobrescribe estos valores por defecto.
    """
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    manana = hoy + datetime.timedelta(days=1)
    hoy_str = hoy.strftime('%Y-%m-%d')

    return {
        'fecha_str': hoy_str,
        'fecha_desde_str': hoy_str,
        'fecha_hasta_str': hoy_str,
        'fecha_ayer': ayer.strftime('%Y-%m-%d'),
        'fecha_manana': manana.strftime('%Y-%m-%d'),
        'es_hoy': True,
        'operario_filtro': request.GET.get('operario', '').strip(),
    }
