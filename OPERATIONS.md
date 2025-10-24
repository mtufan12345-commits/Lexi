# Lexi Production Operations Guide

Last updated: 2025-10-24

## Quick Status Check

```bash
# Quick status
lexi-status

# Full monitoring report
lexi-status full

# Backup status
lexi-status backup
```

## Service Management

### Start/Stop/Restart
```bash
# Restart service
systemctl restart lexi

# Stop service
systemctl stop lexi

# Start service
systemctl start lexi

# Check status
systemctl status lexi
```

### Auto-start Configuration
✅ **Auto-start is ENABLED** - Service will start automatically on boot

```bash
# Verify auto-start
systemctl is-enabled lexi

# Disable auto-start (not recommended)
systemctl disable lexi

# Re-enable auto-start
systemctl enable lexi
```

## Monitoring

### Health Check Endpoint
```bash
# Check application health
curl http://localhost:5000/health | python3.11 -m json.tool

# Via HTTPS (from external)
curl https://lexiai.nl/health
```

**Health Check Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-24T14:27:35.205902",
  "services": {
    "database": "healthy",
    "s3": "healthy",
    "vertex_ai": "healthy",
    "email": "healthy"
  }
}
```

### Logs

```bash
# View live logs
journalctl -u lexi -f

# View last 100 lines
journalctl -u lexi -n 100

# View logs since 1 hour ago
journalctl -u lexi --since "1 hour ago"

# Search for errors
journalctl -u lexi | grep -i error

# View logs from specific date
journalctl -u lexi --since "2025-10-24"
```

### Log Rotation
✅ **Configured** - Logs rotate automatically
- **Max size:** 500MB
- **Retention:** 30 days
- **Compression:** Enabled
- **Config:** `/etc/systemd/journald.conf.d/lexi.conf`

### Monitoring Scripts

**Location:** `/var/www/lexi/scripts/`

1. **monitor.sh** - Comprehensive system monitoring
   ```bash
   /var/www/lexi/scripts/monitor.sh
   ```

2. **backup-check.sh** - Backup status verification
   ```bash
   /var/www/lexi/scripts/backup-check.sh
   ```

## Backups

### Database (Neon.tech)
- **Type:** Automated daily snapshots
- **Retention:** 7 days (free tier) / 30 days (paid)
- **Provider:** Neon.tech
- **Recovery:** Via Neon.tech dashboard (https://console.neon.tech)

### S3 Storage
- **Provider:** fsn1.your-objectstorage.com
- **Bucket:** lexi
- **Versioning:** ⚠️ Not enabled (recommended to enable)
- **Manual Backup:** Files stored in `/chats/`, `/uploads/`, `/artifacts/`

### Code (GitHub)
- **Repository:** github.com/mtufan12345-commits/Lexi
- **Branch:** main
- **Sync Check:**
  ```bash
  cd /var/www/lexi && git status
  ```

### Configuration Files
⚠️ **NOT in git** (contain secrets):
- `.env` - Environment variables
- `google-credentials.json` - Google Cloud credentials
- `/etc/systemd/system/lexi.service` - Systemd service

**Recommendation:** Create encrypted backup of these files

## Deployment

### Update Application
```bash
# 1. Pull latest code
cd /var/www/lexi
git pull origin main

# 2. Install dependencies (if needed)
pip install -r requirements.txt
npm install  # if package.json changed

# 3. Rebuild CSS (if needed)
npm run build:css

# 4. Restart service
systemctl restart lexi

# 5. Verify
lexi-status
```

### Environment Variables
All environment variables are loaded from `/var/www/lexi/.env`

**Critical variables:**
- `SESSION_SECRET` - Flask session secret
- `DATABASE_URL` - PostgreSQL connection
- `GOOGLE_CLOUD_PROJECT` - Vertex AI project
- `S3_*` - S3 storage credentials
- `STRIPE_SECRET_KEY_PROD` - Payment processing

**Edit .env:**
```bash
nano /var/www/lexi/.env
# After editing, restart service
systemctl restart lexi
```

## Security

### File Permissions
✅ **Secured** - Sensitive files are owner-only readable

```bash
# Verify permissions
ls -la /var/www/lexi/.env
ls -la /var/www/lexi/google-credentials.json

