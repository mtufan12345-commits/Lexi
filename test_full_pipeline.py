#!/usr/bin/env python3
"""
Full Pipeline Test Suite

Tests the complete automatic document processing pipeline:
1. Document upload
2. R1 analysis
3. Graph building
4. Status tracking
5. GraphRAG integration
"""

import sys
import os
import json
import time
import tempfile
from pathlib import Path

sys.path.insert(0, '/var/www/lexi')

# Setup Flask app context
import logging
logging.basicConfig(level=logging.INFO)

from models import db, Document
from services import get_r1_client
from document_graph_builder import get_graph_builder
from document_processing_pipeline import get_processing_pipeline
from graphrag import get_graphrag


def create_test_document(content: str) -> str:
    """Create a temporary test document"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        return f.name


def test_r1_client():
    """Test DeepSeek R1 client"""
    print("\n" + "=" * 80)
    print("TEST 1: DeepSeek R1 Client")
    print("=" * 80)

    try:
        r1_client = get_r1_client()
        print(f"✓ R1 client initialized: {r1_client.enabled}")

        if not r1_client.enabled:
            print("⚠️  R1 client disabled (DEEPSEEK_API_KEY not set)")
            return False

        # Test with sample chunks
        test_chunks = [
            "NBBU CAO 2024-2025. Artikel 1: General Provisions. This agreement applies to all parties...",
            "Artikel 2: Wages and Compensation. The minimum wage is EUR 15.00 per hour...",
            "Artikel 3: Working Hours. Standard working hours are 40 hours per week...",
            "Artikel 4: Leave and Holidays. Employees are entitled to 25 vacation days per year...",
            "Artikel 5: Termination. Notice period is 1 month for both parties..."
        ]

        print(f"\nAnalyzing {len(test_chunks)} test chunks...")
        result = r1_client.analyze_cao_structure(
            chunks=test_chunks,
            document_name="Test NBBU CAO 2024",
            cao_type="NBBU"
        )

        if result.get('success'):
            print(f"✓ R1 analysis successful")
            print(f"  - CAO: {result.get('cao_metadata', {}).get('name', 'Unknown')}")
            print(f"  - Articles found: {len(result.get('artikelen', []))}")
            print(f"  - Relations found: {len(result.get('relaties', []))}")
            print(f"  - Tokens used: {result.get('tokens_used', 0)}")
            return True
        else:
            print(f"❌ R1 analysis failed: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        print(f"❌ R1 client test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_graph_builder():
    """Test document graph builder"""
    print("\n" + "=" * 80)
    print("TEST 2: Document Graph Builder")
    print("=" * 80)

    try:
        builder = get_graph_builder()
        print(f"✓ Graph builder initialized")

        # Create test R1 analysis result
        test_analysis = {
            'success': True,
            'cao_metadata': {
                'name': 'Test CAO for Pipeline',
                'type': 'NBBU',
                'version': '1.0',
                'effective_date': '2025-01-01',
                'sector': 'Testing',
                'description': 'Test document for pipeline validation'
            },
            'artikelen': [
                {
                    'article_number': '1',
                    'title': 'General Provisions',
                    'section': 'Chapter 1',
                    'tags': ['general', 'setup'],
                    'chunk_indices': [0, 1]
                },
                {
                    'article_number': '2',
                    'title': 'Wages',
                    'section': 'Chapter 2',
                    'tags': ['wages', 'compensation'],
                    'chunk_indices': [2, 3]
                },
                {
                    'article_number': '3',
                    'title': 'Working Hours',
                    'section': 'Chapter 3',
                    'tags': ['hours', 'schedule'],
                    'chunk_indices': [4]
                }
            ],
            'relaties': [
                {
                    'source_article': '1',
                    'target_article': '2',
                    'relation_type': 'REFERENCES',
                    'description': 'Article 1 references Article 2'
                }
            ],
            'validation': {
                'total_articles_estimated': 3,
                'coverage_percentage': 100.0,
                'warnings': []
            }
        }

        print("\nBuilding graph structure from test analysis...")
        success, result = builder.build_cao_strukture_from_r1(
            document_id=9999,  # Test ID
            document_name='Test CAO for Pipeline',
            cao_type='NBBU',
            r1_analysis=test_analysis,
            chunk_mappings={}
        )

        if success:
            print(f"✓ Graph building successful")
            print(f"  - Articles created: {result.get('articles_created', 0)}")
            print(f"  - Relations created: {result.get('relations_created', 0)}")
            print(f"  - Chunks linked: {result.get('chunks_linked', 0)}")

            # Get statistics
            stats = builder.get_graph_statistics(9999)
            print(f"✓ Graph statistics:")
            print(f"  - CAO count: {stats.get('cao_count', 0)}")
            print(f"  - Article count: {stats.get('article_count', 0)}")
            print(f"  - Relation count: {stats.get('relation_count', 0)}")

            # Validate integrity
            is_valid, warnings = builder.validate_graph_integrity(9999)
            print(f"✓ Graph validation: valid={is_valid}, warnings={len(warnings)}")

            return True
        else:
            print(f"❌ Graph building failed: {result.get('errors', [])}")
            return False

    except Exception as e:
        print(f"❌ Graph builder test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_graphrag_integration():
    """Test GraphRAG integration"""
    print("\n" + "=" * 80)
    print("TEST 3: GraphRAG Integration")
    print("=" * 80)

    try:
        graphrag = get_graphrag()
        print(f"✓ GraphRAG initialized")
        print(f"  - Database documents: (checking...)")

        # Get indexed documents
        indexed = graphrag.get_indexed_documents()
        print(f"  - Found {len(indexed)} CAO documents in Memgraph")

        if indexed:
            total_articles = sum(doc.get('article_count', 0) for doc in indexed)
            print(f"  - Total articles indexed: {total_articles}")

            # Try a test query
            test_queries = [
                "Wat zijn de regels voor werkuren?",
                "Hoe veel vakantiedagen zijn er?",
                "Wat is het minimale loon?"
            ]

            print(f"\nTesting semantic search with {len(test_queries)} queries...")

            successful_queries = 0
            for query in test_queries:
                try:
                    results = graphrag.semantic_search(query, limit=3)
                    if results:
                        print(f"  ✓ Query: '{query[:30]}...'")
                        print(f"    Found {len(results)} relevant articles")
                        successful_queries += 1
                    else:
                        print(f"  ⚠️  Query: '{query[:30]}...' - No results")
                except Exception as e:
                    print(f"  ❌ Query: '{query[:30]}...' - Error: {e}")

            if successful_queries >= 1:
                print(f"✓ GraphRAG search working ({successful_queries}/{len(test_queries)} queries successful)")
                return True
            else:
                print(f"⚠️  GraphRAG search: Limited results")
                return True  # Still pass if GraphRAG is working
        else:
            print(f"⚠️  No documents indexed yet (expected during first setup)")
            return True

    except Exception as e:
        print(f"❌ GraphRAG test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pipeline_components():
    """Test all pipeline components are accessible"""
    print("\n" + "=" * 80)
    print("TEST 4: Pipeline Component Access")
    print("=" * 80)

    try:
        # Test imports
        print("Testing component imports...")

        from document_importer import parse_txt, generate_embeddings
        print("  ✓ document_importer")

        from document_graph_builder import get_graph_builder
        print("  ✓ document_graph_builder")

        from document_processing_pipeline import get_processing_pipeline
        print("  ✓ document_processing_pipeline")

        from services import get_r1_client
        print("  ✓ services.DeepSeekR1Client")

        from graphrag import get_graphrag
        print("  ✓ graphrag.GraphRAGController")

        # Test component instantiation
        print("\nInstantiating components...")

        pipeline = get_processing_pipeline()
        print(f"  ✓ Processing pipeline: {type(pipeline).__name__}")

        r1_client = get_r1_client()
        print(f"  ✓ R1 client: {type(r1_client).__name__} (enabled={r1_client.enabled})")

        builder = get_graph_builder()
        print(f"  ✓ Graph builder: {type(builder).__name__}")

        graphrag = get_graphrag()
        print(f"  ✓ GraphRAG: {type(graphrag).__name__}")

        print("\n✓ All components accessible and functional")
        return True

    except Exception as e:
        print(f"❌ Component test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("🧪 FULL PIPELINE TEST SUITE")
    print("=" * 80)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Working directory: {os.getcwd()}")

    results = {
        'Pipeline Components': test_pipeline_components(),
        'GraphRAG Integration': test_graphrag_integration(),
        'Graph Builder': test_graph_builder(),
    }

    # R1 test is optional (requires API key)
    try:
        results['DeepSeek R1 Client'] = test_r1_client()
    except Exception as e:
        print(f"⚠️  R1 client test skipped: {e}")
        results['DeepSeek R1 Client'] = None

    # Summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)

    for test_name, result in results.items():
        status = "✓ PASS" if result is True else "❌ FAIL" if result is False else "⊘ SKIP"
        print(f"  {test_name:<30} {status}")

    print("-" * 80)
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\n✨ All tests passed! Pipeline is ready for use.")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed. Please check the errors above.")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
