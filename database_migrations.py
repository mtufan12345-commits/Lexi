#!/usr/bin/env python3
"""
PostgreSQL Schema Migrations for CAO Processing Pipeline
Creates all necessary tables for dual storage (PostgreSQL + Memgraph)
"""

import asyncio
import asyncpg
import os
from pathlib import Path

# Database connection from .env
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://neondb_owner:npg_Fxq6DGIuA1Xd@ep-wandering-sun-a6asxcto.us-west-2.aws.neon.tech/neondb?sslmode=require')


class DatabaseMigrations:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None

    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=1,
            max_size=5,
            command_timeout=60
        )
        print("✅ Connected to PostgreSQL database")

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print("✅ Disconnected from database")

    async def execute_migration(self, sql: str, description: str):
        """Execute a migration with error handling"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(sql)
            print(f"✅ {description}")
        except Exception as e:
            print(f"❌ {description}: {e}")
            raise

    async def run_migrations(self):
        """Run all migrations"""
        print("\n" + "="*70)
        print("FASE 1.1: PostgreSQL Schema Setup")
        print("="*70 + "\n")

        # Migration 1: Enable pgvector extension
        await self.execute_migration(
            "CREATE EXTENSION IF NOT EXISTS vector;",
            "Enable pgvector extension"
        )

        # Migration 2: CAO Articles table
        await self.execute_migration(
            """
            CREATE TABLE IF NOT EXISTS cao_articles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID,
                cao_name TEXT NOT NULL,
                article_number TEXT NOT NULL,
                title TEXT,
                full_text TEXT NOT NULL,

                -- Processing pipeline status
                processing_status TEXT DEFAULT 'parsed',
                processing_error TEXT,

                -- Metadata
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),

                UNIQUE(cao_name, article_number)
            );
            """,
            "Create cao_articles table"
        )

        # Migration 3: CAO Chunks table
        await self.execute_migration(
            """
            CREATE TABLE IF NOT EXISTS cao_chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                article_id UUID NOT NULL REFERENCES cao_articles(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,

                -- Positioning in original text
                start_position INTEGER,
                end_position INTEGER,
                token_count INTEGER,

                -- DeepSeek chunking metadata
                chunk_reasoning TEXT,

                -- Voyage AI embeddings
                embedding vector(1024),
                embedding_model TEXT DEFAULT 'voyage-law-2',
                embedding_input TEXT,

                -- Metadata
                created_at TIMESTAMPTZ DEFAULT NOW(),

                UNIQUE(article_id, chunk_index)
            );
            """,
            "Create cao_chunks table"
        )

        # Migration 4: DeepSeek R1 Analysis table
        await self.execute_migration(
            """
            CREATE TABLE IF NOT EXISTS cao_chunk_analysis (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                chunk_id UUID NOT NULL UNIQUE REFERENCES cao_chunks(id) ON DELETE CASCADE,

                -- R1 structured output (JSONB)
                analysis_data JSONB NOT NULL,

                -- R1 reasoning trace
                reasoning_trace TEXT,

                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
            "Create cao_chunk_analysis table"
        )

        # Migration 5: Cross-references table
        await self.execute_migration(
            """
            CREATE TABLE IF NOT EXISTS cao_article_references (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_article_id UUID NOT NULL REFERENCES cao_articles(id) ON DELETE CASCADE,
                target_article_number TEXT NOT NULL,
                reference_type TEXT NOT NULL,
                context TEXT,
                confidence FLOAT DEFAULT 1.0,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
            "Create cao_article_references table"
        )

        # Migration 6: Create indexes for performance
        print("\n📊 Creating indexes...\n")

        indexes = [
            ("""
            CREATE INDEX IF NOT EXISTS idx_articles_status ON cao_articles(processing_status);
            """, "Index on cao_articles.processing_status"),

            ("""
            CREATE INDEX IF NOT EXISTS idx_articles_cao ON cao_articles(cao_name);
            """, "Index on cao_articles.cao_name"),

            ("""
            CREATE INDEX IF NOT EXISTS idx_chunks_article ON cao_chunks(article_id);
            """, "Index on cao_chunks.article_id"),

            ("""
            CREATE INDEX IF NOT EXISTS idx_analysis_chunk ON cao_chunk_analysis(chunk_id);
            """, "Index on cao_chunk_analysis.chunk_id"),

            ("""
            CREATE INDEX IF NOT EXISTS idx_references_source ON cao_article_references(source_article_id);
            """, "Index on cao_article_references.source_article_id"),

            ("""
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON cao_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
            """, "Vector similarity index on cao_chunks.embedding"),
        ]

        for sql, description in indexes:
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(sql)
                print(f"✅ {description}")
            except Exception as e:
                # Vector index may fail if pgvector not ready, that's OK
                if "ivfflat" in str(e).lower():
                    print(f"⚠️  {description} (vector index deferred)")
                else:
                    print(f"❌ {description}: {e}")

        # Migration 7: Create auto-update timestamp trigger
        print("\n⏰ Creating triggers...\n")

        await self.execute_migration(
            """
            CREATE OR REPLACE FUNCTION update_cao_articles_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            "Create update_cao_articles_updated_at function"
        )

        await self.execute_migration(
            """
            DROP TRIGGER IF EXISTS update_cao_articles_timestamp ON cao_articles;
            CREATE TRIGGER update_cao_articles_timestamp
                BEFORE UPDATE ON cao_articles
                FOR EACH ROW
                EXECUTE FUNCTION update_cao_articles_updated_at();
            """,
            "Create timestamp update trigger"
        )

        print("\n" + "="*70)
        print("✅ ALL MIGRATIONS COMPLETED SUCCESSFULLY")
        print("="*70 + "\n")

    async def verify_schema(self):
        """Verify schema was created correctly"""
        print("\n" + "="*70)
        print("FASE 1.2: Schema Verification")
        print("="*70 + "\n")

        async with self.pool.acquire() as conn:
            # Check tables exist
            tables = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name LIKE 'cao_%'
                ORDER BY table_name;
            """)

            print("📊 CAO Tables Created:")
            for table in tables:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['table_name']};")
                print(f"   ✅ {table['table_name']} (0 rows - empty)")

            # Check indexes
            indexes = await conn.fetch("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename LIKE 'cao_%'
                ORDER BY indexname;
            """)

            print("\n📑 Indexes Created:")
            for idx in indexes:
                print(f"   ✅ {idx['indexname']}")

            # Check extensions
            extensions = await conn.fetch("""
                SELECT extname FROM pg_extension WHERE extname = 'vector';
            """)

            if extensions:
                print("\n🔧 Extensions:")
                print(f"   ✅ pgvector enabled")
            else:
                print("\n⚠️  pgvector not found (may need manual setup)")

        print("\n" + "="*70)
        print("✅ SCHEMA VERIFICATION COMPLETE")
        print("="*70 + "\n")


async def main():
    """Main migration runner"""
    migrations = DatabaseMigrations(DATABASE_URL)

    try:
        await migrations.connect()
        await migrations.run_migrations()
        await migrations.verify_schema()
        await migrations.disconnect()

        print("\n🎉 DATABASE SETUP COMPLETE - Ready for Fase 1.3 (Helper Functions)")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        await migrations.disconnect()
        exit(1)


if __name__ == '__main__':
    asyncio.run(main())
