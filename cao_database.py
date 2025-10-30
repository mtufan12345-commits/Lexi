#!/usr/bin/env python3
"""
PostgreSQL CAO Database Helper Functions
Handles all database operations for CAO processing pipeline
"""

import asyncio
import asyncpg
import os
from uuid import UUID
from typing import List, Dict, Optional
from datetime import datetime

# Database connection from .env
DATABASE_URL = os.getenv('DATABASE_URL')


class CAODatabase:
    """Database operations for CAO processing"""

    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.pool = None

    async def connect(self):
        """Initialize connection pool"""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        print("✅ Database pool initialized")

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print("✅ Database pool closed")

    async def create_article(
        self,
        cao_name: str,
        article_number: str,
        title: Optional[str],
        full_text: str,
        document_id: Optional[UUID] = None
    ) -> UUID:
        """Insert new CAO article, return article_id"""
        query = """
        INSERT INTO cao_articles (document_id, cao_name, article_number, title, full_text)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            article_id = await conn.fetchval(
                query, document_id, cao_name, article_number, title, full_text
            )
        return article_id

    async def get_article_status(self, article_id: UUID) -> Optional[str]:
        """Get current processing status of article"""
        query = "SELECT processing_status FROM cao_articles WHERE id = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, article_id)

    async def update_processing_status(
        self,
        article_id: UUID,
        status: str,
        error: Optional[str] = None
    ):
        """Update article processing status"""
        query = """
        UPDATE cao_articles
        SET processing_status = $2, processing_error = $3
        WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            await conn.execute(query, article_id, status, error)

    async def insert_chunks(
        self,
        article_id: UUID,
        chunks: List[Dict]
    ) -> List[UUID]:
        """Bulk insert chunks for an article"""
        query = """
        INSERT INTO cao_chunks (
            article_id, chunk_index, chunk_text,
            start_position, end_position, token_count, chunk_reasoning
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """
        chunk_ids = []
        async with self.pool.acquire() as conn:
            for chunk in chunks:
                chunk_id = await conn.fetchval(
                    query,
                    article_id,
                    chunk.get('index', 0),
                    chunk.get('text', ''),
                    chunk.get('start_pos'),
                    chunk.get('end_pos'),
                    chunk.get('token_count'),
                    chunk.get('reasoning', '')
                )
                chunk_ids.append(chunk_id)
        return chunk_ids

    async def get_chunks_by_article(self, article_id: UUID) -> List[Dict]:
        """Get all chunks for an article"""
        query = """
        SELECT id, article_id, chunk_index, chunk_text,
               start_position, end_position, token_count,
               chunk_reasoning, embedding, embedding_input
        FROM cao_chunks
        WHERE article_id = $1
        ORDER BY chunk_index ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, article_id)
            return [dict(row) for row in rows]

    async def insert_analysis(
        self,
        chunk_id: UUID,
        analysis_data: Dict,
        reasoning_trace: Optional[str] = None
    ):
        """Store R1 analysis for a chunk"""
        import json
        query = """
        INSERT INTO cao_chunk_analysis (chunk_id, analysis_data, reasoning_trace)
        VALUES ($1, $2::jsonb, $3)
        ON CONFLICT (chunk_id) DO UPDATE
        SET analysis_data = $2::jsonb, reasoning_trace = $3
        """
        async with self.pool.acquire() as conn:
            # Convert analysis_data to JSON string for asyncpg
            analysis_json = json.dumps(analysis_data)
            await conn.execute(query, chunk_id, analysis_json, reasoning_trace)

    async def get_chunks_with_analysis(self, article_id: UUID) -> List[Dict]:
        """Get chunks with their analysis for an article"""
        query = """
        SELECT
            c.id,
            c.article_id,
            c.chunk_index,
            c.chunk_text,
            c.embedding,
            c.embedding_input,
            a.analysis_data,
            a.reasoning_trace
        FROM cao_chunks c
        LEFT JOIN cao_chunk_analysis a ON c.id = a.chunk_id
        WHERE c.article_id = $1
        ORDER BY c.chunk_index ASC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, article_id)
            return [dict(row) for row in rows]

    async def update_chunk_embedding(
        self,
        chunk_id: UUID,
        embedding: List[float],
        embedding_input: str
    ):
        """Store Voyage AI embedding for chunk"""
        query = """
        UPDATE cao_chunks
        SET embedding = $2::vector, embedding_input = $3
        WHERE id = $1
        """
        async with self.pool.acquire() as conn:
            # Convert embedding to string format that PostgreSQL vector type expects
            embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
            await conn.execute(query, chunk_id, embedding_str, embedding_input)

    async def get_articles_by_status(self, status: str) -> List[Dict]:
        """Get all articles with specific status"""
        query = """
        SELECT id, document_id, cao_name, article_number, title, full_text
        FROM cao_articles
        WHERE processing_status = $1
        ORDER BY created_at DESC
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, status)
            return [dict(row) for row in rows]

    async def get_article_count(self, cao_name: str) -> int:
        """Get number of articles for a CAO"""
        query = "SELECT COUNT(*) FROM cao_articles WHERE cao_name = $1"
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, cao_name)

    async def get_cao_list(self) -> List[Dict]:
        """Get list of all CAOs with article counts"""
        query = """
        SELECT
            cao_name,
            COUNT(*) as article_count,
            COUNT(CASE WHEN processing_status = 'embedded' THEN 1 END) as processed_count,
            MIN(created_at) as first_uploaded,
            MAX(updated_at) as last_updated
        FROM cao_articles
        GROUP BY cao_name
        ORDER BY cao_name
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def insert_article_reference(
        self,
        source_article_id: UUID,
        target_article_number: str,
        reference_type: str,
        context: Optional[str] = None,
        confidence: float = 1.0
    ):
        """Store reference between articles"""
        query = """
        INSERT INTO cao_article_references
        (source_article_id, target_article_number, reference_type, context, confidence)
        VALUES ($1, $2, $3, $4, $5)
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                query, source_article_id, target_article_number,
                reference_type, context, confidence
            )

    async def health_check(self) -> bool:
        """Check if database is accessible"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            print(f"❌ Database health check failed: {e}")
            return False

    async def get_stats(self) -> Dict:
        """Get database statistics"""
        async with self.pool.acquire() as conn:
            stats = {}

            # Article counts
            stats['total_articles'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_articles"
            )
            stats['articles_parsed'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_articles WHERE processing_status = 'parsed'"
            )
            stats['articles_chunked'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_articles WHERE processing_status = 'chunked'"
            )
            stats['articles_analyzed'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_articles WHERE processing_status = 'analyzed'"
            )
            stats['articles_embedded'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_articles WHERE processing_status = 'embedded'"
            )

            # Chunk counts
            stats['total_chunks'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_chunks"
            )
            stats['chunks_with_embeddings'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_chunks WHERE embedding IS NOT NULL"
            )

            # Analysis counts
            stats['chunks_analyzed'] = await conn.fetchval(
                "SELECT COUNT(*) FROM cao_chunk_analysis"
            )

            return stats


