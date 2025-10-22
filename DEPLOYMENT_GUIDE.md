# 🚀 Deployment Guide - Lexi CAO naar Hetzner

## ❗ **Oplossing voor "startSignup is not defined" Probleem**

**Oorzaak:** Je Hetzner server draait **oude code** zonder de nieuwste updates. Browsers cachen deze oude HTML/JavaScript files.

**Oplossing:** Deploy de nieuwste code van GitHub naar Hetzner en herstart Gunicorn.

---

## 📋 **Stap-voor-Stap Deployment Proces**

### **Stap 1: Code Pushen naar GitHub**

Vanaf deze Replit omgeving:

```bash
# Als je nog geen Git remote hebt:
git remote add origin https://github.com/jouw-username/lexi-cao.git

# Commit alle wijzigingen:
git add .
git commit -m "Fix: Cache busting met BUILD_VERSION voor JavaScript functies"

# Push naar GitHub:
git push origin main

# (Optioneel) Maak een release tag:
git tag -a v2025.10.22 -m "Production release - Cache busting fix"
git push origin v2025.10.22
```

---

### **Stap 2: Deploy op Hetzner Server**

SSH naar je Hetzner server en voer uit:

```bash
# Ga naar je project directory:
cd /pad/naar/lexi-cao

# Pull nieuwste code:
git fetch origin
git pull origin main

# Of gebruik een specifieke tag:
# git fetch --tags
# git checkout v2025.10.22

# Update Python dependencies (indien nodig):
pip install -r requirements.txt

# Herstart Gunicorn (kies één methode):

# Methode A: Systemd service reload (zero downtime):
sudo systemctl reload gunicorn-lexi

# Methode B: Systemd service restart:
sudo systemctl restart gunicorn-lexi

# Methode C: Direct Gunicorn HUP signal (zero downtime):
sudo pkill -HUP gunicorn

# Methode D: Kill en herstart (met downtime):
sudo systemctl stop gunicorn-lexi
sudo systemctl start gunicorn-lexi
```

---

### **Stap 3: Verifieer Deployment**

```bash
# Check of Gunicorn draait:
sudo systemctl status gunicorn-lexi

# Check logs voor errors:
sudo journalctl -u gunicorn-lexi -f

# Test database connectie:
python3 -c "from main import db, app; app.app_context().push(); print('Database OK:', db.engine.execute('SELECT 1').scalar() == 1)"
```

---

### **Stap 4: Test in Browser**

1. **Hard refresh** je browser: `Ctrl+Shift+R` (Windows) of `Cmd+Shift+R` (Mac)
2. Open Developer Tools (`F12`) → Console tab
3. Ga naar `https://lexiai.nl/prijzen`
4. Klik op **"Start met Professional"** knop
5. **Verwacht gedrag:** Formulier opent zonder errors in console

---

## ⚙️ **Aanbevolen Systemd Service Configuratie**

Maak `/etc/systemd/system/gunicorn-lexi.service`:

```ini
[Unit]
Description=Lexi CAO Meester - Gunicorn Production Server
After=network.target neon-postgresql.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/home/lexi/lexi-cao
Environment="PATH=/home/lexi/.local/bin:/usr/local/bin:/usr/bin:/bin"

# Environment Variables (gebruik volledige paths voor secrets)
EnvironmentFile=/home/lexi/lexi-cao/.env

# Build version voor cache busting (gebruik Git commit hash)
Environment="BUILD_VERSION=%H"

# Gunicorn Command (3 workers = 2*CPU+1 voor 1 CPU server)
ExecStart=/usr/local/bin/gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 3 \
    --timeout 120 \
    --worker-class sync \
    --access-logfile /var/log/lexi-cao/access.log \
    --error-logfile /var/log/lexi-cao/error.log \
    --log-level info \
    main:app

# Zero-downtime reload via HUP signal
ExecReload=/bin/kill -s HUP $MAINPID

# Automatic restart on failure
Restart=on-failure
RestartSec=5s

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Activeer service:**

```bash
# Maak log directory:
sudo mkdir -p /var/log/lexi-cao
sudo chown www-data:www-data /var/log/lexi-cao

# Enable en start service:
sudo systemctl daemon-reload
sudo systemctl enable gunicorn-lexi
sudo systemctl start gunicorn-lexi

# Check status:
sudo systemctl status gunicorn-lexi
```

---

## 🌐 **Nginx Reverse Proxy Configuratie**

`/etc/nginx/sites-available/lexiai.nl`:

```nginx
# HTTP → HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name lexiai.nl *.lexiai.nl;
    
    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    # Redirect all other HTTP to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name lexiai.nl *.lexiai.nl;
    
    # SSL Certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/lexiai.nl/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lexiai.nl/privkey.pem;
    
    # SSL Configuration (Mozilla Intermediate)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # HSTS Header (strict HTTPS)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    
    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Serve static files directly from Nginx (performance)
    location /static/ {
        alias /home/lexi/lexi-cao/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    
    # Proxy all other requests to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
        
        # Buffering
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
        proxy_busy_buffers_size 8k;
    }
    
    # Error pages
    error_page 502 503 504 /maintenance.html;
    location = /maintenance.html {
        root /var/www/html;
        internal;
    }
}
```

**Activeer configuratie:**

```bash
# Symlink naar sites-enabled:
sudo ln -s /etc/nginx/sites-available/lexiai.nl /etc/nginx/sites-enabled/

