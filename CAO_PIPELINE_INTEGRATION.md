# CAO Processing Pipeline Integration Guide

## Overview

The CAO processing pipeline provides semantic chunking, embeddings, and vector search for CAO (Collective Labor Agreement) documents.

**Architecture:**
```
Upload (Flask)
    ↓
Memgraph DeepSeek R1 (semantic chunking & analysis)
    ↓
PostgreSQL (articles + chunks)
    ↓
Voyage AI (embeddings)
    ↓
Vector Search (semantic retrieval)
```

## Components

### 1. AI Clients (`src/ai/`)
- **DeepSeekClient**: Semantic chunking using DeepSeek R1 API
- **VoyageClient**: Legal embeddings using Voyage AI (voyage-law-2)
- **fallback_chunker**: Sentence-based chunking fallback

### 2. Database (`src/database/`)
- **CAODatabase**: PostgreSQL queries for articles and chunks
- **CAOMigrations**: Schema creation and extension management

Tables:
- `cao_articles`: Article metadata and full text
- `cao_chunks`: Semantic chunks with embeddings (pgvector)
- `cao_documents`: Document metadata

### 3. Pipeline (`src/pipeline/`)
- **CAOProcessor**: Single document processing pipeline
- **CAOOrchestrator**: Async orchestration with batch processing
- **CAOIntegrationAdapter**: Bridge between Memgraph and PostgreSQL

### 4. API (`src/api/`)
- **cao_routes**: Flask blueprint with endpoints
  - `POST /api/cao/process` - Process CAO document
  - `GET /api/cao/status/<doc_id>` - Get processing status
  - `POST /api/cao/search` - Semantic search

### 5. App Integration (`src/cao_app.py`)
- Initialization module for Flask integration

## Installation

### 1. Install Dependencies

```bash
pip install deepseek httpx voyageai asyncpg pgvector
```

### 2. Environment Variables

Add to `.env`:
```bash
# DeepSeek R1
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# Voyage AI
VOYAGE_API_KEY=your_voyage_api_key

# PostgreSQL
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=postgres
DATABASE_NAME=lexi
```

### 3. PostgreSQL Extensions

Ensure pgvector is installed:
```sql
CREATE EXTENSION vector;
```

## Flask Integration

### In `main.py`:

```python
from src.cao_app import init_cao_pipeline

# After creating Flask app
app = Flask(__name__)

# Initialize CAO pipeline (after other setup)
init_cao_pipeline(app)

# Now you can use:
# app.cao_db - database queries
# app.cao_orchestrator - processing orchestrator
# app.deepseek_client - DeepSeek R1
# app.voyage_client - Voyage AI
```

## Usage Examples

### Process a CAO Document

```python
import asyncio
from src.pipeline.cao_orchestrator import CAOOrchestrator

# Async processing
async def process_cao():
    orchestrator = app.cao_orchestrator
    result = await orchestrator.process_cao_document(
        file_path="/path/to/cao.pdf",
        cao_name="CAO 2024",
        document_id="unique-id"
    )
    print(result)

asyncio.run(process_cao())
```

### API Endpoint

```bash
# Process document
curl -X POST http://localhost:5000/api/cao/process \
  -H "Content-Type: application/json" \
  -d '{
    "cao_name": "CAO 2024",
    "file_path": "/tmp/cao_2024.pdf"
  }'

# Get status
curl http://localhost:5000/api/cao/status/doc-uuid

# Search
curl -X POST http://localhost:5000/api/cao/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "vacation rights",
    "limit": 10
  }'
```

## Processing Pipeline

### Step 1: Semantic Chunking (DeepSeek R1)
- Reads document (PDF/TXT/DOCX)
- Uses DeepSeek R1 to identify articles and sections
- Fallback to regex patterns if R1 fails

### Step 2: Database Storage (PostgreSQL)
- Creates cao_articles records
- Creates cao_chunks records
- Tracks processing status

### Step 3: Embedding Generation (Voyage AI)
- Generates voyage-law-2 embeddings
- Stores in pgvector column
- Updates chunk records

