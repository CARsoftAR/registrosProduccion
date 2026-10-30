"""
Script de Inicialización del Módulo de Auditoría de Producción ABBAMAT.
1. Crea los parámetros por defecto de planta (Jornada teórica: 8.5 hs).
2. Sincroniza los operarios desde la tabla TMAN014 de EqualRP.
3. Activa los operarios de taller habituales.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from control_produccion.models import ParametroTaller, OperarioTaller
from control_produccion.services.analytics_service import sincronizar_operarios_taller

def init():
    print("=== INICIALIZANDO MÓDULO DE CONTROL DE PRODUCCIÓN ===")
    
    # 1. Parámetros
    param = ParametroTaller.get_solo()
    print(f"[OK] Parámetros de Taller configurados: Jornada = {param.jornada_teorica_horas} hs | Tolerancia bache = {param.tolerancia_bache_minutos} min")

    # 2. Sincronizar operarios
    print("[...] Sincronizando operarios desde TMAN014 de EqualRP (Modo Solo Lectura)...")
    sincronizar_operarios_taller()
    
    activos = OperarioTaller.objects.filter(activo=True)
    inactivos = OperarioTaller.objects.filter(activo=False)
    print(f"[OK] Operarios Activos en Auditoría: {activos.count()}")
    print(f"[OK] Otros conceptos en catálogo: {inactivos.count()}")
    
    for op in activos:
        print(f"  - Legajo {op.id_concepto:>4}: {op.nombre}")

if __name__ == '__main__':
    init()
