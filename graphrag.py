#!/usr/bin/env python3
"""
GraphRAG Module for Lexi AI
Strict grounding-aware RAG system for juridical documents
- Only retrieves from uploaded documents in Memgraph
- NEVER makes internet requests
- Provides source citations
"""

import os
from typing import List, Dict, Tuple, Optional
from sentence_transformers import SentenceTransformer
from gqlalchemy import Memgraph
import json


class GraphRAGController:
    """
    GraphRAG system with strict grounding for juridical documents
    """

    def __init__(self):
        """Initialize GraphRAG with Memgraph and embedding model"""
        print("🚀 Initializing GraphRAG...")

        # Memgraph connection
        self.memgraph_host = os.getenv('MEMGRAPH_HOST', '46.224.4.188')
        self.memgraph_port = int(os.getenv('MEMGRAPH_PORT', 7687))
        self.memgraph = Memgraph(host=self.memgraph_host, port=self.memgraph_port)

        # Test connection
        try:
            list(self.memgraph.execute_and_fetch("RETURN 1"))
            print(f"   ✅ Connected to Memgraph ({self.memgraph_host}:{self.memgraph_port})")
        except Exception as e:
            print(f"   ❌ Error connecting to Memgraph: {e}")
            raise

        # Embedding model (cached globally)
        print("   ⏳ Loading embedding model...")
        self.embedding_model = SentenceTransformer('intfloat/multilingual-e5-large')
        print("   ✅ Embedding model loaded")

        # Get database stats
        caos = self.get_indexed_documents()
        total_articles = sum(cao['article_count'] for cao in caos)
        print(f"   📊 Database: {len(caos)} documents, {total_articles} articles")

    def get_indexed_documents(self) -> List[Dict]:
        """Get list of all indexed documents (for grounding validation)"""
        try:
            results = list(self.memgraph.execute_and_fetch("""
                MATCH (cao:CAO)
                OPTIONAL MATCH (cao)-[:CONTAINS_ARTICLE]->(article:Article)
                RETURN cao.name as cao_name, COUNT(article) as article_count
                ORDER BY cao_name
            """))
            return results
        except Exception as e:
            print(f"   ⚠️  Error fetching documents: {e}")
            return []

    def semantic_search(self, query: str, limit: int = 5, threshold: float = 0.65) -> List[Dict]:
        """
        Semantic search in Memgraph (GROUNDED - only uses indexed documents)

        Args:
            query: User question
            limit: Max results to return
            threshold: Minimum similarity score (0-1)

        Returns:
            List of relevant articles with sources
        """
        try:
            # Generate embedding for query
            query_embedding = self.embedding_model.encode(query, convert_to_tensor=False).tolist()

            # Search in Memgraph using similarity-based retrieval
            # Since Memgraph vector search may not be available, we use a simpler approach:
            # Match all articles and score them based on embedding similarity in Python
            cypher = """
            MATCH (cao:CAO)-[:CONTAINS_ARTICLE]->(article:Article)
            RETURN
                article.article_number as article_number,
                article.content as content,
                article.cao as cao,
                cao.name as cao_name,
                cao.source as source
            LIMIT 1000
            """

            results = list(self.memgraph.execute_and_fetch(cypher))

            # Score and rank results (client-side similarity)
            scored_results = []
            for result in results:
                # Create embedding for article content
                content = result.get('content', '')
                if not content:
                    continue

                content_embedding = self.embedding_model.encode(content, convert_to_tensor=False).tolist()

                # Calculate cosine similarity
                similarity = self._cosine_similarity(query_embedding, content_embedding)

                if similarity >= threshold:
                    scored_results.append({
                        'article_number': result['article_number'],
                        'content': content,
                        'cao_name': result['cao_name'],
                        'similarity': similarity,
                        'source': result.get('source', 'indexed')
                    })

            # Sort by similarity and return top results
            scored_results.sort(key=lambda x: x['similarity'], reverse=True)
            return scored_results[:limit]

        except Exception as e:
            print(f"   ❌ Search error: {e}")
            return []

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = sum(a ** 2 for a in vec1) ** 0.5
        mag2 = sum(b ** 2 for b in vec2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def build_context(self, search_results: List[Dict], max_tokens: int = 2000) -> Tuple[str, List[str]]:
        """
        Build context for LLM from search results

        Args:
            search_results: Results from semantic_search
            max_tokens: Max tokens in context (approximate)

        Returns:
            (context_string, sources_list)
        """
        context = []
        sources = []
        token_count = 0

        for result in search_results:
            # Estimate tokens (rough: 1 token ≈ 4 characters)
            content_tokens = len(result['content']) // 4

            if token_count + content_tokens > max_tokens:
                break

            context.append(
                f"\n📄 {result['cao_name']} (Article {result['article_number']}, similarity: {result['similarity']:.2f}):\n"
                f"{result['content']}\n"
            )

            sources.append({
                'cao': result['cao_name'],
                'article': result['article_number'],
                'similarity': result['similarity']
            })

            token_count += content_tokens

        return "".join(context), sources

    def query(
        self,
        user_question: str,
        deepseek_service=None,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Full GraphRAG query pipeline (grounded Q&A)

        Args:
            user_question: User's question
            deepseek_service: Optional DeepSeek service for LLM response
            conversation_history: Optional conversation history

        Returns:
            {
                'answer': str,
                'sources': List[Dict],
                'grounded': bool,
                'context_used': str
            }
        """
        # Step 1: Semantic search (grounded to indexed documents only)
        print(f"🔍 Searching for: '{user_question}'")
        search_results = self.semantic_search(user_question, limit=5)

        if not search_results:
            return {
                'answer': "Helaas kan ik geen relevante informatie vinden in de beschikbare documenten voor uw vraag.",
                'sources': [],
                'grounded': False,
                'context_used': "No matching documents found"
            }

        # Step 2: Build context from search results
        context, sources = self.build_context(search_results)

        # Step 3: Call DeepSeek with grounding constraints
        if deepseek_service and deepseek_service.enabled:
            # Build system instruction with grounding constraints
            system_instruction = """Je bent Lexi, een juridisch assistent.

KRITIEK - JE MAG NOOIT:
- Op het internet zoeken
- Informatie buiten de gegeven context gebruiken
- Jezelf aanpassen aan vragen buiten jouw knowledge base
- Speculeren over wetten/regelingen die niet in de context staan

REGELS:
1. Antwoord ALLEEN op basis van de gegeven documentcontext
2. Citeer altijd de bron (documento + artikelnummer)
3. Zeg expliciet als informatie niet in je documenten staat
4. Wees voorzichtig met interpretatie van juridische teksten
5. Raad aan om rechtsgeleiding in te winnen voor complexe vragen

Context documenten:
{context}"""

            try:
                response = deepseek_service.chat(
                    user_question,
                    conversation_history=conversation_history,
                    system_instruction=system_instruction.format(context=context)
                )

                return {
                    'answer': response,
                    'sources': sources,
                    'grounded': True,
                    'context_used': context
                }
            except Exception as e:
                print(f"⚠️  DeepSeek error: {e}")
                # Fallback: Return context-based response
                pass

        # Fallback: Return structured context without LLM
        return {
            'answer': f"Op basis van de beschikbare documenten:\n\n{context}",
            'sources': sources,
            'grounded': True,
            'context_used': context
        }

    def validate_grounding(self, sources: List[Dict]) -> bool:
        """Validate that all sources are from indexed documents"""
        indexed_docs = {doc['cao_name'] for doc in self.get_indexed_documents()}

        for source in sources:
            if source['cao'] not in indexed_docs:
                return False

        return True


# Global GraphRAG instance
_graphrag_instance = None


def get_graphrag() -> GraphRAGController:
    """Get or create global GraphRAG instance"""
    global _graphrag_instance
    if _graphrag_instance is None:
        _graphrag_instance = GraphRAGController()
    return _graphrag_instance


if __name__ == "__main__":
    # Test GraphRAG
    graphrag = get_graphrag()

    # Test query
    test_queries = [
        "Wat zijn de regels voor vakantie?",
        "Hoe lang mag een arbeidsovereenkomst geduurd?",
        "Wat is een CAO?",
    ]

    print("\n" + "=" * 80)
    print("🧪 GRAPHRAG TEST")
    print("=" * 80)

    for query in test_queries:
        print(f"\n❓ Query: {query}")
        result = graphrag.query(query)
        print(f"✅ Grounded: {result['grounded']}")
        print(f"📊 Sources: {len(result['sources'])}")
        print(f"💬 Answer preview: {result['answer'][:200]}...")
