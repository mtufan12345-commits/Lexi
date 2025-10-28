"""
Document Upload Routes Blueprint
Voeg dit toe aan main.py in Replit
"""

from flask import Blueprint, request, jsonify, render_template
from werkzeug.utils import secure_filename
import os
import threading
import json
from pathlib import Path
import subprocess
import time

# Create blueprint
upload_bp = Blueprint('upload', __name__, url_prefix='/upload')

# Configuration
UPLOAD_DIR = '/tmp/cao_import'
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx'}

# Global upload status tracker
upload_status = {
    'status': 'idle',  # idle, uploading, processing, complete, error
    'progress': 0,
    'current_file': '',
    'total_files': 0,
    'processed_files': 0,
    'messages': [],
    'imported_count': 0,
    'error': None
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@upload_bp.route('/', methods=['GET'])
def upload_page():
    """Render upload interface"""
    return render_template('document_upload.html')


@upload_bp.route('/api/upload', methods=['POST'])
def upload_files():
    """Handle file upload - CSRF exempt for multipart/form-data"""
    global upload_status

    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    files = request.files.getlist('files')

    if not files or files[0].filename == '':
        return jsonify({'error': 'No files selected'}), 400

    # Validate and save files
    valid_files = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_DIR, filename)
            file.save(file_path)
            valid_files.append(file_path)

    if not valid_files:
        return jsonify({'error': 'No valid PDF/TXT/DOCX files provided'}), 400

    # Reset status
    upload_status = {
        'status': 'uploading',
        'progress': 0,
        'current_file': '',
        'total_files': len(valid_files),
        'processed_files': 0,
        'messages': [f"📁 {len(valid_files)} files uploaded successfully"],
        'imported_count': 0,
        'error': None
    }

    # Start async import in background
    thread = threading.Thread(
        target=_process_documents_async,
        args=(valid_files,)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'message': 'Upload successful, processing started',
        'files_count': len(valid_files)
    })


@upload_bp.route('/api/status', methods=['GET'])
def get_status():
    """Get current upload/import status"""
    return jsonify(upload_status)


@upload_bp.route('/api/cancel', methods=['POST'])
def cancel_upload():
    """Cancel current operation"""
    global upload_status
    upload_status['status'] = 'cancelled'
    return jsonify({'message': 'Operation cancelled'})


@upload_bp.route('/api/documents', methods=['GET'])
def get_documents():
    """Get list of indexed documents from Memgraph"""
    try:
        from gqlalchemy import Memgraph

        memgraph = Memgraph(
            host=os.getenv('MEMGRAPH_HOST', '46.224.4.188'),
            port=int(os.getenv('MEMGRAPH_PORT', 7687))
        )

        # Query documents
        results = list(memgraph.execute_and_fetch("""
            MATCH (cao:CAO)-[:CONTAINS_ARTICLE]->(article:Article)
            WITH cao.name as cao, COUNT(article) as article_count
            RETURN cao, article_count
            ORDER BY cao
        """))

        documents = []
        for r in results:
            documents.append({
                'cao': r['cao'],
                'article_count': r['article_count'],
                'status': 'indexed'
            })

        return jsonify({'documents': documents})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@upload_bp.route('/api/documents/list', methods=['GET'])
def get_documents_list():
    """Get list of indexed documents for Super Admin dashboard"""
    try:
        from gqlalchemy import Memgraph
        from datetime import datetime
        import sys
        print(f"DEBUG: Starting get_documents_list()", file=sys.stderr, flush=True)

        memgraph = Memgraph(
            host=os.getenv('MEMGRAPH_HOST', '46.224.4.188'),
            port=int(os.getenv('MEMGRAPH_PORT', 7687))
        )
        print(f"DEBUG: Memgraph connected", file=sys.stderr, flush=True)

        # Query all CAO documents with their article counts
        results = list(memgraph.execute_and_fetch("""
            MATCH (cao:CAO)
            WITH cao.name as cao_name, cao
            OPTIONAL MATCH (cao)-[:CONTAINS_ARTICLE]->(article:Article)
            RETURN cao_name, COUNT(article) as article_count
            ORDER BY cao_name
        """))
        print(f"DEBUG: Query returned {len(results)} results", file=sys.stderr, flush=True)

        documents = []
        total_articles = 0

        for idx, r in enumerate(results):
            article_count = r['article_count'] if r['article_count'] else 0
            total_articles += article_count
            documents.append({
                'id': f'doc_{idx+1}',
                'cao_name': r['cao_name'],
                'status': 'indexed',
                'article_count': article_count,
                'upload_date': datetime.now().isoformat()
            })
            print(f"DEBUG: Added document {idx+1}: {r['cao_name']}", file=sys.stderr, flush=True)

        print(f"DEBUG: Returning {len(documents)} documents", file=sys.stderr, flush=True)
        return jsonify({
            'documents': documents,
            'total': len(documents),
            'total_articles': total_articles
        })
    except Exception as e:
        print(f"DEBUG: Error in get_documents_list: {str(e)}", file=sys.stderr, flush=True)
        import traceback
        print(traceback.format_exc(), file=sys.stderr, flush=True)
        return jsonify({'error': str(e)}), 500


