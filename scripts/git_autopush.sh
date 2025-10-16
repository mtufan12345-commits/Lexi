#!/bin/bash
# Automatic Git Sync - Runs every 5 minutes via Scheduled Deployment
# Safe backup script with error handling

set -e

echo "🔄 Starting git autopush at $(date)"

# Configure git (if not already set)
git config --global user.email "autopush@lexi-ai.nl" || true
git config --global user.name "Lexi Autopush" || true

# Pull latest changes first
echo "📥 Pulling latest changes..."
git pull origin main || {
    echo "⚠️ Pull failed - may need manual intervention"
    exit 0
}

# Check if there are any changes
if [[ -z $(git status -s) ]]; then
    echo "✅ No changes to commit"
    exit 0
fi

# Add all changes
echo "📝 Adding changes..."
git add .

# Commit with timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
git commit -m "autopush: $TIMESTAMP from Replit" || {
    echo "⚠️ Commit failed - possibly no changes"
    exit 0
}

# Push to remote
echo "🚀 Pushing to remote..."
git push origin main || {
    echo "❌ Push failed - check credentials and network"
    exit 1
}

echo "✅ Git autopush completed successfully at $(date)"
