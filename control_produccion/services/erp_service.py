"""
Servicio de Acceso en Modo Solo Lectura a la Base de Datos del ERP (EqualRP_Prod_Master).
Conexión directa vía pyodbc sin ORM para máxima velocidad, aislamiento y seguridad.
"""

import logging
import datetime
import pyodbc
from django.conf import settings

logger = logging.getLogger(__name__)

# Cache de driver funcional para evitar reintentar en cada consulta
_WORKING_DRIVER = None


def get_erp_connection():
    """
    Obtiene una conexión activa y en modo SOLO LECTURA a la base de datos del ERP.
    Prueba el driver configurado y realiza fallback automático si es necesario.
    """
    global _WORKING_DRIVER

    db_cfg = settings.ERP_DB_CONFIG
    host = db_cfg.get('HOST', '192.168.88.12')
    db_name = db_cfg.get('NAME', 'EqualRP_Prod_Master')
    user = db_cfg.get('USER', 'tablero')
    password = db_cfg.get('PASSWORD', 'tablero2019')
    configured_driver = db_cfg.get('DRIVER', 'SQL Server Native Client 11.0')

    drivers_to_try = []
    if _WORKING_DRIVER:
        drivers_to_try.append(_WORKING_DRIVER)
    if configured_driver and configured_driver not in drivers_to_try:
        drivers_to_try.append(configured_driver)

    # Agregar drivers comunes instalados en el sistema
    available = pyodbc.drivers()
    for d in ['SQL Server Native Client 11.0', 'ODBC Driver 17 for SQL Server', 'ODBC Driver 18 for SQL Server', 'SQL Server']:
        if d in available and d not in drivers_to_try:
            drivers_to_try.append(d)

    last_error = None
    for driver in drivers_to_try:
        try:
            conn_str = (
                f"DRIVER={{{driver}}};"
                f"SERVER={host};"
                f"DATABASE={db_name};"
                f"UID={user};"
                f"PWD={password};"
                f"ReadOnly=1;"
                f"APP=ABBAMAT_Control_Produccion;"
            )
            # Timeout corto de 5s para evitar bloqueos
            conn = pyodbc.connect(conn_str, timeout=5)
            # Modo autocommit y solo lectura para evitar transacciones abiertas
            conn.autocommit = True
            _WORKING_DRIVER = driver
            return conn
        except Exception as e:
            last_error = e
            logger.warning(f"Fallo conexión ERP con driver '{driver}': {e}")

    logger.error(f"No se pudo conectar a la base de datos del ERP: {last_error}")
    raise ConnectionError(f"Error al conectar con base de datos del ERP: {last_error}")


def get_all_taller_concepts_from_erp():
    """
    Obtiene el catálogo completo de conceptos / operarios de taller desde TMAN014.
    Filtra conceptos de baja y conceptos abstractos (roles tipo P1000).
    """
    sql = """
        SELECT 
            LTRIM(RTRIM(IDCONCEPTO)) AS id_concepto,
            LTRIM(RTRIM(CONCEPTO)) AS concepto,
            ISNULL(Baja, 0) AS baja
        FROM TMAN014
        WHERE (Baja IS NULL OR Baja = 0)
          AND IDCONCEPTO NOT LIKE 'P%'
          AND IDCONCEPTO NOT IN ('888', '1')
        ORDER BY 
            CASE WHEN ISNUMERIC(IDCONCEPTO) = 1 THEN CAST(IDCONCEPTO AS INT) ELSE 9999 END,
            CONCEPTO
    """
    conceptos = []
    try:
        with get_erp_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            for row in cursor.fetchall():
                conceptos.append({
                    'id_concepto': str(row[0]),
                    'nombre': str(row[1]) if row[1] else '',
                    'baja': bool(row[2])
                })
    except Exception as e:
        logger.error(f"Error al consultar conceptos de TMAN014: {e}")
    return conceptos


