"""Database migrations for CAO processing pipeline"""
import logging
from typing import Optional, Dict
import asyncpg

logger = logging.getLogger(__name__)

class CAOMigrations:
    """Handle schema creation for CAO pipeline"""

    @staticmethod
    async def create_cao_schema(db_pool: asyncpg.Pool) -> bool:
        """
        Create PostgreSQL tables for CAO document processing

        Tables:
        - cao_documents: Document metadata
        - cao_articles: Extracted articles
        - cao_chunks: Semantic chunks with embeddings
        """
        try:
            async with db_pool.acquire() as conn:
                # cao_documents table
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS cao_documents (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    filename VARCHAR(255) NOT NULL,
                    cao_name VARCHAR(255) NOT NULL,
                    document_type VARCHAR(50),
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processing_status VARCHAR(50) DEFAULT 'pending',
                    total_articles INT DEFAULT 0,
                    total_chunks INT DEFAULT 0,
                    processing_error TEXT
                )
                """)
                logger.info("✓ Created cao_documents table")

                # cao_articles table
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS cao_articles (
                    id BIGSERIAL PRIMARY KEY,
                    document_id UUID NOT NULL REFERENCES cao_documents(id) ON DELETE CASCADE,
                    cao_name VARCHAR(255) NOT NULL,
                    article_number VARCHAR(50) NOT NULL,
                    title VARCHAR(500),
                    full_text TEXT NOT NULL,
                    processing_status VARCHAR(50) DEFAULT 'pending',
                    processing_error TEXT,
                    r1_metadata JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(document_id, article_number)
                )
                """)
                logger.info("✓ Created cao_articles table")

                # cao_chunks table
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS cao_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    article_id BIGINT NOT NULL REFERENCES cao_articles(id) ON DELETE CASCADE,
                    chunk_index INT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    token_count INT,
                    chunk_reasoning TEXT,
                    embedding VECTOR(1024),
                    embedding_input TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                logger.info("✓ Created cao_chunks table")

                # Create indexes for performance
                await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cao_articles_document_id
                ON cao_articles(document_id)
                """)

                await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cao_articles_cao_name
                ON cao_articles(cao_name)
                """)

                await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cao_chunks_article_id
                ON cao_chunks(article_id)
                """)

                # Vector search index (requires pgvector extension)
                try:
                    await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cao_chunks_embedding_hnsw
                    ON cao_chunks USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 200)
                    """)
                    logger.info("✓ Created vector search index")
                except Exception as e:
                    logger.warning(f"⚠️  Vector index creation failed (pgvector may not be installed): {e}")

                logger.info("✅ CAO schema created successfully")
                return True

        except Exception as e:
            logger.error(f"❌ Error creating CAO schema: {e}")
            return False

    @staticmethod
    async def check_extensions(db_pool: asyncpg.Pool) -> Dict[str, bool]:
        """Check if required extensions are installed"""
        try:
            async with db_pool.acquire() as conn:
                extensions = {}

                # Check pgvector
                try:
                    result = await conn.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
                    )
                    extensions['pgvector'] = result
                except:
                    extensions['pgvector'] = False

                # Check uuid-ossp
                try:
                    result = await conn.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp')"
                    )
                    extensions['uuid-ossp'] = result
                except:
                    extensions['uuid-ossp'] = False

                return extensions

        except Exception as e:
            logger.error(f"Error checking extensions: {e}")
            return {}

    @staticmethod
    async def install_extensions(db_pool: asyncpg.Pool) -> bool:
        """Install required PostgreSQL extensions"""
        try:
            async with db_pool.acquire() as conn:
                # Install pgvector
                try:
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    logger.info("✓ Installed pgvector extension")
                except Exception as e:
                    logger.warning(f"⚠️  pgvector installation failed: {e}")

                # Install uuid-ossp
                try:
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
                    logger.info("✓ Installed uuid-ossp extension")
                except Exception as e:
                    logger.warning(f"⚠️  uuid-ossp installation failed: {e}")

                return True

        except Exception as e:
            logger.error(f"Error installing extensions: {e}")
            return False
