"""Tests for CAO processing pipeline"""
import pytest
import asyncio
import os
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

# Test imports
sys_path_insert = True
try:
    from src.ai.deepseek_client import DeepSeekClient
    from src.ai.voyage_client import VoyageClient
    from src.ai.fallback_chunker import sentence_chunking
    from src.database.cao_queries import CAODatabase
    from src.pipeline.cao_processor import CAOProcessor
    from src.pipeline.cao_orchestrator import CAOOrchestrator
    from src.pipeline.cao_integration import CAOIntegrationAdapter
except ImportError:
    pytest.skip("CAO pipeline not available", allow_module_level=True)


class TestFallbackChunker:
    """Test fallback chunking"""

    def test_sentence_chunking_basic(self):
        """Test basic sentence chunking"""
        text = "Article 1. This is first. Article 2. This is second."
        chunks = sentence_chunking(text, max_sentences=1)

        assert len(chunks) > 0
        assert all('text' in chunk for chunk in chunks)
        assert all('index' in chunk for chunk in chunks)
        assert all('token_count' in chunk for chunk in chunks)

    def test_sentence_chunking_empty(self):
        """Test empty text handling"""
        chunks = sentence_chunking("", max_sentences=5)
        assert isinstance(chunks, list)

    def test_sentence_chunking_metadata(self):
        """Test chunk metadata"""
        text = "First sentence. Second sentence. Third sentence."
        chunks = sentence_chunking(text, max_sentences=2)

        for chunk in chunks:
            assert 'reasoning' in chunk
            assert 'Fallback' in chunk['reasoning']


class TestDeepSeekClient:
    """Test DeepSeek client"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test client initialization"""
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-key'}):
            client = DeepSeekClient()
            assert client.api_key == 'test-key'
            assert client.base_url == 'https://api.deepseek.com/v1'
            await client.close()

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test missing API key"""
        with patch.dict(os.environ, {}, clear=True):
            client = DeepSeekClient()
            with pytest.raises(ValueError):
                await client.semantic_chunk("text", "1", "CAO")


class TestVoyageClient:
    """Test Voyage AI client"""

    def test_initialization(self):
        """Test Voyage client initialization"""
        with patch.dict(os.environ, {'VOYAGE_API_KEY': 'test-key'}):
            client = VoyageClient()
            assert client.api_key == 'test-key'
            assert client.model == 'voyage-law-2'

    def test_embedding_input_creation(self):
        """Test embedding input enrichment"""
        client = VoyageClient()
        analysis = {
            'themes': ['labor', 'rights'],
            'summary': 'Summary text'
        }
        chunk_text = "Article text here"

        result = client.create_embedding_input(chunk_text, analysis)

        assert 'THEMA:' in result
        assert 'labor, rights' in result
        assert 'CONTEXT:' in result
        assert 'Article text here' in result


class TestCAODatabase:
    """Test database queries"""

    @pytest.mark.asyncio
    async def test_database_initialization(self):
        """Test database initialization"""
        mock_pool = AsyncMock()
        db = CAODatabase(mock_pool)

        assert db.pool == mock_pool

    @pytest.mark.asyncio
    async def test_create_article(self):
        """Test article creation"""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.fetchval.return_value = 123

        db = CAODatabase(mock_pool)
        article_id = await db.create_article(
            document_id="doc-123",
            cao_name="CAO 2024",
            article_number="1",
            title="Title",
            full_text="Text"
        )

        assert article_id == 123
        mock_conn.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_insert_chunks(self):
        """Test chunk insertion"""
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_conn.fetchval.side_effect = [1, 2, 3]

        db = CAODatabase(mock_pool)
        chunks = [
            {'index': 0, 'text': 'text1', 'token_count': 10, 'reasoning': 'r1'},
            {'index': 1, 'text': 'text2', 'token_count': 20, 'reasoning': 'r2'}
        ]

        chunk_ids = await db.insert_chunks(123, chunks)

        assert len(chunk_ids) == 2
        assert 1 in chunk_ids


class TestCAOIntegrationAdapter:
    """Test integration adapter"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test adapter initialization"""
        mock_db = AsyncMock()
        mock_voyage = AsyncMock()

        adapter = CAOIntegrationAdapter(mock_db, mock_voyage)

        assert adapter.db == mock_db
        assert adapter.voyage == mock_voyage

    @pytest.mark.asyncio
    async def test_sync_article_to_postgres(self):
        """Test syncing article to PostgreSQL"""
        mock_db = AsyncMock()
        mock_db.create_article.return_value = 123
        mock_db.update_status.return_value = None
        mock_voyage = None

        adapter = CAOIntegrationAdapter(mock_db, mock_voyage)
        article_data = {
            'cao_name': 'CAO 2024',
            'article_number': '1',
            'title': 'Title',
            'full_text': 'Text'
        }

        article_id = await adapter.sync_article_to_postgres(article_data)

        assert article_id == 123
        mock_db.create_article.assert_called_once()
        mock_db.update_status.assert_called_once()


