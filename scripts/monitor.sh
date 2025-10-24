#!/bin/bash
# Lexi Production Monitoring Script
# Run this script to check system health

set -e

echo "=========================================="
echo "LEXI PRODUCTION MONITORING"
echo "=========================================="
echo "Timestamp: $(date)"
echo ""

# Service Status
echo "📊 SERVICE STATUS"
echo "------------------------------------------"
systemctl is-active --quiet lexi && echo "✓ Service: RUNNING" || echo "✗ Service: STOPPED"
echo "  Uptime: $(systemctl show lexi --property=ActiveEnterTimestamp --value | cut -d' ' -f2-)"
echo "  Workers: $(ps aux | grep gunicorn | grep -v grep | wc -l)"
echo ""

# Health Check
echo "🏥 HEALTH CHECK"
echo "------------------------------------------"
curl -s http://localhost:5000/health | python3.11 -m json.tool || echo "✗ Health check failed"
echo ""

# Disk Usage
echo "💾 DISK USAGE"
echo "------------------------------------------"
df -h / | tail -1 | awk '{print "  Used: "$3" / "$2" ("$5")"}'
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    echo "  ⚠️  WARNING: Disk usage above 80%"
fi
echo ""

# Memory Usage
echo "🧠 MEMORY USAGE"
echo "------------------------------------------"
free -h | grep Mem | awk '{print "  Used: "$3" / "$2" ("int($3/$2*100)"%)"}'
echo ""

# Recent Errors
echo "⚠️  RECENT ERRORS (last 10 min)"
echo "------------------------------------------"
ERROR_COUNT=$(journalctl -u lexi --since "10 minutes ago" --no-pager | grep -iE "error|exception|fail" | grep -v "SIGTERM\|errorlog" | wc -l)
echo "  Errors: $ERROR_COUNT"
if [ $ERROR_COUNT -gt 0 ]; then
    journalctl -u lexi --since "10 minutes ago" --no-pager | grep -iE "error|exception|fail" | grep -v "SIGTERM\|errorlog" | tail -5
fi
echo ""

# Database Connection
echo "🗄️  DATABASE"
echo "------------------------------------------"
python3.11 << 'EOF'
import os
os.chdir('/var/www/lexi')
from dotenv import load_dotenv
load_dotenv()
from main import app
from models import db
with app.app_context():
    try:
        db.session.execute(db.text('SELECT 1'))
        print("  ✓ Connected")
    except Exception as e:
        print(f"  ✗ Error: {str(e)[:50]}")
EOF
echo ""

# S3 Storage
echo "☁️  S3 STORAGE"
echo "------------------------------------------"
python3.11 << 'EOF'
import os
os.chdir('/var/www/lexi')
from dotenv import load_dotenv
load_dotenv()
from services import s3_service
print(f"  Status: {'✓ Enabled' if s3_service.enabled else '✗ Disabled'}")
EOF
echo ""

echo "=========================================="
echo "Monitoring complete"
echo "=========================================="
