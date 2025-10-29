#!/bin/bash
# ==============================================================================
# Lexi AI - Install Memgraph + DeepSeek RAG Dependencies on Hetzner
# ==============================================================================
# Run this script on your Hetzner server (46.224.4.188)
# Usage: ssh root@46.224.4.188 < install_memgraph_deps.sh
# ==============================================================================

set -e  # Exit on error

echo "🚀 Installing Memgraph + DeepSeek RAG dependencies on Hetzner..."
echo ""

# Navigate to project directory
cd /var/www/lexi

# Activate virtual environment
source venv/bin/activate

echo "📦 Installing Python ML dependencies..."
pip install --no-cache-dir --upgrade pip

# Install dependencies (may take 5-10 minutes for torch/sentence-transformers)
pip install --no-cache-dir \
    gqlalchemy==1.6.0 \
    sentence-transformers==2.2.2 \
    torch==2.1.0 \
    PyPDF2==3.0.1 \
    python-docx==1.2.0 \
    mgclient

echo ""
echo "✅ Dependencies installed!"
echo ""

# Test imports
echo "🧪 Testing imports..."
python3 << 'EOF'
import sys
try:
    import gqlalchemy
    print("✅ gqlalchemy:", gqlalchemy.__version__)
except Exception as e:
    print("❌ gqlalchemy:", str(e))
    sys.exit(1)

try:
    import sentence_transformers
    print("✅ sentence-transformers:", sentence_transformers.__version__)
except Exception as e:
    print("❌ sentence-transformers:", str(e))
    sys.exit(1)

try:
    import torch
    print("✅ torch:", torch.__version__)
except Exception as e:
    print("❌ torch:", str(e))
    sys.exit(1)

try:
    from PyPDF2 import PdfReader
    print("✅ PyPDF2: OK")
except Exception as e:
    print("❌ PyPDF2:", str(e))
    sys.exit(1)

print("\n🎉 All dependencies installed successfully!")
EOF

echo ""
echo "🔌 Testing Memgraph connection..."
python3 << 'EOF'
import os
from gqlalchemy import Memgraph

try:
    memgraph = Memgraph(
        host=os.getenv('MEMGRAPH_HOST', '46.224.4.188'),
        port=int(os.getenv('MEMGRAPH_PORT', 7687))
    )
    
    # Test query
    result = list(memgraph.execute_and_fetch("RETURN 1 as test"))
    print("✅ Memgraph connection successful!")
    print(f"   Host: {os.getenv('MEMGRAPH_HOST', '46.224.4.188')}")
    print(f"   Port: {os.getenv('MEMGRAPH_PORT', 7687)}")
    
    # Show existing CAO documents
    caos = list(memgraph.execute_and_fetch("""
        MATCH (cao:CAO)
        OPTIONAL MATCH (cao)-[:CONTAINS_ARTICLE]->(article:Article)
        RETURN cao.name as cao_name, COUNT(article) as article_count
        ORDER BY cao.name
    """))
    
    if caos:
        print(f"\n📚 Existing documents in Memgraph: {len(caos)}")
        for cao in caos:
            print(f"   - {cao['cao_name']}: {cao['article_count']} articles")
    else:
        print("\n📚 No documents in Memgraph yet - ready for import!")
        
except Exception as e:
    print(f"❌ Memgraph connection failed: {e}")
    print("\n💡 Make sure Memgraph is running:")
    print("   docker ps | grep memgraph")
    print("   docker start <memgraph-container>")
    import sys
    sys.exit(1)
EOF

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Next steps:"
echo "1. Restart Lexi service: sudo systemctl restart lexi"
echo "2. Check service status: sudo systemctl status lexi"
echo "3. Upload documents via Super Admin dashboard: https://lexiai.nl/super-admin/documents"
echo ""
