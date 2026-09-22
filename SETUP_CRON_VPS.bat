@echo off
title Lince — Configurar Cron Secuencia Diaria
color 0A
echo.
echo ============================================================
echo   Lince VPS — Configurando secuencia automatica de emails
echo   IP: 72.61.4.191   Usuario: root
echo ============================================================
echo.
echo Ingresa tu contrasena SSH cuando se pida (no se ve al escribir).
echo.
echo El secreto de la tarea se genera EN EL VPS y se queda alli: no viaja
echo por este archivo ni por el repositorio.
echo.

REM La logica vive en setup_vps_cron.sh, versionado y revisable.
REM Antes este .bat llevaba el secreto escrito a mano, y el repositorio es
REM publico: cualquiera podia disparar la secuencia diaria de emails.
ssh root@72.61.4.191 "cd /opt/lince && git pull origin main && bash setup_vps_cron.sh"

echo.
echo ============================================================
echo   Listo. Puedes cerrar esta ventana.
echo ============================================================
pause
