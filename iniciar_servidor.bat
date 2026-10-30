@echo off
title ABBAMAT - Control y Auditoria de Produccion
color 0B
echo ======================================================================
echo   ABBAMAT - SISTEMA DE CONTROL Y AUDITORIA DE PRODUCCION (TALLER)
echo   Jornada Teorica: 8,5 Horas Diarias  ^|  Conexion ERP: Solo Lectura
echo ======================================================================
echo.

cd /d "c:\Sistemas ABBAMAT\registrosProduccion"

echo [1/2] Verificando base de datos y esquema local...
python manage.py migrate --noinput

echo [2/2] Sincronizando parametros y nomina de planta...
python init_database.py

echo.
echo ======================================================================
echo   SERVIDOR LISTO EN: http://127.0.0.1:8080
echo   Pantalla Principal: http://127.0.0.1:8080/control-produccion/
echo ======================================================================
echo.

python manage.py runserver 0.0.0.0:8080
pause
