#!/bin/bash
# Safe document import wrapper

IMPORT_DIR="/tmp/cao_import"
LOG_DIR="/var/log/lexi"
LOG_FILE="$LOG_DIR/safe_import.log"

mkdir -p "$LOG_DIR"

echo "🟢 Starting safe document import..."
echo "   Directory: $IMPORT_DIR"
echo "   Log: $LOG_FILE"
echo ""

# Start import in background
python3 /var/www/lexi/import_documents_safe.py "$IMPORT_DIR" \
    >> "$LOG_FILE" 2>&1 &

IMPORT_PID=$!
echo "✅ Import process started (PID: $IMPORT_PID)"
echo "   Monitor with: tail -f $LOG_FILE"
echo "   Stop with: kill $IMPORT_PID"

# Save PID for tracking
echo "$IMPORT_PID" > /var/run/safe_import.pid

exit 0
