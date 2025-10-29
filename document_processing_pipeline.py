#!/usr/bin/env python3
"""
Automatic Document Processing Pipeline for Lexi

Full end-to-end pipeline for document upload → processing → graph building

Pipeline Phases:
1. uploaded       - Document file saved
2. chunking       - Text parsing and chunking
3. embedding      - Generate embeddings for chunks
4. saving_chunks  - Save chunks to Memgraph
5. analyzing_structure - R1 analysis of document structure
6. building_graph - Create CAO/Artikel nodes and relationships
7. validating     - Validate graph integrity
8. complete       - Document fully processed

Status tracking:
- Real-time phase updates in database
- Error recovery with rollback support
- Detailed error logging and warnings
"""

import os
import sys
import json
import time
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, List

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import Lexi modules
sys.path.insert(0, '/var/www/lexi')

from models import db, Document
from services import get_r1_client
from document_graph_builder import get_graph_builder
from document_importer import parse_txt, generate_embeddings, import_to_memgraph


class DocumentProcessingPipeline:
    """
    Orchestrates automatic document processing through all phases.
    """

    def __init__(self):
        """Initialize pipeline with components"""
        self.r1_client = get_r1_client()
        self.graph_builder = get_graph_builder()

    def update_document_status(
        self,
        document_id: int,
        status: str,
        additional_data: dict = None
    ) -> bool:
        """
        Update document status in database

        Args:
            document_id: Document database ID
            status: New status (uploaded, chunking, embedding, etc.)
            additional_data: Additional fields to update

        Returns:
            Success boolean
        """
        try:
            doc = Document.query.get(document_id)
            if not doc:
                logger.error(f"Document {document_id} not found")
                return False

            doc.status = status

            if additional_data:
                for key, value in additional_data.items():
                    if hasattr(doc, key):
                        setattr(doc, key, value)

            db.session.commit()
            logger.info(f"✓ Document {document_id} status updated: {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update document status: {e}")
            db.session.rollback()
            return False

    def process_document_pipeline(
        self,
        document_id: int,
        file_path: str,
        document_name: str,
        cao_type: Optional[str] = None
    ) -> Dict:
        """
        Full automatic processing pipeline

        Args:
            document_id: Database ID of document
            file_path: Path to uploaded file
            document_name: Name of document
            cao_type: Type of CAO if known (NBBU, ABU, etc.)

        Returns:
            {
                'success': bool,
                'document_id': int,
                'phases_completed': [str],
                'final_status': str,
                'statistics': {
                    'total_chunks': int,
                    'graph_nodes': int,
                    'graph_relations': int,
                    'graph_articles': int
                },
                'r1_analysis': {...},
                'errors': [str],
                'warnings': [str],
                'total_time': float
            }
        """
        start_time = time.time()
        result = {
            'success': True,
            'document_id': document_id,
            'phases_completed': [],
            'final_status': 'complete',
            'statistics': {},
            'r1_analysis': None,
            'errors': [],
            'warnings': [],
            'total_time': 0
        }

        try:
            # Phase 1: Chunking
            logger.info(f"[PHASE 1] Chunking document {document_id}: {document_name}")
            self.update_document_status(document_id, 'chunking')

            try:
                # Parse file into chunks
                if file_path.endswith('.txt'):
                    chunks = parse_txt(file_path)
                else:
                    # Default to TXT handling
                    chunks = parse_txt(file_path)

                if not chunks:
                    error_msg = "No chunks extracted from document"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].append(error_msg)
                    result['final_status'] = 'error'
                    self.update_document_status(
                        document_id,
                        'error',
                        {
                            'error_message': error_msg,
                            'error_phase': 'chunking',
                            'completed_at': datetime.utcnow()
                        }
                    )
                    return result

                result['phases_completed'].append('chunking')
                logger.info(f"✓ Chunking complete: {len(chunks)} chunks")

            except Exception as e:
                error_msg = f"Chunking failed: {str(e)}"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                result['final_status'] = 'error'
                self.update_document_status(
                    document_id,
                    'error',
                    {
                        'error_message': error_msg,
                        'error_phase': 'chunking',
                        'completed_at': datetime.utcnow()
                    }
                )
                return result

            # Phase 2: Embedding
            logger.info(f"[PHASE 2] Generating embeddings for {len(chunks)} chunks")
            self.update_document_status(document_id, 'embedding')

            try:
                embeddings = generate_embeddings(chunks)
                if not embeddings:
                    error_msg = "Failed to generate embeddings"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].append(error_msg)
                    result['final_status'] = 'error'
                    self.update_document_status(
                        document_id,
                        'error',
                        {
                            'error_message': error_msg,
                            'error_phase': 'embedding',
                            'completed_at': datetime.utcnow()
                        }
                    )
                    return result

                result['phases_completed'].append('embedding')
                logger.info(f"✓ Embeddings complete: {len(embeddings)} embeddings")

            except Exception as e:
                error_msg = f"Embedding failed: {str(e)}"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                result['final_status'] = 'error'
                self.update_document_status(
                    document_id,
                    'error',
                    {
                        'error_message': error_msg,
                        'error_phase': 'embedding',
                        'completed_at': datetime.utcnow()
                    }
                )
                return result

            # Phase 3: Save chunks to Memgraph
            logger.info(f"[PHASE 3] Saving chunks to Memgraph")
            self.update_document_status(document_id, 'saving_chunks')

            try:
                chunk_mappings = import_to_memgraph(
                    chunks=chunks,
                    embeddings=embeddings,
                    document_name=document_name,
                    document_id=document_id,
                    cao_type=cao_type
                )

                if not chunk_mappings:
                    error_msg = "Failed to save chunks to Memgraph"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].append(error_msg)
                    result['final_status'] = 'error'
                    self.update_document_status(
                        document_id,
                        'error',
                        {
                            'error_message': error_msg,
                            'error_phase': 'saving_chunks',
                            'completed_at': datetime.utcnow()
                        }
                    )
                    return result

                result['phases_completed'].append('saving_chunks')
                result['statistics']['total_chunks'] = len(chunks)
                logger.info(f"✓ Chunks saved: {len(chunks)} chunks to Memgraph")

            except Exception as e:
                error_msg = f"Saving chunks failed: {str(e)}"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                result['final_status'] = 'error'
                self.update_document_status(
                    document_id,
                    'error',
                    {
                        'error_message': error_msg,
                        'error_phase': 'saving_chunks',
                        'completed_at': datetime.utcnow()
                    }
                )
                return result

            # Phase 4: R1 Structure Analysis
            logger.info(f"[PHASE 4] Analyzing document structure with R1")
            self.update_document_status(document_id, 'analyzing_structure')

            try:
                if not self.r1_client.enabled:
                    error_msg = "DeepSeek R1 client not enabled"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].append(error_msg)
                    result['final_status'] = 'error'
                    self.update_document_status(
                        document_id,
                        'error',
                        {
                            'error_message': error_msg,
                            'error_phase': 'analyzing_structure',
                            'completed_at': datetime.utcnow()
                        }
                    )
                    return result

                r1_analysis = self.r1_client.analyze_cao_structure(
                    chunks=chunks,
                    document_name=document_name,
                    cao_type=cao_type
                )

                if not r1_analysis.get('success'):
                    error_msg = f"R1 analysis failed: {r1_analysis.get('error', 'Unknown error')}"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].append(error_msg)
                    result['final_status'] = 'error'
                    self.update_document_status(
                        document_id,
                        'error',
                        {
                            'error_message': error_msg,
                            'error_phase': 'analyzing_structure',
                            'completed_at': datetime.utcnow()
                        }
                    )
                    return result

                result['phases_completed'].append('analyzing_structure')
                result['r1_analysis'] = r1_analysis
                logger.info(f"✓ R1 Analysis complete: {len(r1_analysis.get('artikelen', []))} articles identified")

            except Exception as e:
                error_msg = f"R1 analysis failed: {str(e)}"
                logger.error(f"❌ {error_msg}")
                traceback.print_exc()
                result['errors'].append(error_msg)
                result['final_status'] = 'error'
                self.update_document_status(
                    document_id,
                    'error',
                    {
                        'error_message': error_msg,
                        'error_phase': 'analyzing_structure',
                        'completed_at': datetime.utcnow()
                    }
                )
                return result

            # Phase 5: Build Graph Structure
            logger.info(f"[PHASE 5] Building graph structure")
            self.update_document_status(document_id, 'building_graph')

            try:
                success, graph_result = self.graph_builder.build_cao_strukture_from_r1(
                    document_id=document_id,
                    document_name=document_name,
                    cao_type=cao_type,
                    r1_analysis=r1_analysis,
                    chunk_mappings=chunk_mappings
                )

                if not success:
                    error_msg = f"Graph building failed: {', '.join(graph_result.get('errors', []))}"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].extend(graph_result.get('errors', []))
                    result['final_status'] = 'error'
                    self.update_document_status(
                        document_id,
                        'error',
                        {
                            'error_message': error_msg,
                            'error_phase': 'building_graph',
                            'completed_at': datetime.utcnow()
                        }
                    )
                    return result

                result['phases_completed'].append('building_graph')
                result['statistics'].update({
                    'graph_nodes': graph_result.get('articles_created', 0),
                    'graph_relations': graph_result.get('relations_created', 0),
                    'graph_articles': graph_result.get('articles_created', 0)
                })

                if graph_result.get('warnings'):
                    result['warnings'].extend(graph_result['warnings'])

                logger.info(f"✓ Graph building complete: {graph_result.get('articles_created', 0)} articles, {graph_result.get('relations_created', 0)} relations")

            except Exception as e:
                error_msg = f"Graph building failed: {str(e)}"
                logger.error(f"❌ {error_msg}")
                traceback.print_exc()
                result['errors'].append(error_msg)
                result['final_status'] = 'error'
                self.update_document_status(
                    document_id,
                    'error',
                    {
                        'error_message': error_msg,
                        'error_phase': 'building_graph',
                        'completed_at': datetime.utcnow()
                    }
                )
                return result

            # Phase 6: Validation
            logger.info(f"[PHASE 6] Validating graph integrity")
            self.update_document_status(document_id, 'validating')

            try:
                is_valid, validation_warnings = self.graph_builder.validate_graph_integrity(document_id)

                if validation_warnings:
                    result['warnings'].extend(validation_warnings)

                if not is_valid:
                    result['final_status'] = 'complete_with_warnings'
                    logger.warning(f"⚠️  Validation warnings: {validation_warnings}")
                else:
                    result['final_status'] = 'complete'

                result['phases_completed'].append('validating')
                logger.info(f"✓ Validation complete: {len(validation_warnings)} warnings")

            except Exception as e:
                error_msg = f"Validation failed: {str(e)}"
                logger.error(f"❌ {error_msg}")
                result['warnings'].append(error_msg)
                result['final_status'] = 'complete_with_warnings'

            # Phase 7: Complete
            logger.info(f"[PHASE 7] Marking document as complete")
            result['total_time'] = time.time() - start_time

            # Save R1 analysis to database
            r1_analysis_json = json.dumps(r1_analysis, ensure_ascii=False, default=str)

            self.update_document_status(
                document_id,
                result['final_status'],
                {
                    'total_chunks': result['statistics'].get('total_chunks', 0),
                    'graph_nodes': result['statistics'].get('graph_nodes', 0),
                    'graph_relations': result['statistics'].get('graph_relations', 0),
                    'graph_articles': result['statistics'].get('graph_articles', 0),
                    'r1_analysis': r1_analysis_json,
                    'r1_tokens_used': r1_analysis.get('tokens_used', 0),
                    'validation_passed': result['final_status'] == 'complete',
                    'validation_warnings': json.dumps(result['warnings'], ensure_ascii=False),
                    'completed_at': datetime.utcnow()
                }
            )

            logger.info(f"✅ Document {document_id} processing complete!")
            logger.info(f"   Total time: {result['total_time']:.1f}s")
            logger.info(f"   Phases: {', '.join(result['phases_completed'])}")
            logger.info(f"   Chunks: {result['statistics'].get('total_chunks', 0)}")
            logger.info(f"   Articles: {result['statistics'].get('graph_articles', 0)}")
            logger.info(f"   Relations: {result['statistics'].get('graph_relations', 0)}")
            logger.info(f"   Final status: {result['final_status']}")

            return result

        except Exception as e:
            logger.error(f"❌ Pipeline failed unexpectedly: {e}")
            traceback.print_exc()
            result['success'] = False
            result['final_status'] = 'error'
            result['errors'].append(f"Unexpected error: {str(e)}")
            result['total_time'] = time.time() - start_time

            # Save error to database
            self.update_document_status(
                document_id,
                'error',
                {
                    'error_message': str(e),
                    'error_phase': 'unknown',
                    'completed_at': datetime.utcnow()
                }
            )

            return result


# Global pipeline instance
_pipeline_instance = None


def get_processing_pipeline() -> DocumentProcessingPipeline:
    """Get or create global processing pipeline"""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = DocumentProcessingPipeline()
    return _pipeline_instance
