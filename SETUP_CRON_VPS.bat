@echo off
title Lince - Configurar cron y claves
echo.
echo Ejecuta setup_vps_cron.sh en el VPS (genera claves nuevas si hacen falta).
echo.
set /p VPS=IP o dominio del VPS: 
ssh root@%VPS% "cd /opt/lince && git pull origin main && bash setup_vps_cron.sh"
echo.
pause
