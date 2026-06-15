#!/bin/bash
# ============================================================
# Lince — Setup en AlmaLinux 9 con CyberPanel
# IP: 72.61.4.191  |  User: root
# Ejecutar: bash setup_vps.sh
# ============================================================
set -e

echo ""
echo "============================================================"
echo " 🐆  LINCE — Instalación en AlmaLinux 9 + CyberPanel"
echo "============================================================"

# ── 1. Dependencias del sistema (dnf, no apt) ─────────────────
echo ""
echo "▶ [1/7] Actualizando sistema..."
dnf update -y -q

echo "▶ [2/7] Instalando dependencias del sistema..."
# Python 3.11 en AlmaLinux 9
dnf install -y python3.11 python3.11-pip python3.11-devel \
    git curl wget gcc make \
    nss atk at-spi2-atk libdrm libX11 libXcomposite libXdamage \
    libXext libXfixes libXrandr libgbm libxkbcommon alsa-lib \
    pango cairo cups-libs libXScrnSaver mesa-libgbm \
    xdg-utils 2>/dev/null || true

# Instalar python3.11-venv si no está incluido
python3.11 -m ensurepip --upgrade 2>/dev/null || true

# ── 2. Clonar repositorio ─────────────────────────────────────
echo ""
echo "▶ [3/7] Clonando repositorio en /opt/lince..."
cd /opt

if [ -d "lince" ]; then
    echo "   Repositorio ya existe — actualizando..."
    cd lince && git pull origin main
else
    git clone https://github.com/robertonoboa/lince.git lince
    cd lince
fi

# ── 3. Entorno virtual Python ─────────────────────────────────
echo ""
echo "▶ [4/7] Configurando entorno Python 3.11..."
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── 4. Playwright + Chromium ──────────────────────────────────
echo ""
echo "▶ [5/7] Instalando Playwright + Chromium..."
python3.11 -m playwright install chromium
python3.11 -m playwright install-deps chromium 2>/dev/null || \
    dnf install -y \
        nss-devel atk gtk3 libXt libXtst pango alsa-lib \
        cups-libs libXScrnSaver 2>/dev/null || true

# ── 5. Variables de entorno ───────────────────────────────────
echo ""
echo "▶ [6/7] Configurando variables de entorno..."

if [ ! -f /opt/lince/.env ]; then
    cat > /opt/lince/.env << 'ENVEOF'
# ── Supabase ──────────────────────────────────────────────────
SUPABASE_URL=https://bpycimognxzipvleqvsu.supabase.co
SUPABASE_KEY=REEMPLAZAR_CON_CLAVE_SUPABASE

# ── Brevo ─────────────────────────────────────────────────────
BREVO_API_KEY=REEMPLAZAR_CON_CLAVE_BREVO

# ── OpenAI ────────────────────────────────────────────────────
OPENAI_API_KEY=REEMPLAZAR_CON_CLAVE_OPENAI

# ── Google Sheets ─────────────────────────────────────────────
GOOGLE_SHEET_ID=1hgNERuux2eZ1MDv-tgCDp_qva-fqf1RHF9Qu4Qysjjg
GOOGLE_SHEETS_CREDENTIALS=REEMPLAZAR_CON_JSON_CREDENCIALES
ENVEOF
    echo "   ⚠️  Archivo .env creado — edita con tus claves: nano /opt/lince/.env"
else
    echo "   .env ya existe — no se sobreescribe"
fi

# ── 6. Servicio systemd ───────────────────────────────────────
echo ""
echo "▶ [7/7] Configurando servicio systemd..."

cat > /etc/systemd/system/lince.service << 'SERVICEEOF'
[Unit]
Description=Lince API — FastAPI + Uvicorn
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/lince
EnvironmentFile=/opt/lince/.env
ExecStart=/opt/lince/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lince

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable lince
systemctl start lince || true

# ── Abrir puerto 8080 en firewall (para pruebas temporales) ──
firewall-cmd --zone=public --add-port=8080/tcp --permanent 2>/dev/null || true
firewall-cmd --reload 2>/dev/null || true

echo ""
echo "============================================================"
echo " ✅  Instalación base completada"
echo "============================================================"
echo ""
echo " Estado del servicio:"
systemctl status lince --no-pager -l || true
echo ""
echo " Prueba local:"
echo "   curl http://127.0.0.1:8080/health"
echo ""
echo " ─────────────────────────────────────────────────────────"
echo " PRÓXIMOS PASOS MANUALES:"
echo " 1. Editar claves:   nano /opt/lince/.env"
echo " 2. Reiniciar:       systemctl restart lince"
echo " 3. Ver logs:        journalctl -u lince -f"
echo " 4. En CyberPanel:   Crear sitio lince.noboweb.com"
echo "    → Configurar proxy reverso → http://127.0.0.1:8080"
echo " 5. SSL automático:  CyberPanel → SSL → Issue SSL"
echo " ─────────────────────────────────────────────────────────"
echo ""
