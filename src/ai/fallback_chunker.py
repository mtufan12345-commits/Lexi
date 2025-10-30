"""Fallback chunking when DeepSeek unavailable"""
import re

def sentence_chunking(text, max_sentences=8):
    """Simple sentence-based chunking"""
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    for i in range(0, len(sentences), max_sentences):
        chunk_sentences = sentences[i:i + max_sentences]
        chunk_text = ' '.join(chunk_sentences)

        chunks.append({
            'index': len(chunks),
            'text': chunk_text,
            'token_count': len(chunk_text.split()),
            'reasoning': f'Fallback: sentences {i} to {i+len(chunk_sentences)}'
        })

    return chunks