### Step 4: Graph Relationships (Memgraph)
- Already handled by existing Memgraph pipeline
- Integration adapter bridges data between systems

## Progress Callbacks

Register callbacks to monitor processing:

```python
async def progress_handler(event, data):
    print(f"Event: {event}, Data: {data}")

orchestrator.on_progress(progress_handler)
```

Events emitted:
- `reading`: Reading document
- `chunking`: Semantic chunking started
- `storing`: Storing in database
- `embedding`: Generating embeddings
- `graphing`: Creating graph relationships
- `complete`: Processing finished
- `error`: Error occurred

## Error Handling

Pipeline handles:
- Missing API keys → fallback to sentence chunking
- Voyage API failures → store chunk without embedding
- Memgraph unavailable → PostgreSQL-only mode
- Large documents → batch processing with rate limiting

## Performance

- **Concurrent processing**: 3 Voyage API calls parallel by default
- **Memory**: Streaming for large PDFs
- **Database**: Indexed on document_id, cao_name, article_id
- **Vector search**: HNSW index for fast similarity queries

## Monitoring

Check processing logs:
```bash
# Application logs
tail -f /var/log/lexi/cao_pipeline.log

# Database logs (if needed)
tail -f /var/log/postgresql/postgresql.log
```

## Integration with Existing Upload

The CAO pipeline works alongside the existing Memgraph DeepSeek R1 pipeline:

1. **Super Admin Upload** → Memgraph pipeline (existing)
2. **CAO API** (`/api/cao/*`) → PostgreSQL pipeline (new)
3. Both maintain separate data but can be synchronized via integration adapter

To sync Memgraph articles to PostgreSQL:

```python
# Extract articles from Memgraph
articles = await integration.extract_articles_from_memgraph("CAO 2024")

# Import to PostgreSQL
result = await integration.import_articles_to_postgres(
    document_id="uuid",
    cao_name="CAO 2024",
    articles=articles
)
```

## Database Schema

```sql
-- CAO Documents
CREATE TABLE cao_documents (
    id UUID PRIMARY KEY,
    filename VARCHAR(255),
    cao_name VARCHAR(255),
    document_type VARCHAR(50),
    upload_date TIMESTAMP,
    processing_status VARCHAR(50),
    total_articles INT,
    total_chunks INT
);

-- Articles
CREATE TABLE cao_articles (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID REFERENCES cao_documents(id),
    cao_name VARCHAR(255),
    article_number VARCHAR(50),
    title VARCHAR(500),
    full_text TEXT,
    processing_status VARCHAR(50),
    r1_metadata JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Chunks with Embeddings
CREATE TABLE cao_chunks (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT REFERENCES cao_articles(id),
    chunk_index INT,
    chunk_text TEXT,
    token_count INT,
    chunk_reasoning TEXT,
    embedding VECTOR(1024),
    embedding_input TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Indexes
CREATE INDEX idx_cao_articles_document_id ON cao_articles(document_id);
CREATE INDEX idx_cao_articles_cao_name ON cao_articles(cao_name);
CREATE INDEX idx_cao_chunks_article_id ON cao_chunks(article_id);
CREATE INDEX idx_cao_chunks_embedding_hnsw ON cao_chunks
  USING hnsw (embedding vector_cosine_ops);
```

## Troubleshooting

**Q: "VOYAGE_API_KEY not set"**
A: Add `VOYAGE_API_KEY` to environment variables

**Q: Vector index creation fails**
A: Install pgvector: `CREATE EXTENSION vector;`

**Q: DeepSeek chunking fails**
A: Check API key and rate limits, pipeline falls back to regex

**Q: Slow embedding generation**
A: Adjust `max_concurrent` parameter in batch processing

## Future Enhancements

- [ ] Real-time processing webhooks
- [ ] Batch import from Memgraph
- [ ] Advanced vector search filters
- [ ] Caching for frequently accessed chunks
- [ ] Multi-language support
- [ ] Custom chunking strategies
