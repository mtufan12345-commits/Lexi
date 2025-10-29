#!/usr/bin/env python3
"""
Document Importer voor Lexi AI
Parset PDF/TXT bestanden en indexeert ze in Memgraph met embeddings
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Tuple
import re
import time
import gc

# Global model cache to avoid reloading for each document
_embedding_model = None
_model_load_time = 0

def parse_pdf(file_path: str) -> List[str]:
    """Parse PDF file into text chunks"""
    try:
        from PyPDF2 import PdfReader

        chunks = []
        reader = PdfReader(file_path)

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            # Split by paragraphs
            paragraphs = text.split('\n\n')
            for para in paragraphs:
                if para.strip() and len(para.strip()) > 50:  # Only keep substantial chunks
                    chunks.append(para.strip())

        return chunks
    except Exception as e:
        print(f"   ❌ Error reading PDF: {e}")
        return []

def parse_txt(file_path: str) -> List[str]:
    """Parse TXT file into text chunks"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split by paragraphs (double newlines)
        chunks = content.split('\n\n')
        return [chunk.strip() for chunk in chunks if chunk.strip() and len(chunk.strip()) > 50]
    except Exception as e:
        print(f"   ❌ Error reading TXT: {e}")
        return []

def parse_document(file_path: str) -> Tuple[str, List[str]]:
    """Parse document file and return (cao_name, chunks)"""
    file_path = Path(file_path)
    cao_name = file_path.stem.replace('_', ' ').title()

    if file_path.suffix.lower() == '.pdf':
        chunks = parse_pdf(file_path)
    elif file_path.suffix.lower() == '.txt':
        chunks = parse_txt(file_path)
    else:
        print(f"   ⚠️  Unsupported format: {file_path.suffix}")
        return cao_name, []

    return cao_name, chunks

