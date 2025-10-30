"""Flask blueprint for CAO processing pipeline API endpoints"""
import asyncio
import logging
from flask import Blueprint, request, jsonify, current_app
from uuid import uuid4
import os

logger = logging.getLogger(__name__)

cao_bp = Blueprint('cao', __name__, url_prefix='/api/cao')

@cao_bp.route('/process', methods=['POST'])
def process_cao_document():
    """
    Process CAO document through pipeline

    Expected request:
    {
        "document_id": "uuid (optional)",
        "cao_name": "CAO Name",
        "file_path": "/path/to/file"
    }
    """
    try:
        data = request.get_json()

        if not data or 'cao_name' not in data or 'file_path' not in data:
            return jsonify({
                "error": "Missing required fields: cao_name, file_path"
            }), 400

        cao_name = data.get('cao_name')
        file_path = data.get('file_path')
        document_id = data.get('document_id', str(uuid4()))

        # Verify file exists
        if not os.path.exists(file_path):
            return jsonify({
                "error": f"File not found: {file_path}"
            }), 400

        # Get orchestrator from app context
        orchestrator = current_app.cao_orchestrator
        if not orchestrator:
            return jsonify({
                "error": "CAO pipeline not initialized"
            }), 500

        # Start async processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                orchestrator.process_cao_document(
                    file_path=file_path,
                    cao_name=cao_name,
                    document_id=document_id
                )
            )

            return jsonify({
                "success": True,
                "document_id": document_id,
                "result": result
            }), 200

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Error processing CAO document: {e}")
        return jsonify({
            "error": str(e)
        }), 500

@cao_bp.route('/status/<document_id>', methods=['GET'])
def get_cao_status(document_id):
    """Get processing status for a CAO document"""
    try:
        orchestrator = current_app.cao_orchestrator
        if not orchestrator:
            return jsonify({"error": "CAO pipeline not initialized"}), 500

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            status = loop.run_until_complete(
                orchestrator.get_pipeline_status(document_id)
            )
            return jsonify(status), 200
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Error getting CAO status: {e}")
        return jsonify({"error": str(e)}), 500

@cao_bp.route('/search', methods=['POST'])
def search_cao():
    """
    Semantic search across CAO documents using Voyage embeddings

    Expected request:
    {
        "query": "search text",
        "limit": 10,
        "cao_filter": "CAO Name (optional)"
    }
    """
    try:
        data = request.get_json()

        if not data or 'query' not in data:
            return jsonify({
                "error": "Missing required field: query"
            }), 400

        query = data.get('query')
        limit = data.get('limit', 10)
        cao_filter = data.get('cao_filter')

        # Get Voyage client
        voyage = current_app.voyage_client
        if not voyage:
            return jsonify({
                "error": "Vector search not available"
            }), 500

        # Generate embedding for query
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            query_embedding = loop.run_until_complete(
                voyage.embed_chunks([query])
            )

            # Search in database (would use pgvector similarity)
            # This is a placeholder - actual implementation would:
            # 1. Query PostgreSQL cao_chunks using vector similarity
            # 2. Return top-k results with metadata

            return jsonify({
                "results": [],
                "count": 0
            }), 200

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Error searching CAO: {e}")
        return jsonify({"error": str(e)}), 500
