from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('control_produccion.urls', namespace='control_produccion')),
]
