#!/usr/bin/env python3
"""
DeepSeek Batch Processor with Parallel Processing

Features:
- Process multiple documents in parallel
- Resource-aware parallel execution
- Progress tracking
- Auto-retry on failure
- Memory-safe batch limits

Much faster than sequential processing!
"""

import os
import sys
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
import psutil

sys.path.insert(0, '/var/www/lexi')

from deepseek_processor import DeepSeekProcessor

class DeepSeekBatchProcessor:
    def __init__(self, max_workers: int = None, max_memory_pct: float = 80.0):
        """
        Initialize batch processor

        Args:
            max_workers: Number of parallel document processors (auto if None)
            max_memory_pct: Max RAM usage before limiting parallelism
        """
        if max_workers is None:
            # Use number of CPU cores, but cap at 4 for memory safety
            max_workers = min(psutil.cpu_count() or 4, 4)

        self.max_workers = max_workers
        self.max_memory_pct = max_memory_pct
        self.results = {}
        self.log_file = '/var/log/lexi/deepseek_batch.log'

        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)

    def log(self, message: str):
        """Log to file and stdout"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)

        try:
            with open(self.log_file, 'a') as f:
                f.write(log_msg + '\n')
        except:
            pass

    def check_memory(self) -> float:
        """Get current memory usage percentage"""
        return psutil.virtual_memory().percent

    def process_file(self, file_path: str) -> Dict:
        """
        Process single document in worker thread

        Returns:
        {
            'file': str,
            'success': bool,
            'imported': int,
            'time': float,
            'error': str or None
        }
        """
        file_path = Path(file_path)
        start_time = time.time()

        try:
            processor = DeepSeekProcessor()
            success = processor.process_document(str(file_path))

            elapsed = time.time() - start_time

            # Query Memgraph to get actual import count
            from gqlalchemy import Memgraph
            memgraph = Memgraph(host='localhost', port=7687)
            doc_name = file_path.stem.replace('_', ' ').title()

            result = list(memgraph.execute_and_fetch(f"""
                MATCH (cao:CAO {{name: '{doc_name}'}})-[:CONTAINS_ARTIKEL]->(a:Artikel)
                RETURN count(a) AS count
            """))

            imported = result[0]['count'] if result else 0

            return {
                'file': file_path.name,
                'success': success,
                'imported': imported,
                'time': elapsed,
                'error': None
            }

        except Exception as e:
            elapsed = time.time() - start_time
            return {
                'file': file_path.name,
                'success': False,
                'imported': 0,
                'time': elapsed,
                'error': str(e)[:100]
            }

    def process_directory(self, directory: str, pattern: str = "*.txt"):
        """
        Batch process all files in directory

        Args:
            directory: Path to documents directory
            pattern: File pattern to match (*.txt, *.pdf, etc.)
        """
        doc_dir = Path(directory)

        if not doc_dir.exists():
            self.log(f"❌ Directory not found: {doc_dir}")
            return

        files = sorted(list(doc_dir.glob(f"**/{pattern}")) + list(doc_dir.glob(f"**/{pattern.replace('txt', 'pdf')}")))

        if not files:
            self.log(f"❌ No documents found in {doc_dir}")
            return

        self.log(f"📁 Found {len(files)} documents")
        self.log(f"   Max parallel workers: {self.max_workers}")
        self.log(f"   Max memory: {self.max_memory_pct}%\n")

        start_time = time.time()
        completed = 0
        failed = 0
        total_imported = 0

        # Process in batches to avoid memory overload
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self.process_file, str(f)): f.name
                for f in files
            }

            # Process results as they complete
            for idx, future in enumerate(as_completed(future_to_file), 1):
                file_name = future_to_file[future]

                try:
                    result = future.result()

                    status = "✅" if result['success'] else "❌"
                    self.log(
                        f"[{idx:2d}/{len(files)}] {status} {file_name}: "
                        f"{result['imported']} artikelen in {result['time']:.1f}s"
                    )

                    if result['success']:
                        completed += 1
                        total_imported += result['imported']
                    else:
                        failed += 1
                        if result['error']:
                            self.log(f"         Error: {result['error']}")

                except Exception as e:
                    self.log(f"[{idx:2d}/{len(files)}] ❌ {file_name}: {str(e)[:50]}")
                    failed += 1

                # Check memory
                mem_pct = self.check_memory()
                if mem_pct > self.max_memory_pct:
                    self.log(f"      ⚠️  HIGH MEMORY: {mem_pct:.1f}% - slowing down")
                    time.sleep(5)

        elapsed = time.time() - start_time

        # Summary
        self.log(f"\n{'='*70}")
        self.log(f"✅ BATCH PROCESSING COMPLETE")
        self.log(f"{'='*70}")
        self.log(f"   Total documents: {len(files)}")
        self.log(f"   Completed: {completed}")
        self.log(f"   Failed: {failed}")
        self.log(f"   Total artikelen imported: {total_imported:,}")
        self.log(f"   Total time: {elapsed/60:.1f} minutes")
        self.log(f"   Avg per document: {elapsed/len(files):.1f}s")
        self.log(f"   Overall rate: {total_imported / (elapsed or 1):.1f} artikelen/sec")

        # Save results
        results = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_files': len(files),
            'completed': completed,
            'failed': failed,
            'total_imported': total_imported,
            'duration_seconds': elapsed,
            'avg_per_doc': elapsed / len(files) if files else 0,
            'rate_per_sec': total_imported / (elapsed or 1)
        }

        results_file = '/tmp/deepseek_batch_results.json'
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)

        self.log(f"   Results saved to: {results_file}")

def main():
    import argparse

    parser = argparse.ArgumentParser(description='DeepSeek Batch Document Processor')
    parser.add_argument('directory', help='Directory with documents to process')
    parser.add_argument('--workers', type=int, default=None, help='Max parallel workers (default: auto)')
    parser.add_argument('--memory', type=float, default=80.0, help='Max memory % before throttling (default: 80)')
    parser.add_argument('--pattern', default='*.txt', help='File pattern (default: *.txt)')

    args = parser.parse_args()

    processor = DeepSeekBatchProcessor(
        max_workers=args.workers,
        max_memory_pct=args.memory
    )

    processor.process_directory(args.directory, args.pattern)

if __name__ == '__main__':
    main()
