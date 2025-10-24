#!/bin/bash
# Backup Verification Script
# Checks backup status for all critical data

echo "=========================================="
echo "BACKUP STATUS CHECK"
echo "=========================================="
echo "Timestamp: $(date)"
echo ""

# Database Backup (Neon.tech)
echo "🗄️  DATABASE BACKUP (Neon.tech)"
echo "------------------------------------------"
echo "  Provider: Neon.tech"
echo "  Type: Automated daily snapshots"
echo "  Retention: 7 days (free tier) / 30 days (paid)"
echo "  Status: ✓ Managed by Neon.tech"
echo "  Recovery: Via Neon.tech dashboard"
echo ""

# S3 Storage Backup
echo "☁️  S3 STORAGE BACKUP"
echo "------------------------------------------"
python3.11 << 'EOF'
import os
os.chdir('/var/www/lexi')
from dotenv import load_dotenv
load_dotenv()
from services import s3_service
import boto3

if s3_service.enabled:
    print("  Status: ✓ Enabled")
    print(f"  Bucket: {s3_service.bucket}")
    print(f"  Endpoint: {s3_service.endpoint}")

    # Check if versioning is enabled
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=s3_service.endpoint,
            aws_access_key_id=s3_service.access_key,
            aws_secret_access_key=s3_service.secret_key
        )
        versioning = s3.get_bucket_versioning(Bucket=s3_service.bucket)
        if versioning.get('Status') == 'Enabled':
            print("  Versioning: ✓ Enabled")
        else:
            print("  Versioning: ⚠️  Not enabled (recommended)")
    except Exception as e:
        print(f"  Versioning: ⚠️  Could not check")
else:
    print("  Status: ✗ Disabled")
EOF
echo ""

# Code Backup (GitHub)
echo "📦 CODE BACKUP (GitHub)"
echo "------------------------------------------"
cd /var/www/lexi
CURRENT_BRANCH=$(git branch --show-current)
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/$CURRENT_BRANCH)

echo "  Repository: github.com:mtufan12345-commits/Lexi.git"
echo "  Branch: $CURRENT_BRANCH"
echo "  Local commit: ${LOCAL_COMMIT:0:7}"
echo "  Remote commit: ${REMOTE_COMMIT:0:7}"

if [ "$LOCAL_COMMIT" == "$REMOTE_COMMIT" ]; then
    echo "  Sync status: ✓ In sync"
else
    echo "  Sync status: ⚠️  Out of sync"
fi
echo ""

# Configuration Files
echo "⚙️  CONFIGURATION BACKUP"
echo "------------------------------------------"
echo "  .env file: $([ -f .env ] && echo '✓ Exists' || echo '✗ Missing')"
echo "  google-credentials.json: $([ -f google-credentials.json ] && echo '✓ Exists' || echo '✗ Missing')"
echo "  systemd service: $([ -f /etc/systemd/system/lexi.service ] && echo '✓ Exists' || echo '✗ Missing')"
echo ""
echo "  ⚠️  NOTE: These files are NOT in git (contain secrets)"
echo "  Recommendation: Keep encrypted backup of .env and credentials"
echo ""

# Backup Recommendations
echo "💡 RECOMMENDATIONS"
echo "------------------------------------------"
echo "1. Enable S3 versioning for automatic file recovery"
echo "2. Create manual backup of .env and credentials (encrypted)"
echo "3. Document recovery procedures"
echo "4. Test restore process quarterly"
echo ""

echo "=========================================="
echo "Backup check complete"
echo "=========================================="
