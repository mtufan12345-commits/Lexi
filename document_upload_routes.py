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


@upload_bp.route('/api/documents/<int:document_id>/status', methods=['GET'])
def get_document_status(document_id):
    """
    Get individual document processing status

    Returns:
    {
        'document_id': int,
        'filename': str,
        'status': str,  # uploaded, chunking, embedding, saving_chunks, analyzing_structure, building_graph, validating, complete, error
        'progress': {
            'current_phase': str,
            'phases_completed': [str],
            'total_phases': 7
        },
        'statistics': {
            'total_chunks': int,
            'graph_nodes': int,
            'graph_relations': int,
            'graph_articles': int
        },
        'error': str|null,
        'warnings': [str],
        'completed_at': str|null
    }
    """
    try:
        import sys
        sys.path.insert(0, '/var/www/lexi')
        from models import db, Document

        doc = Document.query.get(document_id)
        if not doc:
            return jsonify({'error': 'Document not found'}), 404

        # Determine progress
        phase_order = [
            'uploaded',
            'chunking',
            'embedding',
            'saving_chunks',
            'analyzing_structure',
            'building_graph',
            'validating',
            'complete',
            'error'
        ]

        current_phase_idx = phase_order.index(doc.status) if doc.status in phase_order else 0
        phases_completed = phase_order[:current_phase_idx]

        # Parse JSON fields
        r1_analysis = None
        if doc.r1_analysis:
            try:
                r1_analysis = json.loads(doc.r1_analysis)
            except:
                pass

        validation_warnings = []
        if doc.validation_warnings:
            try:
                validation_warnings = json.loads(doc.validation_warnings)
            except:
                validation_warnings = [doc.validation_warnings]

        return jsonify({
            'document_id': doc.id,
            'filename': doc.filename,
            'status': doc.status,
            'progress': {
                'current_phase': doc.status,
                'phases_completed': phases_completed,
                'total_phases': 7
            },
            'statistics': {
                'total_chunks': doc.total_chunks or 0,
                'graph_nodes': doc.graph_nodes or 0,
                'graph_relations': doc.graph_relations or 0,
                'graph_articles': doc.graph_articles or 0
            },
            'r1_analysis': r1_analysis,
            'r1_tokens_used': doc.r1_tokens_used or 0,
            'error': doc.error_message,
            'error_phase': doc.error_phase,
            'warnings': validation_warnings,
            'completed_at': doc.completed_at.isoformat() if doc.completed_at else None
        })

    except Exception as e:
        import traceback
        print(f"Error getting document status: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


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


# Background processing - Automatic Pipeline Integration
def _process_documents_async(file_paths):
    """
    Process documents using automatic pipeline
    Integrates with:
    - DocumentProcessingPipeline (orchestration)
    - DeepSeekR1Client (structure analysis)
    - DocumentGraphBuilder (graph creation)
    """
    global upload_status

    try:
        import sys
        sys.path.insert(0, '/var/www/lexi')

        from models import db, Document
        from document_processing_pipeline import get_processing_pipeline

        pipeline = get_processing_pipeline()
        upload_status['status'] = 'processing'
        total_imported = 0

        for idx, file_path in enumerate(file_paths):
            filename = os.path.basename(file_path)
            upload_status['current_file'] = filename
            upload_status['progress'] = int((idx / len(file_paths)) * 100)

            try:
                # Create document record in database
                upload_status['messages'].append(f"📁 Creating document record: {filename}")

                doc = Document(
                    filename=filename,
                    cao_type='UNKNOWN',
                    uploaded_by=1,  # System/Super Admin
                    status='uploaded'
                )
                db.session.add(doc)
                db.session.commit()
                document_id = doc.id

                upload_status['messages'].append(f"✓ Document created (ID: {document_id})")

                # Run full automatic pipeline
                upload_status['messages'].append(f"🚀 Starting automatic processing pipeline...")

                result = pipeline.process_document_pipeline(
                    document_id=document_id,
                    file_path=file_path,
                    document_name=filename,
                    cao_type='UNKNOWN'
                )

                if result['success']:
                    stats = result.get('statistics', {})
                    upload_status['messages'].append(
                        f"✅ {filename}: {stats.get('total_chunks', 0)} chunks, "
                        f"{stats.get('graph_articles', 0)} articles, "
                        f"{stats.get('graph_relations', 0)} relations"
                    )
                    total_imported += stats.get('graph_articles', 0)
                    upload_status['processed_files'] += 1
                else:
                    error_msg = result.get('errors', ['Unknown error'])[0]
                    upload_status['messages'].append(
                        f"❌ {filename}: {error_msg}"
                    )
                    upload_status['error'] = error_msg

                # Show processing time
                processing_time = result.get('total_time', 0)
                upload_status['messages'].append(
                    f"⏱️  Processing time: {processing_time:.1f}s"
                )

            except Exception as e:
                upload_status['messages'].append(
                    f"❌ Error processing {filename}: {str(e)}"
                )
                upload_status['error'] = str(e)
                import traceback
                print(traceback.format_exc())

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
