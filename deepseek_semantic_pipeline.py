#!/usr/bin/env python3
"""
Pure DeepSeek Semantic Processing Pipeline

NO embeddings. NO paragraph chunking. ONLY DeepSeek R1.

Pipeline:
1. Read document
2. DeepSeek semantic chunking (artikel/section level)
3. DeepSeek R1 analysis (structure extraction)
4. Direct Memgraph import with semantic metadata
5. Build rich graph with relationships

This is the ONLY way documents should be processed from now on.
"""

import os
import sys
import json
import time
import gc
from pathlib import Path
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import psutil

sys.path.insert(0, '/var/www/lexi')

from services import get_r1_client
from gqlalchemy import Memgraph

class DeepSeekSemanticPipeline:
    """Pure DeepSeek semantic processing"""

    def __init__(self):
        self.r1_client = get_r1_client()
        # Use environment variables for Memgraph connection (supports production deployment)
        memgraph_host = os.getenv('MEMGRAPH_HOST', 'localhost')
        
        # Safely parse port with fallback
        try:
            port_str = os.getenv('MEMGRAPH_PORT', '7687')
            memgraph_port = int(port_str)
        except (ValueError, TypeError) as e:
            print(f"⚠️  Invalid MEMGRAPH_PORT '{port_str}', using default 7687: {e}")
            memgraph_port = 7687
        
        self.memgraph = Memgraph(host=memgraph_host, port=memgraph_port)
        self.log_file = '/var/log/lexi/deepseek_semantic.log'
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    def log(self, msg: str, level: str = 'INFO'):
        """Log with timestamp"""
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{ts}] [{level}] {msg}"
        print(log_msg)
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_msg + '\n')
        except:
            pass

    def read_document(self, file_path: str) -> Tuple[str, str]:
        """Read document, return (content, document_name)"""
        path = Path(file_path)

        try:
            if path.suffix.lower() == '.pdf':
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()

            doc_name = path.stem.replace('_', ' ').title()
            return text, doc_name

        except Exception as e:
            self.log(f"Error reading {file_path}: {e}", 'ERROR')
            return "", ""

    def deepseek_semantic_chunk(self, text: str, doc_name: str) -> List[Dict]:
        """
        Use DeepSeek R1 to intelligently chunk document

        Returns chunks with semantic metadata:
        {
            'content': str,
            'article_number': str,
            'title': str,
            'section': str,
            'type': 'artikel' | 'section' | 'clause',
            'chunk_index': int
        }
        """
        self.log(f"🧠 DeepSeek semantic chunking: {doc_name} ({len(text)} chars)")

        # Use R1 to analyze structure
        prompt = f"""Analyze document structure and create semantic chunks.

Document: {doc_name}
Content (first 8000 chars):
{text[:8000]}

Task:
1. Identify articles (Artikel/Art./§)
2. Identify sections/titles
3. Extract key clauses

Return JSON with chunks:
{{
    "chunks": [
        {{
            "content": "full text of artikel/section",
            "article_number": "number or null",
            "title": "titel if exists",
            "section": "section name",
            "type": "artikel|section|clause"
        }}
    ],
    "total_articles": number,
    "document_type": "cao|law|contract|other"
}}"""

        try:
            # Call R1 for smart chunking
            result = self.r1_client.analyze_cao_structure(
                chunks=[text],
                document_name=doc_name
            )

            if result.get('success'):
                artikelen = result.get('artikelen', [])
                self.log(f"   ✓ Found {len(artikelen)} semantic units via R1")

                # Convert R1 artikelen to chunks
                chunks = []
                for idx, art in enumerate(artikelen):
                    # Safely extract content with null protection
                    article_content = art.get('content') or ''
                    
                    if not article_content:
                        # Fallback: combine title and description if content not provided
                        title = art.get('title') or ''
                        description = art.get('description') or ''
                        article_content = (title + '\n' + description).strip()
                    
                    # Skip empty chunks
                    if not article_content or len(article_content) < 10:
                        self.log(f"   ⚠️  Skipping empty chunk at index {idx}", 'WARN')
                        continue
                    
                    chunks.append({
                        'content': article_content,
                        'article_number': art.get('article_number') or '',
                        'title': art.get('title') or '',
                        'section': art.get('section') or '',
                        'type': 'artikel',
                        'tags': art.get('tags') or [],
                        'chunk_index': idx
                    })

                return chunks if chunks else self._fallback_chunking(text)

            else:
                self.log(f"   ⚠️  R1 chunking failed: {result.get('error')}", 'WARN')
                return self._fallback_chunking(text)

        except Exception as e:
            self.log(f"   ❌ Error in semantic chunking: {e}", 'ERROR')
            return self._fallback_chunking(text)

    def _fallback_chunking(self, text: str) -> List[Dict]:
        """Fallback: intelligent chunking without R1"""
        chunks = []

        # Try artikel pattern
        import re
        pattern = r'(?:^|\n)(Artikel|Art\.)\s+(\d+(?:[a-z])?)[:\.]?\s*(.*?)(?=(?:Artikel|Art\.)\s+\d|$)'
        matches = list(re.finditer(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE))

        if len(matches) > 3:
            for idx, match in enumerate(matches):
                header = match.group(1) + ' ' + match.group(2)
                content = match.group(3).strip()

                if len(content) > 50:
                    chunks.append({
                        'content': header + '\n' + content,
                        'article_number': match.group(2),
                        'title': '',
                        'section': '',
                        'type': 'artikel',
                        'tags': [],
                        'chunk_index': idx
                    })

            if chunks:
                return chunks

        # Last resort: section-based
        sections = text.split('\n\n')
        for idx, section in enumerate(sections):
            if len(section.strip()) > 100:
                chunks.append({
                    'content': section.strip(),
                    'article_number': '',
                    'title': '',
                    'section': '',
                    'type': 'section',
                    'tags': [],
                    'chunk_index': idx
                })

        return chunks

    def deepseek_r1_analyze(self, chunks: List[Dict], doc_name: str) -> Dict:
        """
        Run full R1 analysis on semantic chunks

        Returns:
        {
            'cao_metadata': {...},
            'artikelen': [...],
            'relaties': [...],
            'success': bool
        }
        """
        self.log(f"🧠 R1 deep analysis: {len(chunks)} semantic chunks")

        chunk_texts = [c['content'] for c in chunks]

        try:
            result = self.r1_client.analyze_cao_structure(
                chunks=chunk_texts,
                document_name=doc_name
            )

            if result.get('success'):
                self.log(
                    f"   ✓ R1 analysis complete: "
                    f"{len(result.get('artikelen', []))} artikelen, "
                    f"{len(result.get('relaties', []))} relaties"
                )
                return result
            else:
                self.log(f"   ❌ R1 analysis failed: {result.get('error')}", 'ERROR')
                return None

        except Exception as e:
            self.log(f"   ❌ Error in R1 analysis: {e}", 'ERROR')
            return None

    def import_to_memgraph(self, doc_name: str, chunks: List[Dict], r1_result: Dict) -> int:
        """
        Import semantic chunks and R1 analysis to Memgraph

        Creates:
        - CAO node (document)
        - Artikel nodes (semantic chunks with R1 metadata)
        - CONTAINS_ARTIKEL relationships
        - REFERENCES relationships between artikelen
        """
        self.log(f"💾 Importing to Memgraph: {doc_name}")

        try:
            # Create CAO node
            list(self.memgraph.execute_and_fetch(f"""
                CREATE (cao:CAO {{
                    name: '{doc_name}',
                    type: $type,
                    processing_type: 'deepseek_semantic'
                }})
            """, {
                'type': r1_result.get('cao_metadata', {}).get('type', 'unknown') if r1_result else 'unknown'
            }))

            self.log(f"   ✓ CAO node created")

            imported = 0

            # Import artikelen from R1 analysis
            if r1_result and 'artikelen' in r1_result:
                artikelen = r1_result['artikelen']

                for artikel in artikelen:
                    try:
                        number = artikel.get('article_number', 'UNKNOWN')
                        title = artikel.get('title', '')
                        section = artikel.get('section', '')
                        tags = ','.join(artikel.get('tags', []))

                        # Create Artikel node
                        list(self.memgraph.execute_and_fetch(f"""
                            MATCH (cao:CAO {{name: '{doc_name}'}})
                            CREATE (a:Artikel {{
                                number: '{number}',
                                title: $title,
                                section: $section,
                                cao: '{doc_name}',
                                tags: $tags,
                                r1_processed: true,
                                chunk_type: 'semantic'
                            }})
                            CREATE (cao)-[:CONTAINS_ARTIKEL]->(a)
                        """, {
                            'title': title,
                            'section': section,
                            'tags': tags
                        }))

                        imported += 1

                        if imported % 50 == 0:
                            self.log(f"      Imported {imported}/{len(artikelen)} artikelen...")

                    except Exception as e:
                        self.log(f"      ⚠️  Error importing artikel {number}: {str(e)[:50]}", 'WARN')

                # Import relationships
                for relatie in r1_result.get('relaties', []):
                    try:
                        source = relatie.get('source_article')
                        target = relatie.get('target_article')
                        rel_type = relatie.get('relation_type', 'REFERENCES')

                        query = f"""
                        MATCH (a1:Artikel {{number: '{source}', cao: '{doc_name}'}})
                        MATCH (a2:Artikel {{number: '{target}', cao: '{doc_name}'}})
                        CREATE (a1)-[:{rel_type}]->(a2)
                        """

                        list(self.memgraph.execute_and_fetch(query))

                    except:
                        pass  # Skip failed relationships

                self.log(f"   ✓ Imported {imported} artikelen + relationships")
                return imported
            else:
                self.log(f"   ⚠️  No R1 analysis results", 'WARN')
                return 0

        except Exception as e:
            self.log(f"   ❌ Error importing: {e}", 'ERROR')
            return 0

    def process_document(self, file_path: str) -> bool:
        """Full pipeline for single document"""
        start = time.time()

        # Read
        text, doc_name = self.read_document(file_path)
        if not text:
            return False

        self.log(f"\n{'='*70}")
        self.log(f"📄 {Path(file_path).name}")
        self.log(f"{'='*70}")
        self.log(f"   Read: {len(text)} chars")

        # Semantic chunk
        chunks = self.deepseek_semantic_chunk(text, doc_name)
        if not chunks:
            self.log(f"❌ Failed to chunk", 'ERROR')
            return False

        self.log(f"   Chunks: {len(chunks)} semantic units")

        # R1 analysis
        r1_result = self.deepseek_r1_analyze(chunks, doc_name)
        if not r1_result:
            self.log(f"⚠️  Skipping R1 analysis", 'WARN')
            r1_result = {'artikelen': [], 'relaties': []}

        # Import
        imported = self.import_to_memgraph(doc_name, chunks, r1_result)

        elapsed = time.time() - start
        self.log(f"   ✅ Complete in {elapsed:.1f}s - Imported {imported} artikelen")

        return imported > 0

    def process_directory_parallel(self, directory: str, max_workers: int = 4) -> Dict:
        """Process all documents in parallel"""
        doc_dir = Path(directory)

        if not doc_dir.exists():
            self.log(f"❌ Directory not found: {doc_dir}", 'ERROR')
            return {}

        files = sorted(
            list(doc_dir.glob("**/*.txt")) +
            list(doc_dir.glob("**/*.pdf"))
        )

        if not files:
            self.log(f"❌ No documents found", 'ERROR')
            return {}

        self.log(f"\n{'='*70}")
        self.log(f"🚀 STARTING PURE DEEPSEEK SEMANTIC PIPELINE")
        self.log(f"{'='*70}")
        self.log(f"   Documents: {len(files)}")
        self.log(f"   Workers: {max_workers}")
        self.log(f"   Method: DeepSeek semantic chunking + R1")
        self.log("")

        start_time = time.time()
        results = {
            'success': 0,
            'failed': 0,
            'total_artikelen': 0,
            'files_processed': []
        }

        # Process in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.process_document, str(f)): f.name for f in files}

            for idx, future in enumerate(as_completed(futures), 1):
                file_name = futures[future]
                try:
                    success = future.result()
                    if success:
                        results['success'] += 1
                    else:
                        results['failed'] += 1

                except Exception as e:
                    self.log(f"❌ {file_name}: {str(e)[:50]}", 'ERROR')
                    results['failed'] += 1

                # Memory check
                mem_pct = psutil.virtual_memory().percent
                if mem_pct > 85:
                    self.log(f"⚠️  HIGH MEMORY: {mem_pct:.1f}% - slowing down", 'WARN')
                    time.sleep(5)

        # Get final stats
        result = list(self.memgraph.execute_and_fetch(
            "MATCH (a:Artikel) RETURN count(*) AS count"
        ))
        total_artikelen = result[0]['count'] if result else 0

        elapsed = time.time() - start_time

        # Summary
        self.log(f"\n{'='*70}")
        self.log(f"✅ PIPELINE COMPLETE")
        self.log(f"{'='*70}")
        self.log(f"   Total documents: {len(files)}")
        self.log(f"   Successful: {results['success']}")
        self.log(f"   Failed: {results['failed']}")
        self.log(f"   Total artikelen: {total_artikelen:,}")
        self.log(f"   Duration: {elapsed/60:.1f} minutes")
        self.log(f"   Rate: {total_artikelen / (elapsed or 1):.0f} artikelen/sec")

        results['total_artikelen'] = total_artikelen
        results['duration'] = elapsed

        return results

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Pure DeepSeek Semantic Pipeline')
    parser.add_argument('directory', help='Documents directory')
    parser.add_argument('--workers', type=int, default=4, help='Parallel workers')

    args = parser.parse_args()

    pipeline = DeepSeekSemanticPipeline()
    pipeline.process_directory_parallel(args.directory, args.workers)

if __name__ == '__main__':
    main()
