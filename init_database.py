"""
Script de Inicialización del Módulo de Auditoría de Producción ABBAMAT.
Configura exclusivamente la Base de Datos Local con:
1. Parámetros fijos de planta (Jornada teórica: 8.5 hs, tolerancia: 15 min).
2. Los 14 operarios activos de la nómina de planta con sus esquemas rotativos.
Sin dependencias de red ni consumo de endpoints externos para la nómina.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from control_produccion.models import ParametroTaller, OperarioTaller

OPERARIOS_14 = [
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

ESQUEMA_BASE = {
    'lunes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
    'martes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
    'miercoles': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
    'jueves': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
    'viernes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
    'sabado': {'activo': False, 'inicio': '07:00', 'fin': '12:00'},
    'domingo': {'activo': False, 'inicio': '07:00', 'fin': '12:00'},
}

def init():
    print("=== INICIALIZANDO BASE DE DATOS LOCAL EXCLUSIVA ===")
    
    # 1. Parámetros locales
    param = ParametroTaller.get_solo()
    param.jornada_teorica_horas = 8.5
    param.tolerancia_bache_minutos = 15
    param.hora_inicio_turno = '07:00'
    param.hora_fin_turno = '16:00'
    param.save()
    print(f"[OK] Parámetros locales configurados: Jornada = {param.jornada_teorica_horas} hs | Tolerancia bache = {param.tolerancia_bache_minutos} min")

    # 2. Cargar nómina de 14 operarios activos
    ids_14 = [op["id_concepto"] for op in OPERARIOS_14]
    OperarioTaller.objects.exclude(id_concepto__in=ids_14).delete()

    for data in OPERARIOS_14:
        op, created = OperarioTaller.objects.get_or_create(
            id_concepto=data["id_concepto"],
            defaults={
                "nombre": data["nombre"],
                "categoria": data["categoria"],
                "es_mensual": data["es_mensual"],
                "activo": True,
                "horario_rotativo": ESQUEMA_BASE,
            }
        )
        if not created:
            op.nombre = data["nombre"]
            op.categoria = data["categoria"]
            op.es_mensual = data["es_mensual"]
            op.activo = True
            if not op.horario_rotativo:
                op.horario_rotativo = ESQUEMA_BASE
            op.save()

    activos = OperarioTaller.objects.filter(activo=True)
    print(f"[OK] Operarios Activos en Nómina Local: {activos.count()}")
    for op in activos:
        print(f"  - Legajo {op.id_concepto:>4}: {op.nombre} ({op.categoria})")

if __name__ == '__main__':
    init()
