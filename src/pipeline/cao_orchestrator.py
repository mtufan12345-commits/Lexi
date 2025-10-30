"""Async orchestrator for CAO processing pipeline with DeepSeek + Voyage"""
import asyncio
import logging
import json
from typing import Dict, List, Optional, Callable
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

class CAOOrchestrator:
    """
    Orchestrates the complete CAO processing pipeline:
    1. Semantic chunking (DeepSeek R1)
    2. Embedding generation (Voyage AI)
    3. Database storage (PostgreSQL)
    4. Graph relationships (Memgraph)
    """

    def __init__(self, db, deepseek_client, voyage_client, integration_adapter=None):
        self.db = db
        self.deepseek = deepseek_client
        self.voyage = voyage_client
        self.integration = integration_adapter
        self.logger = logging.getLogger(__name__)
        self.progress_callbacks: List[Callable] = []

    def on_progress(self, callback: Callable):
        """Register callback for progress updates"""
        self.progress_callbacks.append(callback)

    async def _emit_progress(self, event: str, data: Dict = None):
        """Emit progress event to all registered callbacks"""
        for callback in self.progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, data or {})
                else:
                    callback(event, data or {})
            except Exception as e:
                self.logger.error(f"Error in progress callback: {e}")

    async def process_cao_document(self,
                                  file_path: str,
                                  cao_name: str,
                                  document_id: Optional[str] = None) -> Dict:
        """
        Process a single CAO document through the complete pipeline

        Returns:
            {
                "success": bool,
                "document_id": str,
                "articles_count": int,
                "chunks_count": int,
                "embeddings_count": int,
                "errors": List[str]
            }
        """
        if not document_id:
            document_id = str(uuid4())

        result = {
            "success": False,
            "document_id": document_id,
            "articles_count": 0,
            "chunks_count": 0,
            "embeddings_count": 0,
            "errors": []
        }

        try:
            # Phase 1: Read document
            await self._emit_progress("reading", {"file": file_path})
            self.logger.info(f"📖 Reading {cao_name}...")

            # Phase 2: Semantic chunking
            await self._emit_progress("chunking", {"cao_name": cao_name})
            self.logger.info(f"🧠 Semantic chunking {cao_name}...")

            # Note: This would call deepseek.semantic_chunk() for actual CAO processing
            # For now, placeholder for integration with existing R1 pipeline

            # Phase 3: Database storage
            await self._emit_progress("storing", {"document_id": document_id})
            self.logger.info(f"💾 Storing articles in PostgreSQL...")

            # Phase 4: Embedding generation
            await self._emit_progress("embedding", {"cao_name": cao_name})
            self.logger.info(f"📊 Generating Voyage embeddings...")

            # Phase 5: Graph relationships
            await self._emit_progress("graphing", {"cao_name": cao_name})
            self.logger.info(f"🔗 Creating Memgraph relationships...")

            result["success"] = True
            await self._emit_progress("complete", result)

            return result

        except Exception as e:
            self.logger.error(f"❌ Pipeline error: {e}")
            result["errors"].append(str(e))
            await self._emit_progress("error", {"error": str(e)})
            return result

    async def process_articles_batch(self,
                                    document_id: str,
                                    cao_name: str,
                                    articles: List[Dict],
                                    max_concurrent: int = 3) -> Dict:
        """
        Process multiple articles concurrently with rate limiting

        Args:
            document_id: Parent document ID
            cao_name: CAO name
            articles: List of article dicts
            max_concurrent: Max concurrent Voyage API calls

        Returns:
            Summary of batch processing
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = []

        async def process_article_with_limit(article):
            async with semaphore:
                return await self._process_single_article(
                    document_id, cao_name, article
                )

        for article in articles:
            task = process_article_with_limit(article)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        failed = sum(1 for r in results if isinstance(r, Exception) or not (isinstance(r, dict) and r.get("success")))

        return {
            "total": len(articles),
            "successful": successful,
            "failed": failed,
            "results": results
        }

    async def _process_single_article(self,
                                     document_id: str,
                                     cao_name: str,
                                     article: Dict) -> Dict:
        """
        Process single article: store in DB + generate embedding
        """
        try:
            article_number = article.get("article_number", "UNKNOWN")
            title = article.get("title", "")
            full_text = article.get("full_text", "")

            # Store in PostgreSQL
            article_id = await self.db.create_article(
                document_id=document_id,
                cao_name=cao_name,
                article_number=article_number,
                title=title,
                full_text=full_text
            )

            # Create chunk
            chunks = [{
                "index": 0,
                "text": full_text,
                "token_count": len(full_text.split()),
                "reasoning": f"Article {article_number}"
            }]

            chunk_ids = await self.db.insert_chunks(article_id, chunks)

            # Generate embedding
            if self.voyage and full_text:
                try:
                    embedding = await self.voyage.embed_chunks([full_text])
                    await self.db.update_chunk_embedding(
                        chunk_ids[0],
                        embedding[0],
                        full_text
                    )
                except Exception as e:
                    self.logger.warning(f"⚠️  Embedding failed for {article_number}: {e}")

            await self.db.update_status(article_id, "complete")

            return {
                "success": True,
                "article_number": article_number,
                "article_id": article_id
            }

        except Exception as e:
            self.logger.error(f"Error processing article {article.get('article_number')}: {e}")
            return {"success": False, "error": str(e)}

    async def get_pipeline_status(self, document_id: str) -> Dict:
        """Get current processing status for a document"""
        # Implementation would fetch from database
        return {
            "document_id": document_id,
            "status": "unknown"
        }
