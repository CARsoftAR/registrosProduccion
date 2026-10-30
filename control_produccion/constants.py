"""
Constantes fijas del motor de auditoría y cálculo de producción ABBAMAT.
Parámetros inmutables de planta definidos de forma estática en el backend,
eliminando cualquier dependencia de tablas o pantallas de configuración manuales.
"""

# Jornada laboral teórica diaria obligatoria
JORNADA_TEORICA_HORAS = 8.5
MINUTOS_TEORICOS_JORNADA = 510.0  # 8.5 * 60 minutos

# Horarios estándar de turno de taller
HORA_INICIO_TURNO = "07:00"
HORA_FIN_TURNO = "16:00"

# Detección de baches e inactividad intradía
TOLERANCIA_BACHE_MINUTOS = 15

# Tasa de adopción / cumplimiento aceptable de jornada
PORCENTAJE_ADOPCION_MINIMO = 80.0
HORAS_MINIMAS_ADOPCION = 6.8  # 80% de 8.5 hs
