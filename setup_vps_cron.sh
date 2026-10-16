#!/bin/bash
# ─────────────────────────────────────────────────────────
# setup_vps_cron.sh — correr en el VPS (se puede repetir sin riesgo)
#   bash setup_vps_cron.sh            # usa /opt/lince
#   LINCE_DIR=/opt/lince-v2 bash setup_vps_cron.sh
#
# - Genera claves aleatorias para TASK_SECRET y LINCE_API_TOKEN si faltan
#   o si siguen con el valor viejo que quedó publicado en el repositorio.
# - El cron lee la clave del .env en cada ejecución: nunca se escribe en
#   un archivo del repositorio.
# ─────────────────────────────────────────────────────────
set -e

LINCE_DIR="${LINCE_DIR:-/opt/lince}"
ENV_FILE="${ENV_FILE:-$LINCE_DIR/.env}"
LINCE_URL="${LINCE_URL:-https://lince.noboweb.com}"
CLAVE_VIEJA="lince-cron-2026"

echo "== Lince — configuración del cron ($LINCE_DIR) =="

cd "$LINCE_DIR"
git pull origin main
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

asegurar_clave () {
    local nombre="$1"
    local actual
    actual="$(grep -E "^${nombre}=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true)"
    if [ -z "$actual" ] || [ "$actual" = "$CLAVE_VIEJA" ]; then
        local nueva
        nueva="$(openssl rand -hex 24)"
        sed -i "/^${nombre}=/d" "$ENV_FILE"
        echo "${nombre}=${nueva}" >> "$ENV_FILE"
        echo "  ${nombre}: generada (nueva)"
        if [ "$nombre" = "LINCE_API_TOKEN" ]; then
            echo "  >> Guarda este token para entrar al panel: ${nueva}"
        fi
    else
        echo "  ${nombre}: ya configurada"
    fi
}

asegurar_clave TASK_SECRET
asegurar_clave LINCE_API_TOKEN

cat > "$LINCE_DIR/run_daily_sequence.sh" << EOF
#!/bin/bash
# Cron diario — envía el siguiente correo de las secuencias activas
SECRET="\$(grep -E '^TASK_SECRET=' "$ENV_FILE" | tail -1 | cut -d= -f2-)"
echo "[\$(date '+%Y-%m-%d %H:%M:%S')] Secuencia diaria" >> /var/log/lince-sequence.log
curl -s -X POST "$LINCE_URL/tasks/daily-sequence" -H "X-Task-Secret: \$SECRET" >> /var/log/lince-sequence.log 2>&1
echo "" >> /var/log/lince-sequence.log
EOF
chmod 700 "$LINCE_DIR/run_daily_sequence.sh"

(crontab -l 2>/dev/null | grep -v "run_daily_sequence"; echo "0 9 * * * $LINCE_DIR/run_daily_sequence.sh") | crontab -
echo "  Cron diario 9:00 registrado"

systemctl restart lince
sleep 2
systemctl status lince --no-pager | head -10
echo "== Listo. Logs: /var/log/lince-sequence.log =="
