"""Main CAO processing pipeline"""
import logging
from typing import Dict
from uuid import UUID

logger = logging.getLogger(__name__)

class CAOProcessor:
    def __init__(self, db, deepseek, voyage):
        self.db = db
        self.deepseek = deepseek
        self.voyage = voyage

    async def process_article(self, article_id, cao_name, article_number, article_text):
        """Complete pipeline: chunk → analyze → embed"""
        try:
            # Step 1: Semantic chunking
            chunks = await self.deepseek.semantic_chunk(article_text, article_number, cao_name)
            chunk_ids = await self.db.insert_chunks(article_id, chunks)
            await self.db.update_status(article_id, 'chunked')

            logger.info(f"✅ Article {article_number}: {len(chunks)} chunks created")

            # Step 2: Generate embeddings
            for chunk_id, chunk in zip(chunk_ids, chunks):
                # Create enriched input (we'll add R1 analysis later)
                embedding_input = chunk['text']

                # Generate embedding
                embedding = await self.voyage.embed_chunks([embedding_input])
                await self.db.update_chunk_embedding(chunk_id, embedding[0], embedding_input)

            await self.db.update_status(article_id, 'embedded')
            logger.info(f"✅ Article {article_number}: embeddings created")

            return {'success': True, 'chunks': len(chunks)}

        except Exception as e:
            logger.error(f"❌ Processing failed for {article_number}: {e}")
            await self.db.update_status(article_id, 'error', str(e))
            return {'success': False, 'error': str(e)}