@upload_bp.route('/api/documents/<old_cao_name>/rename', methods=['PUT'])
def rename_document(old_cao_name):
    """Rename a CAO document in Memgraph"""
    try:
        from gqlalchemy import Memgraph

        data = request.get_json()
        new_cao_name = data.get('new_name', '').strip()

        if not new_cao_name:
            return jsonify({'error': 'New name is required'}), 400

        memgraph = Memgraph(
            host=os.getenv('MEMGRAPH_HOST', '46.224.4.188'),
            port=int(os.getenv('MEMGRAPH_PORT', 7687))
        )

        # Update the CAO node with new name
        result = list(memgraph.execute_and_fetch("""
            MATCH (cao:CAO {name: $old_name})
            SET cao.name = $new_name
            RETURN cao.name as updated_name
        """, {'old_name': old_cao_name, 'new_name': new_cao_name}))

        if not result:
            return jsonify({'error': 'CAO not found'}), 404

        return jsonify({
            'message': 'CAO renamed successfully',
            'old_name': old_cao_name,
            'new_name': new_cao_name
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@upload_bp.route('/api/documents/<doc_id>', methods=['DELETE'])
def delete_document(doc_id):
    """Delete a CAO document from Memgraph"""
    try:
        from gqlalchemy import Memgraph

        memgraph = Memgraph(
            host=os.getenv('MEMGRAPH_HOST', '46.224.4.188'),
            port=int(os.getenv('MEMGRAPH_PORT', 7687))
        )

        # Get the CAO name from doc_id (format: doc_1, doc_2, etc.)
        # We need to query first to get the actual CAO name to delete
        all_caos = list(memgraph.execute_and_fetch("""
            MATCH (cao:CAO)
            OPTIONAL MATCH (cao)-[:CONTAINS_ARTICLE]->(article:Article)
            RETURN cao.name as cao_name
            ORDER BY cao.name
        """))

        # The doc_id is a sequential number (1, 2, 3...)
        doc_index = int(doc_id.replace('doc_', '')) - 1

        if doc_index < 0 or doc_index >= len(all_caos):
            return jsonify({'error': 'Document not found'}), 404

        cao_to_delete = all_caos[doc_index]['cao_name']

        # Delete the CAO node and all its related articles
        result = list(memgraph.execute_and_fetch("""
            MATCH (cao:CAO {name: $cao_name})
            DETACH DELETE cao
            RETURN 1
        """, {'cao_name': cao_to_delete}))

        if not result:
            return jsonify({'error': 'Document not found in database'}), 404

        return jsonify({
            'status': 'success',
            'message': f'Document "{cao_to_delete}" deleted successfully'
        }), 200

    except ValueError:
        return jsonify({'error': 'Invalid document ID format'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Background processing
def _process_documents_async(file_paths):
    """Process documents in background"""
    global upload_status

    try:
        # Import document importer
        import sys
        sys.path.insert(0, '/var/www/lexi')
        from document_importer import parse_document, generate_embeddings, import_to_memgraph

        from gqlalchemy import Memgraph

        memgraph = Memgraph(
            host=os.getenv('MEMGRAPH_HOST', '46.224.4.188'),
            port=int(os.getenv('MEMGRAPH_PORT', 7687))
        )

        upload_status['status'] = 'processing'
        total_imported = 0

        for idx, file_path in enumerate(file_paths):
            upload_status['current_file'] = os.path.basename(file_path)
            upload_status['progress'] = int((idx / len(file_paths)) * 50)  # 0-50% for parsing

            try:
                # Parse document
                cao_name, chunks = parse_document(file_path)
                upload_status['messages'].append(
                    f"📖 {cao_name}: {len(chunks)} chunks"
                )

                if not chunks:
                    upload_status['messages'].append(
                        f"⚠️  {os.path.basename(file_path)}: No content extracted"
                    )
                    continue

                # Generate embeddings
                upload_status['progress'] = int((idx / len(file_paths)) * 75)  # 50-75% for embeddings
                upload_status['messages'].append(f"⏳ Generating embeddings...")

                embeddings_data = generate_embeddings(chunks)
                upload_status['messages'].append(
                    f"✓ {len(embeddings_data)} embeddings generated"
                )

                # Import to Memgraph
                upload_status['progress'] = int((idx / len(file_paths)) * 90)  # 75-90% for import
                imported = import_to_memgraph(memgraph, cao_name, embeddings_data)
                total_imported += imported

                upload_status['messages'].append(
                    f"✅ {cao_name}: {imported} articles indexed"
                )
                upload_status['processed_files'] += 1

            except Exception as e:
                upload_status['messages'].append(
                    f"❌ Error processing {os.path.basename(file_path)}: {str(e)}"
                )
                upload_status['error'] = str(e)

        # Complete
        upload_status['status'] = 'complete'
        upload_status['progress'] = 100
        upload_status['imported_count'] = total_imported
        upload_status['messages'].append(
            f"\n✨ COMPLETE! {total_imported} total articles indexed"
        )

    except Exception as e:
        upload_status['status'] = 'error'
        upload_status['error'] = str(e)
        upload_status['messages'].append(f"❌ Fatal error: {str(e)}")
        import traceback
        upload_status['messages'].append(traceback.format_exc())


# Register blueprint with app
def register_upload_routes(app):
    """Call this from main.py"""
    app.register_blueprint(upload_bp)

    # CSRF exempt for file upload endpoints (multipart/form-data)
    try:
        from flask_wtf.csrf import csrf
        csrf.exempt(upload_bp)
    except:
        # If csrf not available, continue without exemption
        pass