# Should show: -rw------- (600)
```

### SSL/HTTPS
- ✅ HTTPS enforcement enabled in production
- ✅ CSRF protection enabled
- ✅ Security headers configured
- ✅ Rate limiting active

### SSH Access
SSH key configured for GitHub push/pull
```bash
# View public key
cat ~/.ssh/id_ed25519.pub
```

## Troubleshooting

### Service Won't Start
```bash
# Check logs for errors
journalctl -u lexi -n 50

# Check if port 5000 is in use
lsof -i :5000

# Verify environment variables
python3.11 -c "from dotenv import load_dotenv; import os; load_dotenv(); print('DB:', os.getenv('DATABASE_URL')[:30])"
```

### Chat Returns 500 Error
```bash
# Check S3 service
python3.11 << 'EOF'
from dotenv import load_dotenv; load_dotenv()
from services import s3_service
print('S3 Enabled:', s3_service.enabled)
EOF

# Check Vertex AI
python3.11 << 'EOF'
from dotenv import load_dotenv; load_dotenv()
from services import vertex_ai_service
print('Vertex AI Enabled:', vertex_ai_service.enabled)
EOF

# Check recent errors
journalctl -u lexi --since "10 minutes ago" | grep -i error
```

### High Memory Usage
```bash
# Check memory
free -h

# Check gunicorn workers
ps aux | grep gunicorn

# Restart service to clear memory
systemctl restart lexi
```

### Disk Space Full
```bash
# Check disk usage
df -h

# Find large files
du -h /var/www/lexi | sort -rh | head -20

# Clean journal logs
journalctl --vacuum-size=100M
```

## Performance Tuning

### Gunicorn Workers
Configuration: `/var/www/lexi/gunicorn.conf.py`

```python
workers = 5  # Adjust based on CPU cores
worker_class = 'sync'
timeout = 120
```

After changing:
```bash
systemctl restart lexi
```

## Emergency Contacts

### Service Issues
- Check status: `lexi-status full`
- View logs: `journalctl -u lexi -f`
- Restart: `systemctl restart lexi`

### Database Issues
- Provider: Neon.tech
- Dashboard: https://console.neon.tech

### S3 Storage Issues
- Provider: your-objectstorage.com
- Endpoint: https://fsn1.your-objectstorage.com

## Regular Maintenance

### Daily
- ✅ Automatic: Log rotation
- ✅ Automatic: Database backups
- ✅ Automatic: Health checks

### Weekly
```bash
# Check system health
lexi-status full

# Check backup status
lexi-status backup

# Review error logs
journalctl -u lexi --since "7 days ago" | grep -i error | less
```

### Monthly
```bash
# Update dependencies
pip install --upgrade -r requirements.txt
npm update

# Review disk usage
df -h
du -h /var/www/lexi | sort -rh | head -20

# Test health endpoint
curl http://localhost:5000/health
```

### Quarterly
- Test backup restore process
- Review security configurations
- Update documentation

## Useful Commands Cheat Sheet

```bash
# Status & Health
lexi-status                    # Quick status
lexi-status full              # Full report
curl localhost:5000/health    # Health check

# Service Management
systemctl status lexi         # Status
systemctl restart lexi        # Restart
systemctl stop lexi           # Stop
systemctl start lexi          # Start

# Logs
journalctl -u lexi -f         # Live logs
journalctl -u lexi -n 100     # Last 100 lines
journalctl -u lexi --since "1 hour ago"

# Monitoring
ps aux | grep gunicorn        # Worker processes
free -h                       # Memory usage
df -h                         # Disk usage

# Database
python3.11 -c "from dotenv import load_dotenv; load_dotenv(); from main import app; from models import db; app.app_context().__enter__(); db.session.execute(db.text('SELECT 1')); print('DB OK')"

# Git
git status                    # Check status
git pull origin main          # Update code
git log -5 --oneline         # Recent commits
```

---

**Generated:** 2025-10-24
**Last Review:** 2025-10-24
