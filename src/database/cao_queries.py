"""PostgreSQL queries for CAO processing pipeline"""
import asyncpg
from typing import List, Dict, Optional
from uuid import UUID

class CAODatabase:
    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool

    async def create_article(self, document_id, cao_name, article_number, title, full_text):
        """Insert new CAO article"""
        query = """
        INSERT INTO cao_articles (document_id, cao_name, article_number, title, full_text)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, document_id, cao_name, article_number, title, full_text)

    async def update_status(self, article_id, status, error=None):
        """Update article processing status"""
        query = "UPDATE cao_articles SET processing_status = $2, processing_error = $3 WHERE id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, article_id, status, error)

    async def insert_chunks(self, article_id, chunks):
        """Bulk insert chunks for an article"""
        query = """
        INSERT INTO cao_chunks (article_id, chunk_index, chunk_text, token_count, chunk_reasoning)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """
        chunk_ids = []
        async with self.pool.acquire() as conn:
            for chunk in chunks:
                chunk_id = await conn.fetchval(
                    query, article_id, chunk['index'], chunk['text'],
                    chunk.get('token_count'), chunk.get('reasoning')
                )
                chunk_ids.append(chunk_id)
        return chunk_ids

    async def update_chunk_embedding(self, chunk_id, embedding, embedding_input):
        """Store Voyage AI embedding for chunk"""
        query = "UPDATE cao_chunks SET embedding = $2, embedding_input = $3 WHERE id = $1"
        async with self.pool.acquire() as conn:
            await conn.execute(query, chunk_id, embedding, embedding_input)
