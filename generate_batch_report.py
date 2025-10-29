#!/usr/bin/env python3
"""
Generate comprehensive batch processing report
Shows all documents, artikelen per document, success rate, and statistics
"""

import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

def parse_batch_log(log_file):
    """Parse the batch processing log and extract document statistics"""

    results = []

    with open(log_file, 'r') as f:
        for line in f:
            # Match pattern: [timestamp] [number/total] ✅/❌ filename: N artikelen in Xs
            match = re.search(
                r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\d+)/(\d+)\] ([✅❌]) (.+?): (\d+) artikelen in ([\d.]+)s',
                line
            )

            if match:
                timestamp, doc_num, total, status, filename, artikelen, time_taken = match.groups()
                results.append({
                    'timestamp': timestamp,
                    'number': int(doc_num),
                    'total': int(total),
                    'status': 'SUCCESS' if status == '✅' else 'FAILED',
                    'filename': filename,
                    'artikelen': int(artikelen),
                    'time_seconds': float(time_taken)
                })

    return results

def generate_report(log_file, output_file):
    """Generate comprehensive report"""

    results = parse_batch_log(log_file)

    if not results:
        print(f"❌ No batch results found in {log_file}")
        return

    # Calculate statistics
    total_docs = len(results)
    successful_docs = len([r for r in results if r['status'] == 'SUCCESS'])
    failed_docs = len([r for r in results if r['status'] == 'FAILED'])
    total_artikelen = sum(r['artikelen'] for r in results)
    total_time = sum(r['time_seconds'] for r in results)
    avg_time_per_doc = total_time / total_docs if total_docs > 0 else 0

    # Generate report
    report = []
    report.append("=" * 100)
    report.append("LEXI AI - BATCH DOCUMENT PROCESSING REPORT")
    report.append("=" * 100)
    report.append(f"\nReport Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Log File: {log_file}\n")

    # Summary statistics
    report.append("\n" + "=" * 100)
    report.append("SUMMARY STATISTICS")
    report.append("=" * 100)
    report.append(f"\nTotal Documents:        {total_docs}")
    report.append(f"✅ Successful:          {successful_docs} ({100*successful_docs/total_docs:.1f}%)")
    report.append(f"❌ Failed/No Artikelen: {failed_docs} ({100*failed_docs/total_docs:.1f}%)")
    report.append(f"\nTotal Artikelen:        {total_artikelen}")
    report.append(f"Avg Artikelen/Doc:      {total_artikelen/successful_docs:.1f}" if successful_docs > 0 else "N/A")
    report.append(f"\nTotal Processing Time:  {total_time/60:.1f} minutes ({total_time/3600:.1f} hours)")
    report.append(f"Avg Time/Document:      {avg_time_per_doc:.1f} seconds")
    report.append(f"Processing Rate:        {total_artikelen/(total_time/3600):.1f} artikelen/hour")

    # Detailed document list
    report.append("\n\n" + "=" * 100)
    report.append("DETAILED DOCUMENT PROCESSING RESULTS")
    report.append("=" * 100)
    report.append(f"\n{'#':<5} {'Status':<10} {'Artikelen':<12} {'Time (s)':<10} {'Document Name':<50}")
    report.append("-" * 100)

    for result in results:
        status_icon = "✅ OK" if result['status'] == 'SUCCESS' else "❌ FAIL"
        report.append(
            f"{result['number']:<5} {status_icon:<10} {result['artikelen']:<12} "
            f"{result['time_seconds']:<10.1f} {result['filename']:<50}"
        )

    # Statistics by status
    report.append("\n\n" + "=" * 100)
    report.append("RESULTS BY STATUS")
    report.append("=" * 100)

    successful = [r for r in results if r['status'] == 'SUCCESS']
    failed = [r for r in results if r['status'] == 'FAILED']

    if successful:
        report.append(f"\n✅ SUCCESSFUL DOCUMENTS ({len(successful)}):")
        report.append("-" * 100)
        total_artikelen_success = 0
        for result in successful:
            report.append(f"  [{result['number']:2d}] {result['filename']:<50} → {result['artikelen']:3d} artikelen ({result['time_seconds']:6.1f}s)")
            total_artikelen_success += result['artikelen']
        report.append(f"\n  Total: {total_artikelen_success} artikelen imported")

    if failed:
        report.append(f"\n\n❌ FAILED DOCUMENTS ({len(failed)}):")
        report.append("-" * 100)
        for result in failed:
            report.append(f"  [{result['number']:2d}] {result['filename']:<50} ({result['time_seconds']:6.1f}s)")

    # Top documents by artikelen count
    report.append("\n\n" + "=" * 100)
    report.append("TOP 10 DOCUMENTS BY ARTIKELEN COUNT")
    report.append("=" * 100)
    report.append(f"\n{'Rank':<6} {'Artikelen':<12} {'Document Name':<50}")
    report.append("-" * 100)

    sorted_by_artikelen = sorted([r for r in results if r['artikelen'] > 0],
                                 key=lambda x: x['artikelen'], reverse=True)[:10]
    for idx, result in enumerate(sorted_by_artikelen, 1):
        report.append(f"{idx:<6} {result['artikelen']:<12} {result['filename']:<50}")

    # Processing speed analysis
    report.append("\n\n" + "=" * 100)
    report.append("PROCESSING SPEED ANALYSIS")
    report.append("=" * 100)

    sorted_by_time = sorted(results, key=lambda x: x['time_seconds'], reverse=True)[:10]
    report.append(f"\nSlowest Documents (Top 10):")
    report.append(f"\n{'#':<5} {'Time (s)':<12} {'Artikelen':<12} {'Document Name':<50}")
    report.append("-" * 100)
    for result in sorted_by_time:
        report.append(f"{result['number']:<5} {result['time_seconds']:<12.1f} {result['artikelen']:<12} {result['filename']:<50}")

    # Write report
    report_text = "\n".join(report)

    with open(output_file, 'w') as f:
        f.write(report_text)

    # Also print to console
    print(report_text)
    print(f"\n✅ Report saved to: {output_file}")

if __name__ == '__main__':
    import sys

    log_file = sys.argv[1] if len(sys.argv) > 1 else '/var/log/lexi/deepseek_batch.log'
    output_file = sys.argv[2] if len(sys.argv) > 2 else '/var/log/lexi/batch_report.txt'

    generate_report(log_file, output_file)
