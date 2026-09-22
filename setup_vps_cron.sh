#!/bin/bash
# ─────────────────────────────────────────────────────────
# setup_vps_cron.sh  — Correr UNA SOLA VEZ en el VPS
# Configura la secuencia automática de emails Días 2-5
#
# SEGURIDAD: el secreto de la tarea NO se escribe en este archivo ni en el
# repositorio. Se genera en el propio VPS con `openssl rand -hex 32` y se lee
# de .env para construir el script del cron, que queda con permisos 600.
#
# Para ROTAR el secreto más adelante: borra la línea TASK_SECRET de .env y
# vuelve a ejecutar este script.
# ─────────────────────────────────────────────────────────
set -e

echo ""
echo "======================================================"
echo "  Lince — Configurando secuencia diaria de emails"
echo "======================================================"

# 1. Traer código nuevo de GitHub
echo ""
echo "1/5  git pull..."
cd /opt/lince
git pull origin main

# 2. Asegurar TASK_SECRET en .env (se genera aquí, nunca viene del repo)
echo ""
echo "2/5  Configurando TASK_SECRET en .env..."
if grep -q "^TASK_SECRET=" .env 2>/dev/null; then
    echo "     Ya existe TASK_SECRET en .env — sin cambios"
else
    printf 'TASK_SECRET=%s\n' "$(openssl rand -hex 32)" >> .env
    echo "     TASK_SECRET generado con openssl rand -hex 32"
fi

# Se lee para el script del cron. No se imprime nunca en pantalla ni en logs.
TASK_SECRET_VAL="$(grep -m1 '^TASK_SECRET=' .env | cut -d= -f2-)"
if [ -z "$TASK_SECRET_VAL" ]; then
    echo "     ERROR: TASK_SECRET quedó vacío en .env. Abortando sin tocar el cron."
    exit 1
fi
echo "     Secreto leído de .env (no se muestra)"

# 3. Crear script del cron
#    El heredoc va SIN comillas para que se sustituya el secreto al escribirlo.
echo ""
echo "3/5  Creando /opt/lince/run_daily_sequence.sh..."
cat > /opt/lince/run_daily_sequence.sh <<EOF
#!/bin/bash
# Cron diario — envía emails de secuencia Días 2-5
DATE=\$(date '+%Y-%m-%d %H:%M:%S')
echo "[\$DATE] Ejecutando secuencia diaria..." >> /var/log/lince-sequence.log
curl -s -X POST https://lince.noboweb.com/tasks/daily-sequence \\
     -H "X-Task-Secret: ${TASK_SECRET_VAL}" \\
     -H "Content-Type: application/json" \\
     >> /var/log/lince-sequence.log 2>&1
echo "" >> /var/log/lince-sequence.log
EOF
chmod 700 /opt/lince/run_daily_sequence.sh
echo "     Script creado, ejecutable y solo para root (700), porque contiene el secreto"

# 4. Registrar cron a las 9:00am (evita duplicados)
echo ""
echo "4/5  Registrando cron diario a las 9:00am..."
(crontab -l 2>/dev/null | grep -v "run_daily_sequence"; echo "0 9 * * * /opt/lince/run_daily_sequence.sh") | crontab -
echo "     Cron registrado:"
crontab -l

# 5. Reiniciar servicio Lince
echo ""
echo "5/5  Reiniciando servicio lince..."
systemctl restart lince
sleep 2
systemctl status lince --no-pager | head -20

echo ""
echo "======================================================"
echo "  ✅ Configuración completada"
echo "  El cron corre cada día a las 9:00am del servidor"
echo "  Logs en: /var/log/lince-sequence.log"
echo ""
echo "  El secreto anterior queda invalidado: ya no está en el repo."
echo "  Para rotarlo: borra la línea TASK_SECRET de .env y repite este script."
echo "======================================================"
