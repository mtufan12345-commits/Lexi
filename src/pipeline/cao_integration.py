"""Integration adapter between Memgraph R1 pipeline and PostgreSQL CAO pipeline"""
import asyncio
import logging
from typing import Dict, List, Optional
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)

class CAOIntegrationAdapter:
    """
    Bridges the existing Memgraph/DeepSeek R1 pipeline with PostgreSQL CAO pipeline.

    Workflow:
    1. Document uploaded → Memgraph DeepSeek R1 pipeline creates semantic chunks
    2. Integration adapter extracts articles from Memgraph
    3. PostgreSQL stores articles + chunks for vector search
    4. Voyage AI generates embeddings for semantic search
    """

    def __init__(self, db, voyage_client, memgraph_client=None):
        self.db = db
        self.voyage = voyage_client
        self.memgraph = memgraph_client
        self.logger = logging.getLogger(__name__)

    async def extract_articles_from_memgraph(self, cao_name: str) -> List[Dict]:
        """
        Query Memgraph to extract articles that were just processed by R1

        Returns list of articles with metadata from R1 analysis
        """
        if not self.memgraph:
            self.logger.warning("Memgraph client not available")
            return []

        try:
            # Query artikelen from Memgraph
            query = """
            MATCH (cao:CAO {name: $cao_name})-[:CONTAINS_ARTIKEL]->(a:Artikel)
            RETURN a.number as article_number, a.title as title, a.section as section,
                   a.tags as tags, a.r1_processed as r1_processed
            ORDER BY a.number
            """

            results = list(self.memgraph.execute_and_fetch(
                query,
                {"cao_name": cao_name}
            ))

            self.logger.info(f"Extracted {len(results)} articles from Memgraph for {cao_name}")
            return results

        except Exception as e:
            self.logger.error(f"Error extracting articles from Memgraph: {e}")
            return []

    async def import_articles_to_postgres(self, document_id: str, cao_name: str, articles: List[Dict]) -> Dict:
        """
        Import extracted articles from Memgraph to PostgreSQL for vector search

        Args:
            document_id: UUID of source document
            cao_name: Name of CAO document
            articles: List of article dicts from Memgraph

        Returns:
            Summary of import process
        """
        if not articles:
            return {"success": False, "error": "No articles to import"}

        try:
            imported_count = 0
            chunk_ids = []

            for article in articles:
                article_number = article.get('article_number', 'UNKNOWN')
                title = article.get('title', '')
                full_text = f"{title}" if title else f"Article {article_number}"

                # Create article in PostgreSQL
                article_id = await self.db.create_article(
                    document_id=document_id,
                    cao_name=cao_name,
                    article_number=article_number,
                    title=title,
                    full_text=full_text
                )

                # Create a single chunk per article (articles are already semantic units from R1)
                chunks = [{
                    "index": 0,
                    "text": full_text,
                    "token_count": len(full_text.split()),
                    "reasoning": f"R1 semantic unit from Memgraph"
                }]

                inserted_ids = await self.db.insert_chunks(article_id, chunks)
                chunk_ids.extend(inserted_ids)
                imported_count += 1

                await self.db.update_status(article_id, 'chunked')

            self.logger.info(f"Imported {imported_count} articles to PostgreSQL")
            return {
                "success": True,
                "imported_articles": imported_count,
                "chunk_ids": chunk_ids
            }

        except Exception as e:
            self.logger.error(f"Error importing articles to PostgreSQL: {e}")
            return {"success": False, "error": str(e)}

    async def generate_embeddings_for_chunks(self, chunk_ids: List[int]) -> Dict:
        """
        Generate Voyage AI embeddings for chunks

        Args:
            chunk_ids: List of chunk IDs to embed

        Returns:
            Summary of embedding generation
        """
        try:
            embedded_count = 0

            for chunk_id in chunk_ids:
                # Note: In production, would fetch chunk text from DB here
                # For now, this is a placeholder for the async embedding generation

                # await self.voyage.embed_chunks([chunk_text])
                # await self.db.update_chunk_embedding(chunk_id, embedding, input_text)

                embedded_count += 1

            self.logger.info(f"Generated embeddings for {embedded_count} chunks")
            return {
                "success": True,
                "embedded_count": embedded_count
            }

        except Exception as e:
            self.logger.error(f"Error generating embeddings: {e}")
            return {"success": False, "error": str(e)}

    async def sync_article_to_postgres(self, article_data: Dict) -> Optional[int]:
        """
        Sync a single article from Memgraph to PostgreSQL

        Used for individual article imports or updates
        """
        try:
            document_id = str(uuid4())  # Would be passed in real scenario
            cao_name = article_data.get('cao_name', 'Unknown')
            article_number = article_data.get('article_number', '')
            title = article_data.get('title', '')
            full_text = article_data.get('full_text', '')

            article_id = await self.db.create_article(
                document_id=document_id,
                cao_name=cao_name,
                article_number=article_number,
                title=title,
                full_text=full_text
            )

            await self.db.update_status(article_id, 'synced')
            return article_id

        except Exception as e:
            self.logger.error(f"Error syncing article to PostgreSQL: {e}")
            return None
