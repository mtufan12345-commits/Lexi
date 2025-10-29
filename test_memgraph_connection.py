#!/usr/bin/env python3
"""
Test Memgraph Connection
Tests connection to Memgraph from current environment
"""
import os
import sys

def test_memgraph():
    print("🔌 Testing Memgraph connection...")
    print("")
    
    # Get connection details from environment
    host = os.getenv('MEMGRAPH_HOST', '46.224.4.188')
    port = int(os.getenv('MEMGRAPH_PORT', 7687))
    
    print(f"Host: {host}")
    print(f"Port: {port}")
    print("")
    
    try:
        from gqlalchemy import Memgraph
        print("✅ gqlalchemy imported successfully")
    except ImportError as e:
        print(f"❌ gqlalchemy not available: {e}")
        print("\nInstall with: pip install gqlalchemy mgclient")
        sys.exit(1)
    
    try:
        memgraph = Memgraph(host=host, port=port)
        print("✅ Memgraph client created")
        
        # Test query
        result = list(memgraph.execute_and_fetch("RETURN 1 as test"))
        print("✅ Connection successful!")
        print(f"   Test query result: {result}")
        print("")
        
        # Show existing CAO documents
        print("📚 Querying existing documents...")
        caos = list(memgraph.execute_and_fetch("""
            MATCH (cao:CAO)
            OPTIONAL MATCH (cao)-[:CONTAINS_ARTICLE]->(article:Article)
            RETURN cao.name as cao_name, COUNT(article) as article_count
            ORDER BY cao.name
        """))
        
        if caos:
            print(f"\n📖 Found {len(caos)} document(s) in Memgraph:")
            total_articles = 0
            for cao in caos:
                article_count = cao['article_count']
                total_articles += article_count
                print(f"   • {cao['cao_name']}: {article_count} articles")
            print(f"\n📊 Total: {len(caos)} documents, {total_articles} articles")
        else:
            print("\n📚 No documents in Memgraph yet")
            print("   Ready for import via Super Admin dashboard!")
        
        print("\n✅ Memgraph is ready to use!")
        return True
        
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print("\n💡 Troubleshooting:")
        print("   1. Check if Memgraph is running:")
        print("      docker ps | grep memgraph")
        print("   2. Check firewall allows port 7687:")
        print(f"      telnet {host} {port}")
        print("   3. Verify MEMGRAPH_HOST and MEMGRAPH_PORT in .env")
        return False

if __name__ == "__main__":
    success = test_memgraph()
    sys.exit(0 if success else 1)
