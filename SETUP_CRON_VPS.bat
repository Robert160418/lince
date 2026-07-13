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

ssh root@72.61.4.191 "cd /opt/lince && git pull origin main && grep -q TASK_SECRET .env 2>/dev/null || echo TASK_SECRET=lince-cron-2026 >> .env && printf '#!/bin/bash\nDATE=$(date +%%Y-%%m-%%d\ %%H:%%M:%%S)\necho \"[$$DATE] Secuencia diaria...\" >> /var/log/lince-sequence.log\ncurl -s -X POST https://lince.noboweb.com/tasks/daily-sequence -H \"X-Task-Secret: lince-cron-2026\" -H \"Content-Type: application/json\" >> /var/log/lince-sequence.log 2>&1\n' > /opt/lince/run_daily_sequence.sh && chmod +x /opt/lince/run_daily_sequence.sh && (crontab -l 2>/dev/null | grep -v daily_sequence; echo '0 9 * * * /opt/lince/run_daily_sequence.sh') | crontab - && systemctl restart lince && echo. && echo ============================================================ && echo   TODO LISTO - Cron configurado y servicio reiniciado && echo ============================================================ && crontab -l"

echo.
echo ============================================================
echo   Listo. Puedes cerrar esta ventana.
echo ============================================================
pause
