from django.urls import path
from . import views

app_name = 'control_produccion'

urlpatterns = [
    # Menú Principal / Dashboard Ejecutivo
    path('', views.dashboard_view, name='dashboard'),
    
    # Opción dedicada en el menú: Pantalla de Control y Auditoría de Producción (Taller)
    path('control-produccion/', views.control_produccion_view, name='control_produccion'),
    
    # Ficha individual de auditoría y análisis de baches por operario
    path('operario/<str:id_concepto>/', views.detalle_operario_view, name='detalle_operario'),
    
    # Registro de notas y justificaciones de auditoría
    path('guardar-nota/', views.guardar_nota_auditoria, name='guardar_nota'),
    
    # Configuración de nómina de operarios de taller
    path('operarios/', views.operarios_config_view, name='operarios_config'),
    path('operarios/nuevo/', views.nuevo_operario_view, name='nuevo_operario'),
    path('operarios/<str:id_concepto>/editar/', views.editar_operario_view, name='editar_operario'),
    
    # Configuración de jornada teórica (8,5 hs) y tolerancias
    path('parametros/', views.parametros_taller_view, name='parametros_taller'),
    
    # Exportación de reporte analítico en Excel (.xlsx)
    path('exportar-excel/', views.exportar_excel_view, name='exportar_excel'),
    
    # API JSON para refresco dinámico
    path('api/auditoria-dia/', views.api_auditoria_dia, name='api_auditoria_dia'),
    
    # API detalle de operario y esquema rotativo semanal
    path('api/operario/<str:id_concepto>/', views.api_operario_detalle, name='api_operario_detalle'),
    
    # Interfaz de Checkout y Panel VIP de Productos para Aura Botanica
    path('aura-botanica/', views.aura_botanica_view, name='aura_botanica'),
]
