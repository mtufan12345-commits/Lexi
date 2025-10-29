#!/bin/bash
# ==============================================================================
# Batch Processor Helper Script
# ==============================================================================
# Purpose: Manage system resources during document batch processing
# - Stops gunicorn to free up memory
# - Runs batch processor with optimal settings
# - Restarts gunicorn after completion
# ==============================================================================

set -e

# Configuration
BATCH_DIR="${1:-.}"
PATTERN="${2:-*.txt}"
LOG_FILE="/var/log/lexi/batch_processor_helper.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

function warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

function error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log "Starting batch processor helper..."
log "Directory: $BATCH_DIR"
log "Pattern: $PATTERN"

# Step 1: Stop Lexi service (gunicorn)
log "Stopping Lexi service to free up memory..."
systemctl stop lexi.service || warn "Could not stop lexi.service"
sleep 2

# Step 2: Kill any remaining gunicorn processes
log "Killing remaining gunicorn processes..."
killall -9 python3.11 2>/dev/null || true
sleep 1

# Step 3: Check memory availability
AVAILABLE_MEM=$(free -h | awk '/^Mem:/ {print $7}')
log "Available memory: $AVAILABLE_MEM"

# Step 4: Run batch processor
log "Starting batch processor..."
cd /var/www/lexi

python3 deepseek_batch_processor.py "$BATCH_DIR" --pattern "$PATTERN" 2>&1 | tee -a "$LOG_FILE"

BATCH_RESULT=$?

if [ $BATCH_RESULT -eq 0 ]; then
    log "Batch processing completed successfully!"
else
    error "Batch processing failed with exit code $BATCH_RESULT"
fi

# Step 5: Restart Lexi service
log "Restarting Lexi service..."
systemctl start lexi.service || error "Could not start lexi.service"
sleep 3

# Step 6: Verify service is running
if systemctl is-active --quiet lexi.service; then
    log "Lexi service restarted successfully"
else
    error "Lexi service failed to start. Check with: systemctl status lexi.service"
fi

# Step 7: Final status
log "Batch processor helper completed (exit code: $BATCH_RESULT)"
exit $BATCH_RESULT
