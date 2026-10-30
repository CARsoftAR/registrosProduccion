from django.db import models
from django.utils import timezone


class ParametroTaller(models.Model):
    """
    Parámetros de auditoría operativa de planta y taller.
    Define la jornada obligatoria teórica de 8,5 horas diarias y tolerancias.
    """
    jornada_teorica_horas = models.FloatField(
        default=8.5,
        verbose_name="Jornada Teórica Diaria (Horas)"
    )
    tolerancia_bache_minutos = models.IntegerField(
        default=15,
        verbose_name="Tolerancia para detección de baches intradía (minutos)"
    )
    hora_inicio_taller = models.CharField(
        max_length=10,
        default="07:00",
        verbose_name="Hora Teórica de Inicio"
    )
    hora_fin_taller = models.CharField(
        max_length=10,
        default="16:00",
        verbose_name="Hora Teórica de Fin"
    )
    ultima_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'parametro_taller'
        verbose_name = 'Parámetro de Taller'
        verbose_name_plural = 'Parámetros de Taller'

    def __str__(self):
        return f"Jornada: {self.jornada_teorica_horas} hs | Inicio: {self.hora_inicio_taller} - Fin: {self.hora_fin_taller}"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'jornada_teorica_horas': 8.5,
                'tolerancia_bache_minutos': 15,
                'hora_inicio_taller': '07:00',
                'hora_fin_taller': '16:00',
            }
        )
        # Garantizar valores estáticos fijos por defecto (8,5 hs, 07:00 a 16:00, 15 min bache)
        if (obj.jornada_teorica_horas != 8.5 or 
            obj.hora_inicio_taller != '07:00' or 
            obj.hora_fin_taller != '16:00' or 
            obj.tolerancia_bache_minutos != 15):
            obj.jornada_teorica_horas = 8.5
            obj.tolerancia_bache_minutos = 15
            obj.hora_inicio_taller = '07:00'
            obj.hora_fin_taller = '16:00'
            obj.save(update_fields=['jornada_teorica_horas', 'tolerancia_bache_minutos', 'hora_inicio_taller', 'hora_fin_taller'])
        return obj


