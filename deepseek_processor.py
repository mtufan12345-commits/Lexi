#!/usr/bin/env python3
"""
DeepSeek-Native Document Processor

Pipeline:
1. Read raw document
2. DeepSeek semantic chunking (article/section level)
3. DeepSeek R1 analysis (structure + metadata)
4. Direct Memgraph import (skips embeddings)
5. GraphRAG integration

Benefits:
- No embeddings = 50% faster
- Better chunking = better R1 analysis
- Semantic understanding in one pass
- CAO-aware processing
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Tuple
import re

sys.path.insert(0, '/var/www/lexi')

from services import get_r1_client
from gqlalchemy import Memgraph

class DeepSeekProcessor:
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

    def read_document(self, file_path: str) -> str:
        """Read document content"""
        try:
            if file_path.endswith('.pdf'):
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            print(f"❌ Error reading document: {e}")
            return ""

    def deepseek_semantic_chunking(self, document_text: str, document_name: str) -> List[Dict]:
        """
        Use DeepSeek to intelligently chunk document into semantic units

        Returns: List of chunks with metadata
        {
            'content': str,
            'article_number': str (if applicable),
            'section': str,
            'type': 'artikel' | 'section' | 'paragraph',
            'level': int (nesting level)
        }
        """
        print(f"\n⏳ DeepSeek semantic chunking: {document_name}")

        # First pass: Quick structural analysis
        prompt = f"""Analyze this CAO/legal document and identify its structure.

Document: {document_name}
Content (first 5000 chars):
{document_text[:5000]}