def get_registros_produccion_por_fecha(fecha):
    """
    Consulta en la vista V_TMAN todos los registros de producción para una fecha específica.
    Retorna lista de diccionarios con horas, duraciones, órdenes, artículos y máquinas.
    """
    if isinstance(fecha, (datetime.date, datetime.datetime)):
        fecha_str = fecha.strftime('%Y-%m-%d')
    else:
        fecha_str = str(fecha).strip()

    sql = """
        SELECT 
            HAP_ROW_ID,
            IDORDEN,
            LTRIM(RTRIM(IDCONCEPTO)) AS id_concepto,
            LTRIM(RTRIM(CONCEPTO)) AS concepto,
            FECHA,
            HORA_D,
            HORA_H,
            ISNULL(Tiempo_minutos, 0) AS tiempo_minutos,
            ISNULL(Tiempo_cotizado, 0) AS tiempo_cotizado,
            ISNULL(Tiempo_cotizado_individual, 0) AS tiempo_cotizado_ind,
            ISNULL(Cantidad_producida, 0) AS cantidad_producida,
            LTRIM(RTRIM(ISNULL(IDMAQUINA, ''))) AS id_maquina,
            LTRIM(RTRIM(ISNULL(MaquinaD, ''))) AS maquina,
            LTRIM(RTRIM(ISNULL(IDOPERACION, ''))) AS id_operacion,
            LTRIM(RTRIM(ISNULL(OPERACION, ''))) AS operacion,
            LTRIM(RTRIM(ISNULL(Articulo, ''))) AS articulo,
            LTRIM(RTRIM(ISNULL(Articulod, ''))) AS articulo_desc,
            LTRIM(RTRIM(ISNULL(Formula, ''))) AS formula,
            LTRIM(RTRIM(ISNULL(OBS, ''))) AS observaciones,
            ISNULL(Es_proceso, 0) AS es_proceso,
            ISNULL(Es_programado, 0) AS es_programado
        FROM V_TMAN
        WHERE CONVERT(date, FECHA) = ?
        ORDER BY LTRIM(RTRIM(IDCONCEPTO)), HORA_D ASC
    """
    registros = []
    try:
        with get_erp_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (fecha_str,))
            for row in cursor.fetchall():
                hora_d = row[5]
                hora_h = row[6]
                minutos = float(row[7])

                # Si minutos viene en 0 pero hora_d y hora_h están presentes, calcularlo
                if minutos <= 0 and hora_d and hora_h:
                    diff_mins = (hora_h - hora_d).total_seconds() / 60.0
                    if diff_mins > 0:
                        minutos = diff_mins

                registros.append({
                    'row_id': row[0],
                    'id_orden': row[1],
                    'id_concepto': str(row[2]) if row[2] else '',
                    'concepto': str(row[3]) if row[3] else '',
                    'fecha': row[4],
                    'hora_inicio': hora_d,
                    'hora_fin': hora_h,
                    'hora_inicio_str': hora_d.strftime('%H:%M') if hora_d else '',
                    'hora_fin_str': hora_h.strftime('%H:%M') if hora_h else '',
                    'tiempo_minutos': round(minutos, 2),
                    'tiempo_horas': round(minutos / 60.0, 2),
                    'tiempo_cotizado': round(float(row[8]), 4),
                    'tiempo_cotizado_minutos': round(float(row[8]) * 60.0, 2),
                    'cantidad_producida': float(row[10]),
                    'id_maquina': str(row[11]),
                    'maquina': str(row[12]) if row[12] else (str(row[11]) if row[11] else 'Sin Máquina'),
                    'id_operacion': str(row[13]),
                    'operacion': str(row[14]) if row[14] else 'Operación',
                    'articulo': str(row[15]),
                    'articulo_desc': str(row[16]),
                    'formula': str(row[17]),
                    'observaciones': str(row[18]),
                    'es_proceso': bool(row[19]),
                    'es_programado': bool(row[20]),
                })
    except Exception as e:
        logger.error(f"Error al consultar V_TMAN para fecha {fecha_str}: {e}")
    return registros


def get_detalle_operario_fecha(id_concepto, fecha):
    """
    Retorna los registros cronológicos de un operario específico en una fecha.
    """
    todos = get_registros_produccion_por_fecha(fecha)
    return [r for r in todos if str(r['id_concepto']).strip() == str(id_concepto).strip()]


