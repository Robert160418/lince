@echo off
title Lince — Git Push + VPS Setup
color 0A
echo.
echo ============================================================
echo   LINCE — Git Push al repositorio
echo ============================================================
echo.

cd /d C:\proyectos\joya-de-la-corona

echo Eliminando locks de git...
if exist .git\config.lock del /f .git\config.lock
if exist .git\index.lock del /f .git\index.lock

echo.
echo Agregando archivos...
git add app/main.py app/utils/batch_processor.py app/utils/google_sheets.py app/templates/index.html setup_vps.sh

echo.
echo Haciendo commit...
git commit -m "feat: pipeline auto P1-P6, Sheet colores + emails + resumen + setup VPS"

echo.
echo Haciendo push a GitHub...
git push origin main

echo.
echo ============================================================
echo   Push completado. Ahora conectando al VPS...
echo ============================================================
echo.
echo Abre una nueva terminal y ejecuta:
echo   ssh root@72.61.4.191
echo.
pause
