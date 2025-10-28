#!/usr/bin/env python3
"""
Document Tracker - Maintains a registry of uploaded documents
Stores: bestandsnaam, upload_date, article_count, cao_name
"""
import json
from pathlib import Path
from datetime import datetime

TRACKER_FILE = Path('/tmp/document_uploads_registry.json')

def initialize_tracker():
    """Initialize tracker file if it doesn't exist"""
    if not TRACKER_FILE.exists():
        data = {
            'documents': [],
            'total_uploads': 0,
            'last_updated': datetime.now().isoformat()
        }
        with open(TRACKER_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    return load_tracker()

def load_tracker():
    """Load tracker data"""
    try:
        if TRACKER_FILE.exists():
            with open(TRACKER_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'documents': [], 'total_uploads': 0}

def save_tracker(data):
    """Save tracker data"""
    data['last_updated'] = datetime.now().isoformat()
    with open(TRACKER_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def add_document(filename, cao_name, article_count):
    """Add a new uploaded document to tracker"""
    tracker = load_tracker()

    doc_entry = {
        'id': f"doc_{len(tracker['documents']) + 1}",
        'filename': filename,
        'cao_name': cao_name,
        'article_count': article_count,
        'upload_date': datetime.now().isoformat(),
        'status': 'indexed'
    }

    tracker['documents'].append(doc_entry)
    tracker['total_uploads'] = len(tracker['documents'])
    save_tracker(tracker)

    return doc_entry

def get_all_documents():
    """Get all tracked documents"""
    return load_tracker().get('documents', [])

def delete_document(doc_id):
    """Delete a document from tracker"""
    tracker = load_tracker()
    tracker['documents'] = [d for d in tracker['documents'] if d['id'] != doc_id]
    tracker['total_uploads'] = len(tracker['documents'])
    save_tracker(tracker)
    return True

def get_document_by_id(doc_id):
    """Get a specific document"""
    documents = get_all_documents()
    return next((d for d in documents if d['id'] == doc_id), None)

if __name__ == '__main__':
    # Initialize
    initialize_tracker()
    # Test
    add_document('test_cao.pdf', 'Test CAO 2025', 145)
    print("✅ Tracker initialized")
    print(json.dumps(get_all_documents(), indent=2))
