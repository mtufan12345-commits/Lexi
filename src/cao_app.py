"""CAO processing pipeline initialization for Flask app"""
import asyncio
import asyncpg
import logging
from typing import Optional
import os

from .ai.deepseek_client import DeepSeekClient
from .ai.voyage_client import VoyageClient
from .database.cao_queries import CAODatabase
from .database.migrations import CAOMigrations
from .pipeline.cao_processor import CAOProcessor
from .pipeline.cao_orchestrator import CAOOrchestrator
from .pipeline.cao_integration import CAOIntegrationAdapter
from .api.cao_routes import cao_bp

logger = logging.getLogger(__name__)

class CAOPipeline:
    """Initialize and manage CAO processing pipeline"""

    def __init__(self):
        self.db_pool: Optional[asyncpg.Pool] = None
        self.cao_db: Optional[CAODatabase] = None
        self.deepseek_client: Optional[DeepSeekClient] = None
        self.voyage_client: Optional[VoyageClient] = None
        self.orchestrator: Optional[CAOOrchestrator] = None
        self.integration: Optional[CAOIntegrationAdapter] = None

    async def initialize(self) -> bool:
        """Initialize all components of the CAO pipeline"""
        try:
            # Initialize database pool
            logger.info("🗄️  Initializing PostgreSQL connection pool...")
            self.db_pool = await asyncpg.create_pool(
                host=os.getenv('DATABASE_HOST', 'localhost'),
                port=int(os.getenv('DATABASE_PORT', 5432)),
                user=os.getenv('DATABASE_USER', 'postgres'),
                password=os.getenv('DATABASE_PASSWORD', 'postgres'),
                database=os.getenv('DATABASE_NAME', 'lexi'),
                min_size=5,
                max_size=20
            )
            logger.info("✓ Database pool initialized")

            # Create schema
            logger.info("📐 Creating CAO schema...")
            success = await CAOMigrations.create_cao_schema(self.db_pool)
            if not success:
                logger.warning("⚠️  Schema creation encountered issues")

            # Install extensions
            logger.info("🔌 Installing PostgreSQL extensions...")
            await CAOMigrations.install_extensions(self.db_pool)

            # Initialize database queries
            self.cao_db = CAODatabase(self.db_pool)
            logger.info("✓ CAO database initialized")

            # Initialize AI clients
            logger.info("🤖 Initializing AI clients...")

            if os.getenv('DEEPSEEK_API_KEY'):
                self.deepseek_client = DeepSeekClient()
                logger.info("✓ DeepSeek client initialized")
            else:
                logger.warning("⚠️  DEEPSEEK_API_KEY not set - semantic chunking unavailable")

            if os.getenv('VOYAGE_API_KEY'):
                self.voyage_client = VoyageClient()
                logger.info("✓ Voyage AI client initialized")
            else:
                logger.warning("⚠️  VOYAGE_API_KEY not set - embeddings unavailable")

            # Initialize orchestrator
            self.orchestrator = CAOOrchestrator(
                db=self.cao_db,
                deepseek_client=self.deepseek_client,
                voyage_client=self.voyage_client
            )
            logger.info("✓ CAO orchestrator initialized")

            # Initialize integration adapter
            self.integration = CAOIntegrationAdapter(
                db=self.cao_db,
                voyage_client=self.voyage_client
            )
            logger.info("✓ Integration adapter initialized")

            logger.info("✅ CAO pipeline fully initialized")
            return True

        except Exception as e:
            logger.error(f"❌ Error initializing CAO pipeline: {e}")
            return False

    async def shutdown(self):
        """Shutdown all components"""
        try:
            if self.db_pool:
                await self.db_pool.close()
                logger.info("✓ Database pool closed")

            if self.deepseek_client:
                await self.deepseek_client.close()
                logger.info("✓ DeepSeek client closed")

            logger.info("✅ CAO pipeline shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

def init_cao_pipeline(app):
    """
    Initialize CAO pipeline for Flask app

    Usage in main.py:
    ```
    from src.cao_app import init_cao_pipeline
    init_cao_pipeline(app)
    ```
    """
    pipeline = CAOPipeline()

    @app.before_request
    def before_request():
        # Initialize pipeline on first request
        if not hasattr(app, 'cao_pipeline_initialized'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(pipeline.initialize())
                app.cao_pipeline_initialized = True
            finally:
                loop.close()

            # Attach components to app
            app.cao_pipeline = pipeline
            app.cao_db = pipeline.cao_db
            app.deepseek_client = pipeline.deepseek_client
            app.voyage_client = pipeline.voyage_client
            app.cao_orchestrator = pipeline.orchestrator

    @app.teardown_appcontext
    def teardown(error):
        if hasattr(app, 'cao_pipeline'):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(app.cao_pipeline.shutdown())
            finally:
                loop.close()

    # Register blueprint
    app.register_blueprint(cao_bp)
    logger.info("✓ CAO API routes registered at /api/cao/*")

    return app
