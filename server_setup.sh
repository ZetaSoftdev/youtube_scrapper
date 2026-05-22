#!/bin/bash
# YouTube Intelligence Feed — Full Auto-Deploy Script
# Run this on your Ubuntu server as root

set -e
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  YouTube Intelligence Feed — Auto Deploy"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── 1. System packages ───────────────────────────────────────
echo ""
echo "▶ Step 1/7: Installing system dependencies..."
apt update -qq
apt install -y python3 python3-pip python3-venv nginx rsync curl ufw -qq
echo "✅ System packages installed"

# ─── 2. Project folder ───────────────────────────────────────
echo ""
echo "▶ Step 2/7: Setting up project directory..."
mkdir -p /root/youtube_scrapper/static
echo "✅ Directory ready: /root/youtube_scrapper"

# ─── 3. Python virtual environment ───────────────────────────
echo ""
echo "▶ Step 3/7: Creating Python virtual environment..."
cd /root/youtube_scrapper
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install fastapi==0.115.0 uvicorn[standard]==0.30.6 httpx==0.27.2 python-dotenv==1.0.1 apscheduler==3.10.4 python-multipart==0.0.9 -q
echo "✅ Python environment ready"

# ─── 4. Install nlm CLI ───────────────────────────────────────
echo ""
echo "▶ Step 4/7: Installing NotebookLM CLI (nlm)..."
pip install notebooklm-mcp-cli -q
NLM_BIN=$(which nlm || echo "/root/youtube_scrapper/venv/bin/nlm")
echo "✅ nlm installed at: $NLM_BIN"

# ─── 5. Create .env ───────────────────────────────────────────
echo ""
echo "▶ Step 5/7: Creating .env config..."
cat > /root/youtube_scrapper/.env << 'EOF'
YOUTUBE_API_KEY=AIzaSyCJeQvrfLEHMKECzmtBEcnhs4xcZ0_l2pA
SERVER_URL=http://2.24.195.66
NLM_PATH=/root/youtube_scrapper/venv/bin/nlm
EOF
echo "✅ .env created"

# ─── 6. Systemd service ───────────────────────────────────────
echo ""
echo "▶ Step 6/7: Setting up systemd service..."
cat > /etc/systemd/system/ytfeed.service << 'EOF'
[Unit]
Description=YouTube Intelligence Feed
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/youtube_scrapper
EnvironmentFile=/root/youtube_scrapper/.env
ExecStart=/root/youtube_scrapper/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo "✅ systemd service created"

# ─── 7. Nginx ─────────────────────────────────────────────────
echo ""
echo "▶ Step 7/7: Configuring Nginx..."
cat > /etc/nginx/sites-available/ytfeed << 'EOF'
server {
    listen 80;
    server_name 2.24.195.66 _;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/ytfeed /etc/nginx/sites-enabled/
nginx -t
systemctl enable nginx
systemctl restart nginx
echo "✅ Nginx configured and running"

# ─── Firewall ──────────────────────────────────────────────────
echo ""
echo "▶ Configuring firewall..."
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
echo "y" | ufw enable 2>/dev/null || true
echo "✅ Firewall rules set"

# ─── Done ─────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ SERVER READY — Now upload the app files from Mac"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Python env : /root/youtube_scrapper/venv"
echo "  nlm path   : $NLM_BIN"
echo "  App port   : 8080 (behind Nginx on port 80)"
echo ""
echo "  ⚠️  IMPORTANT: Run 'nlm login' to authenticate NotebookLM"
echo "     Then run the deploy commands from your Mac."
echo ""