def get_registros_produccion_por_rango(fecha_desde, fecha_hasta):
    """
    Consulta en la vista V_TMAN todos los registros de producción entre dos fechas (inclusive).
    Retorna lista de diccionarios con horas, duraciones, órdenes, artículos y máquinas.
    """
    if isinstance(fecha_desde, (datetime.date, datetime.datetime)):
        f_desde_str = fecha_desde.strftime('%Y-%m-%d')
    else:
        f_desde_str = str(fecha_desde).strip()

    if isinstance(fecha_hasta, (datetime.date, datetime.datetime)):
        f_hasta_str = fecha_hasta.strftime('%Y-%m-%d')
    else:
        f_hasta_str = str(fecha_hasta).strip()

    sql = """
        SELECT 
            HAP_ROW_ID,
            IDORDEN,
            LTRIM(RTRIM(IDCONCEPTO)) AS id_concepto,
            LTRIM(RTRIM(CONCEPTO)) AS concepto,
            FECHA,
            HORA_D,
            HORA_H,
            ISNULL(Tiempo_minutos, 0) AS tiempo_minutos,
            ISNULL(Tiempo_cotizado, 0) AS tiempo_cotizado,
            ISNULL(Tiempo_cotizado_individual, 0) AS tiempo_cotizado_ind,
            ISNULL(Cantidad_producida, 0) AS cantidad_producida,
            LTRIM(RTRIM(ISNULL(IDMAQUINA, ''))) AS id_maquina,
            LTRIM(RTRIM(ISNULL(MaquinaD, ''))) AS maquina,
            LTRIM(RTRIM(ISNULL(IDOPERACION, ''))) AS id_operacion,
            LTRIM(RTRIM(ISNULL(OPERACION, ''))) AS operacion,
            LTRIM(RTRIM(ISNULL(Articulo, ''))) AS articulo,
            LTRIM(RTRIM(ISNULL(Articulod, ''))) AS articulo_desc,
            LTRIM(RTRIM(ISNULL(Formula, ''))) AS formula,
            LTRIM(RTRIM(ISNULL(OBS, ''))) AS observaciones,
            ISNULL(Es_proceso, 0) AS es_proceso,
            ISNULL(Es_programado, 0) AS es_programado
        FROM V_TMAN
        WHERE CONVERT(date, FECHA) >= ? AND CONVERT(date, FECHA) <= ?
        ORDER BY LTRIM(RTRIM(IDCONCEPTO)), FECHA ASC, HORA_D ASC
    """
    registros = []
    try:
        with get_erp_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (f_desde_str, f_hasta_str))
            for row in cursor.fetchall():
                hora_d = row[5]
                hora_h = row[6]
                minutos = float(row[7])

                if minutos <= 0 and hora_d and hora_h:
                    diff_mins = (hora_h - hora_d).total_seconds() / 60.0
                    if diff_mins > 0:
                        minutos = diff_mins

                registros.append({
                    'row_id': row[0],
                    'id_orden': row[1],
                    'id_concepto': str(row[2]) if row[2] else '',
                    'concepto': str(row[3]) if row[3] else '',
                    'fecha': row[4],
                    'fecha_str': row[4].strftime('%Y-%m-%d') if row[4] else '',
                    'hora_inicio': hora_d,
                    'hora_fin': hora_h,
                    'hora_inicio_str': hora_d.strftime('%H:%M') if hora_d else '',
                    'hora_fin_str': hora_h.strftime('%H:%M') if hora_h else '',
                    'tiempo_minutos': round(minutos, 2),
                    'tiempo_horas': round(minutos / 60.0, 2),
                    'tiempo_cotizado': round(float(row[8]), 4),
                    'tiempo_cotizado_minutos': round(float(row[8]) * 60.0, 2),
                    'cantidad_producida': float(row[10]),
                    'id_maquina': str(row[11]),
                    'maquina': str(row[12]) if row[12] else (str(row[11]) if row[11] else 'Sin Máquina'),
                    'id_operacion': str(row[13]),
                    'operacion': str(row[14]) if row[14] else 'Operación',
                    'articulo': str(row[15]),
                    'articulo_desc': str(row[16]),
                    'formula': str(row[17]),
                    'observaciones': str(row[18]),
                    'es_proceso': bool(row[19]),
                    'es_programado': bool(row[20]),
                })
    except Exception as e:
        logger.error(f"Error al consultar V_TMAN para rango {f_desde_str} a {f_hasta_str}: {e}")
    return registros