def extract_article_number(text: str) -> str:
    """Extract article number from text"""
    # Common patterns: "Artikel 1", "Art. 1", "Article 1", "§1", etc.
    patterns = [
        r'(?:artikel|art\.?)\s+(\d+(?:[a-z])?)',
        r'(?:§|par\.?)\s*(\d+(?:[a-z])?)',
        r'(?:article)\s+(\d+(?:[a-z])?)'
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return match.group(1)

    return "UNKNOWN"

def get_embedding_model():
    """Get or load the embedding model (cached globally)"""
    global _embedding_model, _model_load_time

    if _embedding_model is not None:
        print(f"   ✅ Using cached model (loaded {_model_load_time:.1f}s ago)")
        return _embedding_model

    try:
        from sentence_transformers import SentenceTransformer
        print("   ⏳ Loading embedding model for first time...")
        start = time.time()
        model = SentenceTransformer('intfloat/multilingual-e5-large')
        load_time = time.time() - start
        _model_load_time = load_time
        _embedding_model = model
        print(f"   ✅ Model loaded in {load_time:.1f}s and cached")
        return model
    except ImportError:
        print("   ⚠️  sentence_transformers not available")
        return None
    except Exception as e:
        print(f"   ⚠️  Error loading model: {str(e)[:100]}")
        return None


def generate_embeddings(chunks: List[str]) -> List[Dict]:
    """Generate embeddings for text chunks (batch processing with model caching)"""
    result = []
    batch_size = 32  # Larger batches now (16GB RAM available)

    model = get_embedding_model()

    try:
        if model is None:
            # Fall back to placeholder embeddings
            raise ImportError("Model not available")

        # Process in batches to avoid loading all embeddings in memory at once
        total_chunks = len(chunks)
        print(f"   ⏳ Generating embeddings for {total_chunks} chunks (batch size: {batch_size})...")

        for batch_start in range(0, total_chunks, batch_size):
            batch_end = min(batch_start + batch_size, total_chunks)
            batch_chunks = chunks[batch_start:batch_end]

            batch_start_time = time.time()

            # Encode this batch
            embeddings = model.encode(batch_chunks, show_progress_bar=False)

            # Add to results
            for chunk, embedding in zip(batch_chunks, embeddings):
                result.append({
                    'text': chunk,
                    'article_number': extract_article_number(chunk),
                    'embedding': embedding.tolist()
                })

            # Clean up memory after each batch
            del embeddings
            gc.collect()

            # Progress indicator with timing
            batch_time = time.time() - batch_start_time
            progress = min(batch_end, total_chunks)
            chunks_per_sec = len(batch_chunks) / batch_time if batch_time > 0 else 0
            if progress % 64 == 0 or progress == total_chunks:
                print(f"   ⏳ Processed {progress}/{total_chunks} chunks ({chunks_per_sec:.1f} chunks/sec)...")

        print(f"   ✅ Generated embeddings for {len(result)} chunks")
        return result

    except (ImportError, AttributeError):
        # sentence_transformers not available - create dummy embeddings with hashes
        print("   ⚠️  Using placeholder embeddings (model not available)")
        import hashlib

        for chunk in chunks:
            # Create a simple deterministic placeholder embedding based on text hash
            hash_digest = hashlib.md5(chunk.encode()).digest()
            # Convert hash bytes to float array (1024 dims like the real model)
            placeholder_embedding = [float((hash_digest[i % len(hash_digest)] % 256) / 256.0 - 0.5) for i in range(1024)]

            result.append({
                'text': chunk,
                'article_number': extract_article_number(chunk),
                'embedding': placeholder_embedding
            })

        print(f"   ✅ Created placeholder embeddings for {len(result)} chunks")
        return result

    except Exception as e:
        # Any other error - still create placeholder embeddings
        print(f"   ⚠️  Error with embeddings: {str(e)[:100]} - using placeholders")
        import hashlib

        for chunk in chunks:
            hash_digest = hashlib.md5(chunk.encode()).digest()
            placeholder_embedding = [float((hash_digest[i % len(hash_digest)] % 256) / 256.0 - 0.5) for i in range(1024)]

            result.append({
                'text': chunk,
                'article_number': extract_article_number(chunk),
                'embedding': placeholder_embedding
            })

        print(f"   ✅ Created {len(result)} articles with placeholder embeddings")
        return result

def import_to_memgraph(memgraph, cao_name: str, embeddings_data: List[Dict]) -> int:
    """Import chunks with embeddings into Memgraph (optimized batch import)"""
    imported_count = 0
    import_start = time.time()

    # Create CAO node if not exists
    try:
        list(memgraph.execute_and_fetch(f"""
            MERGE (cao:CAO {{name: '{cao_name}', version: '2025', source: 'local'}})
        """))
        print(f"   ✅ CAO node created: {cao_name}")
    except Exception as e:
        print(f"   ⚠️  Error creating CAO node: {e}")

    # Import articles with progress tracking
    total = len(embeddings_data)
    print(f"   ⏳ Importing {total} articles to Memgraph...")

    for idx, data in enumerate(embeddings_data):
        try:
            text_safe = data['text'].replace("'", "\\'").replace('"', '\\"')[:1000]  # Truncate

            query = f"""
            MATCH (cao:CAO {{name: '{cao_name}'}})
            CREATE (article:Article {{
                article_number: '{data['article_number']}_{idx}',
                cao: '{cao_name}',
                content: $content,
                embedding_dim: {len(data['embedding'])}
            }})
            CREATE (cao)-[:CONTAINS_ARTICLE]->(article)
            """

            # Note: gqlalchemy might not support large vector arrays directly
            # We'll store embedding metadata separately if needed
            list(memgraph.execute_and_fetch(query, {'content': text_safe}))
            imported_count += 1

            if (idx + 1) % 100 == 0 or (idx + 1) == total:
                elapsed = time.time() - import_start
                rate = imported_count / elapsed if elapsed > 0 else 0
                print(f"      ✓ Imported {imported_count}/{total} articles ({rate:.1f} articles/sec)...")
        except Exception as e:
            print(f"      ⚠️  Error importing article {idx}: {str(e)[:100]}")

    total_time = time.time() - import_start
    print(f"   ✅ Import complete: {imported_count} articles in {total_time:.1f}s")
    return imported_count

def main():
    """Main import function"""
    if len(sys.argv) < 2:
        print("Usage: python document_importer.py <document_dir>")
        print("Example: python document_importer.py /path/to/cao_documents/")
        sys.exit(1)

    doc_dir = Path(sys.argv[1])

    if not doc_dir.exists():
        print(f"❌ Directory not found: {doc_dir}")
        sys.exit(1)

    print(f"📁 Starting document import from: {doc_dir}\n")

    # Connect to Memgraph
    try:
        from gqlalchemy import Memgraph
        memgraph = Memgraph(
            host=os.getenv('MEMGRAPH_HOST', '46.224.4.188'),
            port=int(os.getenv('MEMGRAPH_PORT', 7687))
        )
        list(memgraph.execute_and_fetch("RETURN 1"))
        print("✅ Connected to Memgraph\n")
    except Exception as e:
        print(f"❌ Cannot connect to Memgraph: {e}")
        sys.exit(1)

    # Find all PDF and TXT files
    files = list(doc_dir.glob("**/*.pdf")) + list(doc_dir.glob("**/*.txt"))

    if not files:
        print(f"⚠️  No PDF or TXT files found in {doc_dir}")
        sys.exit(1)

    print(f"📄 Found {len(files)} document(s) to process\n")

    total_imported = 0
    overall_start = time.time()

    for file_idx, file_path in enumerate(files, 1):
        print(f"📖 [{file_idx}/{len(files)}] Processing: {file_path.name}")
        file_start = time.time()

        # Parse document
        parse_start = time.time()
        cao_name, chunks = parse_document(file_path)
        parse_time = time.time() - parse_start
        print(f"   ✓ Parsed into {len(chunks)} chunks ({parse_time:.1f}s)")

        if not chunks:
            continue

        # Generate embeddings
        embed_start = time.time()
        embeddings_data = generate_embeddings(chunks)
        embed_time = time.time() - embed_start
        print(f"   ✓ Generated {len(embeddings_data)} embeddings ({embed_time:.1f}s)")

        # Import to Memgraph
        imported = import_to_memgraph(memgraph, cao_name, embeddings_data)
        total_imported += imported

        file_time = time.time() - file_start
        print(f"   ✓ File processed in {file_time:.1f}s\n")

    overall_time = time.time() - overall_start
    print(f"\n✅ Import complete!")
    print(f"   Total articles: {total_imported}")
    print(f"   Total time: {overall_time:.1f}s")
    print(f"   Average per document: {overall_time/len(files):.1f}s")

if __name__ == "__main__":
    main()