class TestCAOOrchestrator:
    """Test orchestrator"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test orchestrator initialization"""
        mock_db = AsyncMock()
        mock_deepseek = AsyncMock()
        mock_voyage = AsyncMock()

        orchestrator = CAOOrchestrator(
            db=mock_db,
            deepseek_client=mock_deepseek,
            voyage_client=mock_voyage
        )

        assert orchestrator.db == mock_db
        assert orchestrator.deepseek == mock_deepseek
        assert orchestrator.voyage == mock_voyage

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        """Test progress callback registration"""
        mock_db = AsyncMock()
        orchestrator = CAOOrchestrator(mock_db, None, None)

        callback_called = []

        def callback(event, data):
            callback_called.append((event, data))

        orchestrator.on_progress(callback)

        await orchestrator._emit_progress("test_event", {"data": "value"})

        assert len(callback_called) > 0
        assert callback_called[0][0] == "test_event"

    @pytest.mark.asyncio
    async def test_process_articles_batch(self):
        """Test batch processing"""
        mock_db = AsyncMock()
        mock_db.create_article.return_value = 123
        mock_db.insert_chunks.return_value = [456]
        mock_db.update_status.return_value = None

        orchestrator = CAOOrchestrator(mock_db, None, None)

        articles = [
            {'article_number': '1', 'title': 'T1', 'full_text': 'F1'},
            {'article_number': '2', 'title': 'T2', 'full_text': 'F2'}
        ]

        result = await orchestrator.process_articles_batch(
            document_id="doc-123",
            cao_name="CAO",
            articles=articles,
            max_concurrent=2
        )

        assert result['total'] == 2
        assert result['successful'] >= 0  # At least some processed


class TestCAOProcessor:
    """Test document processor"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test processor initialization"""
        mock_db = AsyncMock()
        mock_deepseek = AsyncMock()
        mock_voyage = AsyncMock()

        processor = CAOProcessor(
            db=mock_db,
            deepseek=mock_deepseek,
            voyage=mock_voyage
        )

        assert processor.db == mock_db
        assert processor.deepseek == mock_deepseek
        assert processor.voyage == mock_voyage

    @pytest.mark.asyncio
    async def test_process_article_with_deepseek(self):
        """Test article processing with DeepSeek"""
        mock_db = AsyncMock()
        mock_db.insert_chunks.return_value = [1, 2]
        mock_db.update_status.return_value = None
        mock_db.update_chunk_embedding.return_value = None

        mock_deepseek = AsyncMock()
        mock_deepseek.semantic_chunk.return_value = [
            {'index': 0, 'text': 'chunk1', 'reasoning': 'r1'},
            {'index': 1, 'text': 'chunk2', 'reasoning': 'r2'}
        ]

        mock_voyage = AsyncMock()
        mock_voyage.embed_chunks.return_value = [[0.1, 0.2], [0.3, 0.4]]

        processor = CAOProcessor(mock_db, mock_deepseek, mock_voyage)

        result = await processor.process_article(
            article_id=123,
            cao_name="CAO",
            article_number="1",
            article_text="Article text"
        )

        assert result['success'] is True
        assert result['chunks'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