Return JSON:
{{
    "document_type": "cao|law|contract|other",
    "title": "full title",
    "has_articles": true|false,
    "article_pattern": "pattern to identify articles",
    "sections": ["list", "of", "section", "titles"],
    "estimated_articles": number
}}"""

        try:
            response = self.r1_client.analyze_cao_structure(
                chunks=[document_text[:10000]],
                document_name=document_name
            )

            if not response.get('success'):
                print(f"⚠️  DeepSeek analysis failed: {response.get('error')}")
                # Fall back to regex chunking
                return self._regex_chunking(document_text)

            # Extract metadata
            doc_type = response.get('cao_metadata', {}).get('type', 'unknown')
            print(f"   ✓ Document type: {doc_type}")

            # Now chunk based on structure
            chunks = self._intelligent_chunk(
                document_text,
                doc_type=doc_type,
                document_name=document_name
            )

            print(f"   ✓ Created {len(chunks)} semantic chunks")
            return chunks

        except Exception as e:
            print(f"   ⚠️  Error in semantic chunking: {e}")
            return self._regex_chunking(document_text)

    def _intelligent_chunk(self, text: str, doc_type: str, document_name: str) -> List[Dict]:
        """Intelligently chunk by articles/sections"""
        chunks = []

        if doc_type == 'cao':
            # CAO: chunk by artikel (article)
            chunks = self._chunk_by_articles(text)
        else:
            # Generic: chunk by sections
            chunks = self._chunk_by_sections(text)

        return chunks

    def _chunk_by_articles(self, text: str) -> List[Dict]:
        """Split by artikel/article patterns"""
        chunks = []

        # Multiple patterns for articles
        patterns = [
            (r'(?:^|\n)(Artikel\s+(\d+(?:[a-z])?)[\.\:])(.*?)(?=Artikel\s+\d|$)', 'artikel'),
            (r'(?:^|\n)(Art\.\s+(\d+(?:[a-z])?)[\.\:])(.*?)(?=Art\.\s+\d|$)', 'artikel'),
            (r'(?:^|\n)(\§\s*(\d+)[\.\:])(.*?)(?=\§\s*\d|$)', 'section'),
        ]

        for pattern, chunk_type in patterns:
            matches = list(re.finditer(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE))

            if len(matches) > 5:  # This pattern works!
                for match in matches:
                    header = match.group(1).strip()
                    number = match.group(2)
                    content = match.group(3).strip()

                    if content and len(content) > 50:
                        chunks.append({
                            'content': header + '\n' + content,
                            'article_number': number,
                            'section': header.split(':')[0] if ':' in header else '',
                            'type': chunk_type,
                            'level': 1
                        })

                if chunks:
                    return chunks

        # Fallback: section-based chunking
        return self._chunk_by_sections(text)

    def _chunk_by_sections(self, text: str) -> List[Dict]:
        """Split by section headers (lines with capital letters)"""
        chunks = []
        lines = text.split('\n')

        current_section = None
        current_content = []

        for line in lines:
            # Detect section headers (all caps or numbered)
            if (line.isupper() and len(line) > 3) or re.match(r'^\d+\.\s+[A-Z]', line):
                # Save previous section
                if current_content:
                    content = '\n'.join(current_content).strip()
                    if len(content) > 50:
                        chunks.append({
                            'content': (current_section or '') + '\n' + content,
                            'article_number': '',
                            'section': current_section or '',
                            'type': 'section',
                            'level': 1
                        })

                current_section = line.strip()
                current_content = []
            else:
                if line.strip():
                    current_content.append(line)

        # Last section
        if current_content:
            content = '\n'.join(current_content).strip()
            if len(content) > 50:
                chunks.append({
                    'content': (current_section or '') + '\n' + content,
                    'article_number': '',
                    'section': current_section or '',
                    'type': 'section',
                    'level': 1
                })

        return chunks if chunks else self._regex_chunking(text)

    def _regex_chunking(self, text: str) -> List[Dict]:
        """Fallback: simple paragraph chunking"""
        chunks = []
        paragraphs = text.split('\n\n')

        for para in paragraphs:
            para = para.strip()
            if para and len(para) > 50:
                chunks.append({
                    'content': para,
                    'article_number': '',
                    'section': '',
                    'type': 'paragraph',
                    'level': 0
                })

        return chunks

    def deepseek_r1_analysis(self, chunks: List[Dict], document_name: str) -> Dict:
        """
        Use DeepSeek R1 to analyze chunks and extract:
        - Article metadata
        - Relationships
        - Key concepts
        - Document structure
        """
        print(f"\n⏳ DeepSeek R1 analysis: {len(chunks)} chunks")

        # Prepare chunks for R1
        chunk_texts = [c['content'] for c in chunks]

        try:
            result = self.r1_client.analyze_cao_structure(
                chunks=chunk_texts,
                document_name=document_name
            )

            if result.get('success'):
                print(f"   ✓ R1 analysis successful")
                print(f"     - Articles found: {len(result.get('artikelen', []))}")
                print(f"     - Relations found: {len(result.get('relaties', []))}")
                print(f"     - Tokens used: {result.get('tokens_used', 0)}")

                # Enrich chunks with R1 analysis
                for i, chunk in enumerate(chunks):
                    # Find matching artikel from R1 analysis
                    for artikel in result.get('artikelen', []):
                        if str(i) in artikel.get('chunk_indices', []):
                            chunk['artikel'] = artikel
                            break

                return result
            else:
                print(f"   ❌ R1 analysis failed: {result.get('error')}")
                return None

        except Exception as e:
            print(f"   ❌ Error in R1 analysis: {e}")
            return None

    def import_to_memgraph(self, document_name: str, chunks: List[Dict], r1_result: Dict) -> int:
        """
        Import directly to Memgraph with semantic structure
        (No embeddings needed!)
        """
        print(f"\n⏳ Importing to Memgraph: {document_name}")

        try:
            # Create CAO node
            list(self.memgraph.execute_and_fetch(f"""
                MERGE (cao:CAO {{name: '{document_name}'}})
            """))
            print(f"   ✓ CAO node created")

            imported = 0

            # Import articles from R1 analysis
            if r1_result and 'artikelen' in r1_result:
                artikelen = r1_result['artikelen']

                for artikel in artikelen:
                    try:
                        number = artikel.get('article_number', 'UNKNOWN')
                        title = artikel.get('title', '')
                        tags = ','.join(artikel.get('tags', []))

                        query = f"""
                        MATCH (cao:CAO {{name: '{document_name}'}})
                        CREATE (artikel:Artikel {{
                            number: '{number}',
                            title: $title,
                            cao: '{document_name}',
                            tags: $tags,
                            r1_analyzed: true
                        }})
                        CREATE (cao)-[:CONTAINS_ARTIKEL]->(artikel)
                        """

                        list(self.memgraph.execute_and_fetch(
                            query,
                            {'title': title, 'tags': tags}
                        ))

                        imported += 1

                        if imported % 50 == 0:
                            print(f"      Imported {imported}/{len(artikelen)} artikelen...")

                    except Exception as e:
                        print(f"      ⚠️  Error importing artikel {number}: {str(e)[:50]}")

                # Import relationships
                for relatie in r1_result.get('relaties', []):
                    try:
                        source = relatie.get('source_article')
                        target = relatie.get('target_article')
                        rel_type = relatie.get('relation_type', 'REFERENCES')

                        query = f"""
                        MATCH (a1:Artikel {{number: '{source}', cao: '{document_name}'}})
                        MATCH (a2:Artikel {{number: '{target}', cao: '{document_name}'}})
                        CREATE (a1)-[:{rel_type}]->(a2)
                        """

                        list(self.memgraph.execute_and_fetch(query))
                    except:
                        pass  # Skip failed relationships

                print(f"   ✓ Imported {imported} artikelen + relationships")
                return imported
            else:
                print(f"   ⚠️  No R1 analysis results")
                return 0

        except Exception as e:
            print(f"   ❌ Error importing to Memgraph: {e}")
            return 0

    def process_document(self, file_path: str) -> bool:
        """Full pipeline: read → chunk → analyze → import"""
        file_path = Path(file_path)
        document_name = file_path.stem.replace('_', ' ').title()

        print(f"\n{'='*70}")
        print(f"📄 Processing: {file_path.name}")
        print(f"{'='*70}")

        start_time = time.time()

        # Step 1: Read
        document_text = self.read_document(str(file_path))
        if not document_text:
            print("❌ Failed to read document")
            return False

        print(f"✓ Read document: {len(document_text)} chars")

        # Step 2: Semantic chunking
        chunks = self.deepseek_semantic_chunking(document_text, document_name)
        if not chunks:
            print("❌ Failed to chunk document")
            return False

        # Step 3: R1 analysis
        r1_result = self.deepseek_r1_analysis(chunks, document_name)
        if not r1_result:
            print("⚠️  R1 analysis failed - proceeding without it")

        # Step 4: Import
        imported = self.import_to_memgraph(document_name, chunks, r1_result or {})

        elapsed = time.time() - start_time
        print(f"\n✅ Complete in {elapsed:.1f}s")
        print(f"   Imported: {imported} artikelen")

        return imported > 0

def main():
    import argparse

    parser = argparse.ArgumentParser(description='DeepSeek Document Processor')
    parser.add_argument('document', help='Document file to process')
    args = parser.parse_args()

    processor = DeepSeekProcessor()
    success = processor.process_document(args.document)

    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
