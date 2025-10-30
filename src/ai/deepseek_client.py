"""DeepSeek client - Minimal working version"""
import httpx
import json
import os
import logging

logger = logging.getLogger(__name__)

class DeepSeekClient:
    def __init__(self):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        self.base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
        self.client = httpx.AsyncClient(timeout=120.0)

    async def semantic_chunk(self, article_text, article_number, cao_name):
        """Chunk article text semantically"""
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")

        prompt = f"""Verdeel deze CAO tekst in logische chunks.
CAO: {cao_name}, Artikel: {article_number}

Tekst: {article_text}

Geef JSON: {{"chunks": [{{"text": "...", "reasoning": "..."}}]}}"""

        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}
            }
        )
        response.raise_for_status()
        result = response.json()
        return json.loads(result['choices'][0]['message']['content'])['chunks']

    async def close(self):
        await self.client.aclose()
