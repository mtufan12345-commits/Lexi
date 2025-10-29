#!/usr/bin/env python3
"""
Document Graph Builder for Lexi

Converts R1 analysis results into proper CAO/Artikel graph structure in Memgraph.

Pipeline:
1. Takes R1 analysis output (cao_metadata, artikelen, relaties)
2. Creates CAO node with metadata
3. Creates Artikel nodes for each article
4. Links articles to CAO
5. Creates REFERENCES relationships between related articles
6. Validates graph integrity
"""

import os
import json
from typing import Dict, List, Tuple, Optional
from gqlalchemy import Memgraph
import logging

logger = logging.getLogger(__name__)


class DocumentGraphBuilder:
    """
    Build proper graph structure from R1 analysis results.

    Transforms flat chunks into hierarchical: CAO → Artikel → Chunks
    """

    def __init__(self, memgraph_host: str = None, memgraph_port: int = None):
        """
        Initialize graph builder

        Args:
            memgraph_host: Memgraph host (defaults to env var)
            memgraph_port: Memgraph port (defaults to env var)
        """
        self.memgraph_host = memgraph_host or os.getenv('MEMGRAPH_HOST', '46.224.4.188')
        self.memgraph_port = memgraph_port or int(os.getenv('MEMGRAPH_PORT', 7687))

        try:
            self.memgraph = Memgraph(host=self.memgraph_host, port=self.memgraph_port)
            # Test connection
            list(self.memgraph.execute_and_fetch("RETURN 1"))
            logger.info(f"✓ Memgraph connected: {self.memgraph_host}:{self.memgraph_port}")
        except Exception as e:
            logger.error(f"❌ Memgraph connection failed: {e}")
            raise

    def build_cao_strukture_from_r1(
        self,
        document_id: int,
        document_name: str,
        cao_type: str,
        r1_analysis: dict,
        chunk_mappings: dict
    ) -> Tuple[bool, dict]:
        """
        Build graph structure from R1 analysis results

        Args:
            document_id: Database ID of the document
            document_name: Name of the document
            cao_type: Type of CAO (NBBU, ABU, etc.)
            r1_analysis: R1 analysis result with cao_metadata, artikelen, relaties
            chunk_mappings: Dict mapping article numbers to chunk IDs in database

        Returns:
            (success, result_dict)
            result_dict contains:
            {
                'success': bool,
                'cao_node_id': str,
                'articles_created': int,
                'relations_created': int,
                'chunks_linked': int,
                'errors': [str],
                'warnings': [str]
            }
        """
        result = {
            'success': True,
            'cao_node_id': None,
            'articles_created': 0,
            'relations_created': 0,
            'chunks_linked': 0,
            'errors': [],
            'warnings': []
        }

        try:
            # Step 1: Create or update CAO node
            cao_metadata = r1_analysis.get('cao_metadata', {})

            cao_name = cao_metadata.get('name', document_name)
            cao_type_val = cao_metadata.get('type', cao_type)
            cao_version = cao_metadata.get('version', '')
            cao_date = cao_metadata.get('effective_date', '')

            # Sanitize CAO name for use as node property
            cao_name_safe = cao_name.replace("'", "\\'")

            try:
                # Check if CAO exists
                existing = list(self.memgraph.execute_and_fetch(
                    f"MATCH (cao:CAO) WHERE cao.name = '{cao_name_safe}' RETURN cao"
                ))

                if existing:
                    # Update existing CAO
                    logger.info(f"Updating existing CAO: {cao_name}")
                    self.memgraph.execute_and_fetch(f"""
                        MATCH (cao:CAO) WHERE cao.name = '{cao_name_safe}'
                        SET cao.version = '{cao_version}',
                            cao.effective_date = '{cao_date}',
                            cao.cao_type = '{cao_type_val}',
                            cao.document_id = {document_id},
                            cao.description = '{cao_metadata.get("description", "").replace("'", "\\'")}'
                    """)
                    cao_node_id = cao_name
                else:
                    # Create new CAO node
                    logger.info(f"Creating new CAO: {cao_name}")
                    self.memgraph.execute_and_fetch(f"""
                        CREATE (cao:CAO {{
                            name: '{cao_name_safe}',
                            type: '{cao_type_val}',
                            version: '{cao_version}',
                            effective_date: '{cao_date}',
                            document_id: {document_id},
                            description: '{cao_metadata.get("description", "").replace("'", "\\'")}'
                        }})
                    """)
                    cao_node_id = cao_name

                result['cao_node_id'] = cao_node_id

            except Exception as e:
                error_msg = f"Failed to create/update CAO node: {e}"
                logger.error(f"❌ {error_msg}")
                result['errors'].append(error_msg)
                return False, result

            # Step 2: Create Article nodes
            artikelen = r1_analysis.get('artikelen', [])
            article_map = {}  # Map article_number -> cypher id for relationships

            for artikel in artikelen:
                article_number = artikel.get('article_number', 'UNKNOWN')
                article_title = artikel.get('title', 'No title')
                article_section = artikel.get('section', '')
                article_tags = artikel.get('tags', [])
                chunk_indices = artikel.get('chunk_indices', [])

                try:
                    article_number_safe = article_number.replace("'", "\\'")
                    article_title_safe = article_title.replace("'", "\\'")
                    article_section_safe = article_section.replace("'", "\\'")

                    # Sanitize tags - ensure they're all strings
                    sanitized_tags = []
                    for tag in article_tags:
                        if tag is not None:
                            sanitized_tags.append(str(tag).replace("'", "\\'"))
                    tags_cypher = json.dumps(sanitized_tags)

                    # Create Article node
                    create_artikel_cypher = f"""
                        MATCH (cao:CAO) WHERE cao.name = '{cao_name_safe}'
                        CREATE (artikel:Article {{
                            article_number: '{article_number_safe}',
                            title: '{article_title_safe}',
                            section: '{article_section_safe}',
                            tags: {tags_cypher},
                            cao: '{cao_name_safe}',
                            document_id: {document_id}
                        }})
                        CREATE (cao)-[:CONTAINS_ARTICLE]->(artikel)
                        RETURN artikel
                    """

                    # Debug: check for datetime in query
                    if 'datetime' in create_artikel_cypher.lower():
                        logger.warning(f"⚠️ DATETIME DETECTED IN CYPHER: {create_artikel_cypher[:200]}")

                    list(self.memgraph.execute_and_fetch(create_artikel_cypher))
                    article_map[article_number] = article_number_safe
                    result['articles_created'] += 1

                    # Link chunks to this article if we have chunk mappings
                    if chunk_indices and chunk_mappings:
                        for chunk_idx in chunk_indices:
                            chunk_id = chunk_mappings.get(chunk_idx)
                            if chunk_id:
                                try:
                                    link_cypher = f"""
                                        MATCH (artikel:Article)
                                        WHERE artikel.article_number = '{article_number_safe}'
                                              AND artikel.document_id = {document_id}
                                        MATCH (chunk {{id: {chunk_id}}})
                                        CREATE (artikel)-[:CONTAINS_CHUNK]->(chunk)
                                    """
                                    list(self.memgraph.execute_and_fetch(link_cypher))
                                    result['chunks_linked'] += 1
                                except Exception as e:
                                    logger.warning(f"Could not link chunk {chunk_id} to article {article_number}: {e}")

                except Exception as e:
                    error_msg = f"Failed to create article {article_number}: {e}"
                    logger.error(f"❌ {error_msg}")
                    result['errors'].append(error_msg)

            # Step 3: Create relationships between articles
            relaties = r1_analysis.get('relaties', [])

            for relatie in relaties:
                source_article = relatie.get('source_article')
                target_article = relatie.get('target_article')
                relation_type = relatie.get('relation_type', 'REFERENCES')
                description = relatie.get('description', '')

                if source_article and target_article:
                    if source_article in article_map and target_article in article_map:
                        try:
                            source_safe = article_map[source_article].replace("'", "\\'")
                            target_safe = article_map[target_article].replace("'", "\\'")
                            description_safe = description.replace("'", "\\'")

                            create_relation_cypher = f"""
                                MATCH (source:Article {{article_number: '{source_safe}', document_id: {document_id}}})
                                MATCH (target:Article {{article_number: '{target_safe}', document_id: {document_id}}})
                                CREATE (source)-[:{relation_type} {{
                                    description: '{description_safe}'
                                }}]->(target)
                            """

                            list(self.memgraph.execute_and_fetch(create_relation_cypher))
                            result['relations_created'] += 1

                        except Exception as e:
                            logger.warning(f"Failed to create relation {source_article} -> {target_article}: {e}")
                    else:
                        logger.warning(f"Article not found for relation: {source_article} or {target_article}")

            logger.info(f"✓ Graph structure complete: {result['articles_created']} articles, {result['relations_created']} relations")
            return True, result

        except Exception as e:
            logger.error(f"❌ Graph building failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
            return False, result

    def get_graph_statistics(self, document_id: int) -> dict:
        """
        Get statistics for a document's graph structure

        Args:
            document_id: Document ID to analyze

        Returns:
            {
                'cao_count': int,
                'article_count': int,
                'chunk_count': int,
                'relation_count': int,
                'caos': [{'name': str, 'articles': int}]
            }
        """
        try:
            results = list(self.memgraph.execute_and_fetch(f"""
                MATCH (cao:CAO {{document_id: {document_id}}})
                OPTIONAL MATCH (cao)-[:CONTAINS_ARTICLE]->(artikel:Article)
                OPTIONAL MATCH (artikel)-[:CONTAINS_CHUNK]->(chunk)
                OPTIONAL MATCH (artikel)-[rel:REFERENCES|DEPENDS_ON|APPLIES_TO]-(other:Article)
                RETURN
                    cao.name as cao_name,
                    COUNT(DISTINCT artikel) as article_count,
                    COUNT(DISTINCT chunk) as chunk_count,
                    COUNT(DISTINCT rel) as relation_count
            """))

            stats = {
                'cao_count': len(results),
                'article_count': sum(r.get('article_count', 0) for r in results),
                'chunk_count': sum(r.get('chunk_count', 0) for r in results),
                'relation_count': sum(r.get('relation_count', 0) for r in results),
                'caos': [
                    {'name': r['cao_name'], 'articles': r.get('article_count', 0)}
                    for r in results
                ]
            }

            logger.info(f"Graph stats for doc {document_id}: {stats}")
            return stats

        except Exception as e:
            logger.error(f"Failed to get graph statistics: {e}")
            return {
                'cao_count': 0,
                'article_count': 0,
                'chunk_count': 0,
                'relation_count': 0,
                'caos': []
            }

    def validate_graph_integrity(self, document_id: int) -> Tuple[bool, List[str]]:
        """
        Validate graph structure integrity

        Args:
            document_id: Document to validate

        Returns:
            (is_valid, warnings)
        """
        warnings = []

        try:
            # Check for orphaned articles (articles without CAO)
            orphaned = list(self.memgraph.execute_and_fetch(f"""
                MATCH (artikel:Article {{document_id: {document_id}}})
                WHERE NOT (artikel)<-[:CONTAINS_ARTICLE]-(:CAO)
                RETURN COUNT(artikel) as count
            """))

            if orphaned and orphaned[0].get('count', 0) > 0:
                warnings.append(f"Found {orphaned[0]['count']} orphaned articles")

            # Check for orphaned chunks (chunks without articles)
            orphaned_chunks = list(self.memgraph.execute_and_fetch(f"""
                MATCH (chunk {{document_id: {document_id}}})
                WHERE NOT (chunk)<-[:CONTAINS_CHUNK]-(:Article)
                RETURN COUNT(chunk) as count
            """))

            if orphaned_chunks and orphaned_chunks[0].get('count', 0) > 0:
                warnings.append(f"Found {orphaned_chunks[0]['count']} orphaned chunks")

            # Check for broken relationships
            broken_rels = list(self.memgraph.execute_and_fetch(f"""
                MATCH (artikel:Article {{document_id: {document_id}}})-[rel]->(other)
                WHERE NOT (other:Article {{document_id: {document_id}}})
                RETURN COUNT(rel) as count
            """))

            if broken_rels and broken_rels[0].get('count', 0) > 0:
                warnings.append(f"Found {broken_rels[0]['count']} broken relationships")

            is_valid = len(warnings) < 2
            return is_valid, warnings

        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False, [f"Validation error: {e}"]


# Global builder instance
_builder_instance = None


def get_graph_builder() -> DocumentGraphBuilder:
    """Get or create global graph builder instance"""
    global _builder_instance
    if _builder_instance is None:
        _builder_instance = DocumentGraphBuilder()
    return _builder_instance


if __name__ == "__main__":
    # Test graph builder
    import sys
    logging.basicConfig(level=logging.INFO)

    builder = get_graph_builder()

    # Test R1 analysis structure
    test_r1_result = {
        'success': True,
        'cao_metadata': {
            'name': 'Test CAO 2025',
            'type': 'NBBU',
            'version': '1.0',
            'effective_date': '2025-01-01',
            'sector': 'Testing',
            'description': 'Test CAO for validation'
        },
        'artikelen': [
            {
                'article_number': '1',
                'title': 'General Provisions',
                'section': 'Chapter 1',
                'tags': ['general', 'setup'],
                'chunk_indices': [0, 1, 2]
            },
            {
                'article_number': '2',
                'title': 'Wages',
                'section': 'Chapter 2',
                'tags': ['wages', 'compensation'],
                'chunk_indices': [3, 4, 5]
            }
        ],
        'relaties': [
            {
                'source_article': '1',
                'target_article': '2',
                'relation_type': 'REFERENCES',
                'description': 'Article 1 references Article 2 for wage details'
            }
        ],
        'validation': {
            'total_articles_estimated': 2,
            'coverage_percentage': 100.0,
            'warnings': []
        }
    }

    print("\n🧪 Testing DocumentGraphBuilder...")
    success, result = builder.build_cao_strukture_from_r1(
        document_id=999,
        document_name='Test CAO 2025',
        cao_type='NBBU',
        r1_analysis=test_r1_result,
        chunk_mappings={}
    )

    print(f"Build result: {result}")

    if success:
        stats = builder.get_graph_statistics(999)
        print(f"Graph statistics: {stats}")

        is_valid, warnings = builder.validate_graph_integrity(999)
        print(f"Integrity: valid={is_valid}, warnings={warnings}")
