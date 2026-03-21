"""
Vivioo Memory — Embedding Layer (Step 4)
Turns memory text into vectors using Ollama + nomic-embed-text.

All local — nothing leaves the machine.
"""

import json
import os
import subprocess
from typing import List, Optional

from privacy_filter import load_config

DEFAULT_MODEL = "nomic-embed-text"


def check_ollama() -> dict:
    """
    Check if Ollama is running and the embedding model is available.

    Returns:
        {
            "available": True/False,
            "model_ready": True/False,
            "model": "nomic-embed-text",
            "error": None or error message
        }
    """
    result = {
        "available": False,
        "model_ready": False,
        "model": DEFAULT_MODEL,
        "error": None,
    }

    try:
        # Check if Ollama is running
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            result["available"] = True

            # Check if our model is pulled
            models = [m.get("name", "") for m in data.get("models", [])]
            model_names = [m.split(":")[0] for m in models]
            if DEFAULT_MODEL in model_names or DEFAULT_MODEL in models:
                result["model_ready"] = True
            else:
                result["error"] = (
                    f"Model '{DEFAULT_MODEL}' not found. "
                    f"Run: ollama pull {DEFAULT_MODEL}"
                )
    except Exception as e:
        result["error"] = f"Ollama not available (optional). Keyword search will be used instead."

    return result


def embed_text(text: str, model: str = None) -> Optional[List[float]]:
    """
    Generate an embedding vector for a piece of text.

    Args:
        text: the text to embed
        model: embedding model (defaults to nomic-embed-text)

    Returns:
        List of floats (the embedding vector), or None if Ollama is unavailable
    """
    model = model or _get_model()

    try:
        import urllib.request
        payload = json.dumps({"model": model, "prompt": text}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data.get("embedding")
    except Exception:
        return None


def embed_batch(texts: List[str], model: str = None) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts.

    Args:
        texts: list of texts to embed
        model: embedding model

    Returns:
        List of embedding vectors (None for any that failed)
    """
    return [embed_text(text, model) for text in texts]


def _get_model() -> str:
    """Get the configured embedding model."""
    config = load_config()
    return config.get("defaults", {}).get("embedding_model", DEFAULT_MODEL)
