#!/bin/bash
# ─────────────────────────────────────────────────────────
# setup_vps_cron.sh  — Correr UNA SOLA VEZ en el VPS
# Configura la secuencia automática de emails Días 2-5
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

# 2. Agregar TASK_SECRET al .env (solo si no existe)
echo ""
echo "2/5  Configurando TASK_SECRET en .env..."
if grep -q "TASK_SECRET" .env 2>/dev/null; then
    echo "     Ya existe TASK_SECRET en .env — sin cambios"
else
    echo "TASK_SECRET=lince-cron-2026" >> .env
    echo "     TASK_SECRET agregado"
fi

# 3. Crear script del cron
echo ""
echo "3/5  Creando /opt/lince/run_daily_sequence.sh..."
cat > /opt/lince/run_daily_sequence.sh << 'EOF'
#!/bin/bash
# Cron diario — envía emails de secuencia Días 2-5
DATE=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$DATE] Ejecutando secuencia diaria..." >> /var/log/lince-sequence.log
curl -s -X POST https://lince.noboweb.com/tasks/daily-sequence \
     -H "X-Task-Secret: lince-cron-2026" \
     -H "Content-Type: application/json" \
     >> /var/log/lince-sequence.log 2>&1
echo "" >> /var/log/lince-sequence.log
EOF
chmod +x /opt/lince/run_daily_sequence.sh
echo "     Script creado y ejecutable"

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
echo "======================================================"
