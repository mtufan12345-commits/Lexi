#!/usr/bin/env python3
"""
GraphRAG Test Suite
Test the complete GraphRAG pipeline with real queries
"""

import sys
sys.path.insert(0, '/var/www/lexi')

from graphrag import get_graphrag
import json
from datetime import datetime


def test_graphrag():
    """Run comprehensive GraphRAG tests"""

    print("\n" + "=" * 80)
    print("🧪 GRAPHRAG COMPREHENSIVE TEST SUITE")
    print("=" * 80)

    # Initialize GraphRAG
    print("\n1️⃣  Initializing GraphRAG...")
    try:
        graphrag = get_graphrag()
        print("   ✅ GraphRAG initialized successfully")
    except Exception as e:
        print(f"   ❌ Failed to initialize: {e}")
        return

    # Test queries
    test_queries = [
        {
            "query": "Wat zijn de regels voor vakantie en verlof?",
            "category": "Vakantie"
        },
        {
            "query": "Hoe lang duurt een arbeidsovereenkomst?",
            "category": "Arbeidsovereenkomst"
        },
        {
            "query": "Wat is het minimale loon?",
            "category": "Loon"
        },
        {
            "query": "Welke rechten heb ik bij gelijke behandeling?",
            "category": "Discriminatie"
        },
        {
            "query": "Wat zijn de regels voor CAO?",
            "category": "CAO"
        },
    ]

    results = []

    print(f"\n2️⃣  Running {len(test_queries)} test queries...\n")

    for idx, test in enumerate(test_queries, 1):
        query = test['query']
        category = test['category']

        print(f"   [{idx}/{len(test_queries)}] {category}: '{query}'")

        try:
            result = graphrag.query(query)

            # Validate grounding
            is_grounded = graphrag.validate_grounding(result['sources'])

            test_result = {
                'query': query,
                'category': category,
                'timestamp': datetime.now().isoformat(),
                'success': True,
                'grounded': is_grounded,
                'sources_count': len(result['sources']),
                'sources': [
                    {
                        'cao': s['cao'],
                        'article': s['article'],
                        'similarity': round(s['similarity'], 3)
                    }
                    for s in result['sources']
                ],
                'answer_preview': result['answer'][:200] + "..."
            }

            results.append(test_result)

            print(f"       ✅ Found {len(result['sources'])} sources")
            if result['sources']:
                print(f"       📄 Top source: {result['sources'][0]['cao_name']} (similarity: {result['sources'][0]['similarity']:.2f})")
            print(f"       🔒 Grounded: {is_grounded}")

        except Exception as e:
            test_result = {
                'query': query,
                'category': category,
                'timestamp': datetime.now().isoformat(),
                'success': False,
                'error': str(e)
            }
            results.append(test_result)
            print(f"       ❌ Error: {e}")

        print()

    # Summary
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)

    successful = sum(1 for r in results if r['success'])
    grounded = sum(1 for r in results if r.get('grounded', False))
    total_sources = sum(r.get('sources_count', 0) for r in results)

    print(f"\n✅ Successful queries: {successful}/{len(test_queries)}")
    print(f"🔒 Grounded answers: {grounded}/{successful}")
    print(f"📄 Total sources found: {total_sources}")

    # Details
    print(f"\nQuery Details:")
    for r in results:
        if r['success']:
            print(f"  • {r['category']:<20s} - {r['sources_count']} sources - Grounded: {r['grounded']}")
        else:
            print(f"  • {r['category']:<20s} - ERROR: {r['error'][:50]}")

    # Save results
    output_file = '/tmp/graphrag_test_results.json'
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'database': {
                'documents': 27,
                'articles': 4354
            },
            'tests': results,
            'summary': {
                'total_queries': len(test_queries),
                'successful': successful,
                'grounded': grounded,
                'total_sources': total_sources
            }
        }, f, indent=2)

    print(f"\n💾 Results saved to: {output_file}")
    print("=" * 80)


if __name__ == "__main__":
    test_graphrag()