# Test configuratie:
sudo nginx -t

# Reload Nginx:
sudo systemctl reload nginx
```

---

## 🔐 **Environment Variables (.env file)**

Maak `/home/lexi/lexi-cao/.env`:

```bash
# Flask
SESSION_SECRET="jouw-super-sterke-random-secret-hier"
ENVIRONMENT=production

# Database (Neon PostgreSQL)
DATABASE_URL="postgresql://neondb_owner:npg_dx6XscthfFI0@ep-fancy-meadow-agaclp0e-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"

# Stripe (PRODUCTIE KEYS!)
STRIPE_SECRET_KEY_PROD="sk_live_jouw_stripe_live_key"
STRIPE_WEBHOOK_SECRET_PROD="whsec_jouw_webhook_secret"

# MailerSend
MAILERSEND_API_KEY="mlsn_jouw_mailersend_key"

# Google Cloud (Vertex AI)
GOOGLE_APPLICATION_CREDENTIALS="/home/lexi/lexi-cao/service-account.json"
GOOGLE_CLOUD_PROJECT="jouw-gcp-project-id"
VERTEX_AI_AGENT_ID="jouw-agent-id"
VERTEX_AI_LOCATION="europe-west4"

# S3 Object Storage
S3_ACCESS_KEY="jouw-s3-access-key"
S3_SECRET_KEY="jouw-s3-secret-key"
S3_BUCKET_NAME="lexi-cao-production"
S3_ENDPOINT_URL="https://jouw-endpoint.com"

# Build Version (gebruik Git commit hash)
BUILD_VERSION=$(git rev-parse --short HEAD)
```

**Beveilig je .env file:**

```bash
sudo chmod 600 /home/lexi/lexi-cao/.env
sudo chown www-data:www-data /home/lexi/lexi-cao/.env
```

---

## 🔄 **Automatische Deployment Script**

Maak `/home/lexi/deploy.sh`:

```bash
#!/bin/bash
set -e

echo "🚀 Deploying Lexi CAO to production..."

# Ga naar project directory
cd /home/lexi/lexi-cao

# Pull nieuwste code
echo "📥 Pulling latest code from GitHub..."
git fetch origin
git pull origin main

# Update BUILD_VERSION met Git commit hash
BUILD_VERSION=$(git rev-parse --short HEAD)
sed -i "s/^BUILD_VERSION=.*/BUILD_VERSION=$BUILD_VERSION/" .env

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt --quiet

# Database migrations (indien nodig)
# echo "🗄️ Running database migrations..."
# flask db upgrade

# Reload Gunicorn (zero downtime)
echo "♻️ Reloading Gunicorn..."
sudo systemctl reload gunicorn-lexi

# Wait for reload
sleep 2

# Health check
echo "🏥 Running health check..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://lexiai.nl)
if [ "$HTTP_CODE" -eq 200 ]; then
    echo "✅ Deployment successful! (HTTP $HTTP_CODE)"
    echo "📝 Build version: $BUILD_VERSION"
else
    echo "❌ Deployment failed! (HTTP $HTTP_CODE)"
    exit 1
fi

echo "🎉 Deployment completed!"
```

**Maak executable:**

```bash
chmod +x /home/lexi/deploy.sh
```

**Deploy met één commando:**

```bash
./deploy.sh
```

---

## ✅ **Post-Deployment Checklist**

- [ ] Gunicorn service draait zonder errors
- [ ] Nginx reverse proxy werkt correct
- [ ] HTTPS certificaat is geldig
- [ ] Database connectie naar Neon werkt
- [ ] "Start met Professional" knop werkt zonder hard refresh
- [ ] Browser console toont geen JavaScript errors
- [ ] Stripe webhooks ontvangen (test met een betaling)
- [ ] Email notificaties worden verstuurd
- [ ] S3 object storage werkt (upload een bestand in chat)

---

## 🐛 **Troubleshooting**

### **Probleem: Knop werkt nog steeds niet**

```bash
# Clear browser cache volledig:
# Chrome: Settings → Privacy → Clear browsing data → Cached images and files

# Check of nieuwe code is gedeployed:
grep -r "BUILD_VERSION" /home/lexi/lexi-cao/main.py

# Check Gunicorn versie:
curl -I https://lexiai.nl | grep -i server
# Moet tonen: Server: Lexi AI
```

### **Probleem: Database connection error**

```bash
# Test database connectie:
psql "postgresql://neondb_owner:npg_dx6XscthfFI0@ep-fancy-meadow-agaclp0e-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require" -c "SELECT 1;"

# Check Gunicorn logs:
sudo journalctl -u gunicorn-lexi --since "5 minutes ago"
```

### **Probleem: 502 Bad Gateway**

```bash
# Check of Gunicorn draait:
sudo systemctl status gunicorn-lexi

# Check of poort 5000 luistert:
sudo netstat -tlnp | grep :5000

# Herstart Gunicorn:
sudo systemctl restart gunicorn-lexi
```

---

## 📞 **Hulp Nodig?**

Als je problemen hebt met deployment, check:

1. **Gunicorn logs:** `sudo journalctl -u gunicorn-lexi -f`
2. **Nginx logs:** `sudo tail -f /var/log/nginx/error.log`
3. **App logs:** `/var/log/lexi-cao/error.log`

---

**Succes met je deployment!** 🚀
