#!/bin/bash
echo "Installing gqlalchemy and sentence-transformers..."
python3 << 'PYEOF'
import sys
import subprocess
import json

packages = ['gqlalchemy', 'sentence-transformers']

for pkg in packages:
    print(f"\n📦 Installing {pkg}...")
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '--upgrade', pkg, '--break-system-packages'],
        capture_output=True,
        text=True,
        timeout=300
    )
    
    if result.returncode == 0:
        print(f"✅ {pkg} installed successfully")
    else:
        print(f"❌ {pkg} failed")
        print("Error:", result.stderr[-200:] if result.stderr else "Unknown error")

# Verify installation
print("\n🔍 Verifying installations...")
for pkg in packages:
    try:
        __import__(pkg.replace('-', '_'))
        print(f"✅ {pkg} verified")
    except:
        print(f"❌ {pkg} not found")
PYEOF