class OperarioTaller(models.Model):
    """
    Nómina local de operarios auditables de taller (sincronizada desde TMAN014 de EqualRP).
    Permite activar/desactivar operarios en auditoría sin tocar el ERP.
    """
    id_concepto = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name="ID Concepto / Legajo ERP"
    )
    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre Completo"
    )
    activo = models.BooleanField(
        default=True,
        verbose_name="Activo en Auditoría Taller"
    )
    puesto_area = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Puesto / Sección Principal"
    )
    horario_rotativo = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        verbose_name="Esquema Semanal Rotativo"
    )
    es_mensual = models.BooleanField(
        default=False,
        verbose_name="Liquidación Mensual"
    )
    categoria = models.CharField(
        max_length=100,
        default="PRODUCCIÓN",
        blank=True,
        null=True,
        verbose_name="Sector / Categoría"
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    @property
    def iniciales(self):
        clean = (self.nombre or '').replace(',', ' ').strip()
        parts = [p for p in clean.split() if p]
        if not parts:
            return 'OP'
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    @property
    def horario_base(self):
        esq = self.get_esquema_semanal()
        lun = esq.get('lunes', {})
        if lun.get('activo', True):
            ini = lun.get('inicio', '07:00')
            fin = lun.get('fin', '16:00')
            return f"{ini} a {fin} (L-V)"
        return "Sin horario base"

    @staticmethod
    def get_esquema_semanal_default():
        return {
            'lunes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
            'martes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
            'miercoles': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
            'jueves': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
            'viernes': {'activo': True, 'inicio': '07:00', 'fin': '16:00'},
            'sabado': {'activo': False, 'inicio': '07:00', 'fin': '12:00'},
            'domingo': {'activo': False, 'inicio': '07:00', 'fin': '12:00'},
        }

    def get_esquema_semanal(self):
        default = self.get_esquema_semanal_default()
        if not self.horario_rotativo or not isinstance(self.horario_rotativo, dict):
            return default
        res = {}
        for dia, vals in default.items():
            saved = self.horario_rotativo.get(dia, {})
            res[dia] = {
                'activo': bool(saved.get('activo', vals['activo'])),
                'inicio': str(saved.get('inicio', vals['inicio']) or '07:00'),
                'fin': str(saved.get('fin', vals['fin']) or '16:00'),
            }
        return res

    def get_horario_dia(self, dia_index_o_nombre):
        """
        Retorna el horario configurado para un día específico (0=lunes .. 6=domingo o string 'lunes').
        Calcula también las horas teóricas del turno considerando refrigerio si la jornada supera 6 hs.
        """
        dias = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']
        if isinstance(dia_index_o_nombre, int) and 0 <= dia_index_o_nombre < 7:
            dia_key = dias[dia_index_o_nombre]
        else:
            dia_key = str(dia_index_o_nombre).lower()

        esquema = self.get_esquema_semanal()
        config_dia = esquema.get(dia_key, {'activo': True, 'inicio': '07:00', 'fin': '16:00'})
        
        activo = config_dia.get('activo', True)
        inicio_str = config_dia.get('inicio', '07:00')
        fin_str = config_dia.get('fin', '16:00')

        if not activo:
            return {
                'activo': False,
                'inicio': inicio_str,
                'fin': fin_str,
                'horas_teoricas': 0.0,
                'minutos_teoricos': 0.0,
            }

        try:
            h_ini, m_ini = [int(p) for p in inicio_str.split(':')[:2]]
            h_fin, m_fin = [int(p) for p in fin_str.split(':')[:2]]
            total_mins = (h_fin * 60 + m_fin) - (h_ini * 60 + m_ini)
            if total_mins < 0:
                total_mins += 24 * 60
            
            # Si el turno es estándar (ej: 07:00 a 16:00 = 9h), descontar 30m de refrigerio => 8,5 hs
            if inicio_str == '07:00' and fin_str == '16:00':
                horas_teoricas = 8.5
                mins_netos = 510.0
            elif total_mins >= 360:
                mins_netos = max(0.0, total_mins - 30.0)
                horas_teoricas = round(mins_netos / 60.0, 2)
            else:
                mins_netos = float(total_mins)
                horas_teoricas = round(mins_netos / 60.0, 2)
        except Exception:
            horas_teoricas = 8.5
            mins_netos = 510.0

        return {
            'activo': True,
            'inicio': inicio_str,
            'fin': fin_str,
            'horas_teoricas': horas_teoricas,
            'minutos_teoricos': mins_netos,
        }

    class Meta:
        db_table = 'operario_taller'
        verbose_name = 'Operario de Taller'
        verbose_name_plural = 'Operarios de Taller'
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} (ID: {self.id_concepto})"


class NotaAuditoria(models.Model):
    """
    Justificación o nota de auditoría sobre desvíos o baches de un operario en una fecha.
    """
    MOTIVO_CHOICES = [
        ('OMISION_CARGA', 'Omisión en carga de datos / Olvido'),
        ('MANTENIMIENTO', 'Parada de máquina / Mantenimiento'),
        ('RETRABAJO', 'Retrabajo sin OT asignada'),
        ('TAREAS_GENERALES', 'Limpieza / Tareas auxiliares de planta'),
        ('LICENCIA', 'Permiso / Trámite / Licencia autorizada'),
        ('OTRO', 'Otro motivo'),
    ]

    fecha = models.DateField(db_index=True, verbose_name="Fecha Auditada")
    id_concepto = models.CharField(max_length=50, db_index=True, verbose_name="ID Concepto Operario")
    motivo = models.CharField(max_length=30, choices=MOTIVO_CHOICES, default='OMISION_CARGA')
    detalle = models.TextField(verbose_name="Detalle de Auditoría")
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'nota_auditoria'
        verbose_name = 'Nota de Auditoría'
        verbose_name_plural = 'Notas de Auditoría'
        ordering = ['-fecha', '-creado_el']

    def __str__(self):
        return f"Nota {self.fecha} - {self.id_concepto}: {self.motivo}"