# Singleton instance (optional pattern for convenience)
_db_instance = None


def get_cao_database() -> CAODatabase:
    """Get or create database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = CAODatabase()
    return _db_instance


async def main():
    """Test database operations"""
    db = CAODatabase()

    try:
        print("\n" + "="*70)
        print("FASE 1.3: Database Helper Functions Test")
        print("="*70 + "\n")

        # Connect
        await db.connect()

        # Health check
        is_healthy = await db.health_check()
        print(f"Database health check: {'✅ OK' if is_healthy else '❌ FAILED'}\n")

        # Test article creation
        print("Testing article creation...")
        article_id = await db.create_article(
            cao_name="Test CAO Metalektro",
            article_number="5.1",
            title="Vakantiedagen",
            full_text="Werknemers hebben recht op minimaal 25 vakantiedagen per jaar."
        )
        print(f"✅ Article created: {article_id}\n")

        # Test status update
        print("Testing status update...")
        await db.update_processing_status(article_id, 'chunked')
        status = await db.get_article_status(article_id)
        print(f"✅ Status updated to: {status}\n")

        # Test chunk insertion
        print("Testing chunk insertion...")
        chunks = [
            {
                'index': 0,
                'text': 'Werknemers hebben recht op minimaal 25 vakantiedagen per jaar.',
                'start_pos': 0,
                'end_pos': 62,
                'token_count': 12,
                'reasoning': 'Complete sentence about vacation days'
            }
        ]
        chunk_ids = await db.insert_chunks(article_id, chunks)
        print(f"✅ Chunks inserted: {len(chunk_ids)} chunks\n")

        # Test analysis insertion
        print("Testing analysis insertion...")
        analysis = {
            "rights": ["recht op 25 vakantiedagen"],
            "obligations": [],
            "themes": ["vakantie"],
            "summary": "Regelt aantal vakantiedagen",
            "confidence": 0.99
        }
        await db.insert_analysis(chunk_ids[0], analysis, "Test reasoning trace")
        print(f"✅ Analysis inserted\n")

        # Test embedding update
        print("Testing embedding update...")
        dummy_embedding = [0.1] * 1024
        await db.update_chunk_embedding(
            chunk_ids[0],
            dummy_embedding,
            "Test embedding input"
        )
        print(f"✅ Embedding updated\n")

        # Get statistics
        print("Database statistics:")
        stats = await db.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\n" + "="*70)
        print("✅ ALL DATABASE TESTS PASSED")
        print("="*70 + "\n")

        await db.disconnect()

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        exit(1)


if __name__ == '__main__':
    asyncio.run(main())
