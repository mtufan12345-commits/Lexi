#!/usr/bin/env python3
"""
Safe Document Importer with Memory Management

Features:
- Batch processing with memory limits
- Graceful memory cleanup between documents
- Progress tracking
- Error recovery
- Resource monitoring
"""

import os
import sys
import gc
import psutil
import json
import time
from pathlib import Path
from typing import List, Dict
from datetime import datetime

sys.path.insert(0, '/var/www/lexi')

from gqlalchemy import Memgraph
from document_importer import parse_document, generate_embeddings, import_to_memgraph

class SafeDocumentImporter:
    def __init__(self, memgraph_host='localhost', memgraph_port=7687):
        self.memgraph = Memgraph(host=memgraph_host, port=memgraph_port)
        self.import_state_file = '/tmp/import_state.json'
        self.max_memory_mb = 3000  # Max RAM to use for embeddings
        self.batch_size_chunks = 32  # Chunks to process at once
        self.log_file = '/var/log/lexi/document_import.log'

        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
        self.load_import_state()

    def log(self, message: str):
        """Log import progress"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)

        try:
            with open(self.log_file, 'a') as f:
                f.write(log_msg + '\n')
        except:
            pass

    def load_import_state(self):
        """Load previously imported documents"""
        try:
            if Path(self.import_state_file).exists():
                with open(self.import_state_file, 'r') as f:
                    self.state = json.load(f)
            else:
                self.state = {'imported_files': [], 'failed_files': []}
        except:
            self.state = {'imported_files': [], 'failed_files': []}

    def save_import_state(self):
        """Save import progress"""
        try:
            with open(self.import_state_file, 'w') as f:
                json.dump(self.state, f)
        except Exception as e:
            self.log(f"⚠️  Error saving state: {e}")

    def check_memory(self):
        """Check current memory usage"""
        memory = psutil.virtual_memory()
        memory_mb = memory.used // (1024*1024)
        return memory_mb, memory.percent

    def cleanup_memory(self):
        """Force memory cleanup"""
        gc.collect()
        time.sleep(0.5)
        mem_mb, mem_pct = self.check_memory()
        self.log(f"   Cleaned memory: {mem_mb}MB ({mem_pct:.1f}%)")

    def import_document(self, file_path: str) -> bool:
        """Import single document safely"""
        file_path = Path(file_path)
        file_name = file_path.name

        # Check if already imported
        if file_name in self.state['imported_files']:
            self.log(f"⏭️  Skipping {file_name} (already imported)")
            return True

        if file_name in self.state['failed_files']:
            self.log(f"⏭️  Skipping {file_name} (previously failed)")
            return False

        try:
            self.log(f"\n📄 Processing: {file_name}")

            # Parse document
            cao_name, chunks = parse_document(str(file_path))

            if not chunks:
                self.log(f"   ⚠️  No chunks extracted")
                self.state['failed_files'].append(file_name)
                self.save_import_state()
                return False

            self.log(f"   ✓ Parsed: {len(chunks)} chunks")

            # Check memory before embeddings
            mem_mb, mem_pct = self.check_memory()
            if mem_pct > 85:
                self.log(f"   🔴 HIGH MEMORY ({mem_pct:.1f}%) - Cleaning...")
                self.cleanup_memory()

            # Generate embeddings with batch size
            self.log(f"   ⏳ Generating embeddings (batch size: {self.batch_size_chunks})...")

            embeddings_data = []
            for batch_start in range(0, len(chunks), self.batch_size_chunks):
                batch_end = min(batch_start + self.batch_size_chunks, len(chunks))
                batch_chunks = chunks[batch_start:batch_end]

                # Generate for this batch
                try:
                    batch_embeddings = generate_embeddings(batch_chunks)
                    embeddings_data.extend(batch_embeddings)

                    # Cleanup after batch
                    del batch_embeddings
                    gc.collect()

                    progress = min(batch_end, len(chunks))
                    self.log(f"      {progress}/{len(chunks)} chunks embedded...")

                    # Check memory
                    mem_mb, mem_pct = self.check_memory()
                    if mem_pct > 90:
                        self.log(f"      ⚠️  HIGH MEMORY - aggressive cleanup")
                        self.cleanup_memory()

                except Exception as e:
                    self.log(f"      ❌ Error in batch {batch_start}-{batch_end}: {e}")
                    self.state['failed_files'].append(file_name)
                    self.save_import_state()
                    return False

            self.log(f"   ✓ Embeddings complete: {len(embeddings_data)} embeddings")

            # Import to Memgraph
            self.log(f"   ⏳ Importing to Memgraph...")
            imported_count = import_to_memgraph(self.memgraph, cao_name, embeddings_data)

            if imported_count > 0:
                self.log(f"   ✅ Imported {imported_count} articles")
                self.state['imported_files'].append(file_name)
                self.save_import_state()

                # Final cleanup
                del embeddings_data
                gc.collect()

                return True
            else:
                self.log(f"   ⚠️  No articles imported")
                self.state['failed_files'].append(file_name)
                self.save_import_state()
                return False

        except Exception as e:
            self.log(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            self.state['failed_files'].append(file_name)
            self.save_import_state()
            return False

    def import_directory(self, directory: str):
        """Import all documents from directory"""
        doc_dir = Path(directory)

        if not doc_dir.exists():
            self.log(f"❌ Directory not found: {doc_dir}")
            return

        files = sorted(list(doc_dir.glob("**/*.pdf")) + list(doc_dir.glob("**/*.txt")))

        self.log(f"📁 Found {len(files)} files to process")
        self.log(f"   Already imported: {len(self.state['imported_files'])}")
        self.log(f"   Failed: {len(self.state['failed_files'])}")

        remaining = [f for f in files if f.name not in self.state['imported_files']]
        self.log(f"   To process: {len(remaining)}\n")

        success = 0
        failed = 0
        start_time = time.time()

        for idx, file_path in enumerate(remaining, 1):
            self.log(f"\n[{idx}/{len(remaining)}]")

            if self.import_document(str(file_path)):
                success += 1
            else:
                failed += 1

            # Memory cleanup every 5 documents
            if idx % 5 == 0:
                self.cleanup_memory()

        elapsed = time.time() - start_time
        self.log(f"\n\n{'='*60}")
        self.log(f"✅ Import Complete!")
        self.log(f"   Success: {success}")
        self.log(f"   Failed: {failed}")
        self.log(f"   Total time: {elapsed/60:.1f} minutes")
        self.log(f"   Avg time per file: {elapsed/len(remaining):.1f}s")
        self.log(f"{'='*60}")

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Safe Document Importer')
    parser.add_argument('directory', help='Directory with documents to import')
    parser.add_argument('--reset', action='store_true', help='Reset import state and start fresh')

    args = parser.parse_args()

    importer = SafeDocumentImporter()

    if args.reset:
        importer.state = {'imported_files': [], 'failed_files': []}
        importer.save_import_state()
        print("⚠️  Import state reset")

    importer.import_directory(args.directory)

if __name__ == '__main__':
    main()
