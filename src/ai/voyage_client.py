"""Voyage AI client for legal embeddings"""
import voyageai
import os
from typing import List

class VoyageClient:
    def __init__(self):
        # Try both key names for compatibility
        self.api_key = os.getenv('VOYAGE_API_KEY') or os.getenv('VOYAGE_AI_API_KEY')
        self.model = os.getenv('VOYAGE_AI_MODEL', 'voyage-law-2')
        if self.api_key:
            self.client = voyageai.Client(api_key=self.api_key)

    def create_embedding_input(self, chunk_text, analysis):
        """Enrich chunk with analysis for better embeddings"""
        themes = ', '.join(analysis.get('themes', []))
        summary = analysis.get('summary', '')

        return f"""THEMA: {themes}
CONTEXT: {summary}

{chunk_text}"""

    async def embed_chunks(self, texts, input_type="document"):
        """Generate embeddings for multiple chunks"""
        if not self.api_key:
            raise ValueError("VOYAGE_API_KEY not set")

        result = self.client.embed(
            texts=texts,
            model=self.model,
            input_type=input_type
        )
        return result.embeddings
