"""
Vivioo Memory — TF-IDF Search (v0.5)
Zero-dependency text search using Term Frequency-Inverse Document Frequency.

This replaces the need for ChromaDB or Ollama for basic search.
When neither is available, TF-IDF provides better results than
simple keyword matching — it understands which words are meaningful
(rare words matter more than common ones).

No external dependencies. Pure Python. Works everywhere.

Usage:
    from tfidf import TFIDFIndex

    index = TFIDFIndex()
    index.add("doc1", "The agent prefers story-first marketing campaigns")
    index.add("doc2", "Deploy the server to Vercel with environment variables")
    index.add("doc3", "Marketing budget is $50K for Q2")

    results = index.search("marketing strategy", top_k=2)
    # → [("doc1", 0.82), ("doc3", 0.45)]
"""

import math
import re
from typing import List, Tuple, Dict, Optional


# Common English stop words — filtered to reduce noise
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "about", "than",
    "after", "before", "between", "through", "during", "and", "but",
    "or", "nor", "not", "so", "yet", "both", "either", "neither",
    "it", "its", "i", "me", "my", "we", "our", "you", "your", "he",
    "she", "they", "them", "his", "her", "this", "that", "what", "how",
    "which", "who", "whom", "when", "where", "why", "all", "each",
    "every", "any", "few", "more", "most", "other", "some", "such",
    "no", "only", "own", "same", "too", "very", "just", "if", "then",
})


def _tokenize(text: str) -> List[str]:
    """
    Tokenize text into lowercase words, stripping punctuation.
    Applies basic stemming to improve recall.
    """
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [_stem(w) for w in words if w not in _STOP_WORDS and len(w) >= 2]


def _stem(word: str) -> str:
    """
    Simple suffix-stripping stemmer. No dependencies.
    Reduces words to root form: 'launching' → 'launch'.
    """
    if len(word) <= 3:
        return word
    for suffix in ("ation", "ting", "ment", "ness", "able", "ible", "ally",
                   "ful", "less", "ing", "ied", "ies", "ion", "ous",
                   "ive", "ers", "est", "ely", "ity",
                   "ly", "ed", "er", "al", "en", "es", "ty", "ry", "or", "ar",
                   "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[:-len(suffix)]
    return word


class TFIDFIndex:
    """
    In-memory TF-IDF index for document search.

    Supports incremental adds and efficient cosine-similarity search.
    No external dependencies — pure Python implementation.
    """

    def __init__(self):
        self._docs: Dict[str, List[str]] = {}    # doc_id → tokens
        self._df: Dict[str, int] = {}             # term → doc count
        self._doc_count: int = 0

    def add(self, doc_id: str, text: str) -> None:
        """Add a document to the index."""
        tokens = _tokenize(text)
        if not tokens:
            return

        # Remove old version if updating
        if doc_id in self._docs:
            self._remove_df(doc_id)

        self._docs[doc_id] = tokens
        self._doc_count = len(self._docs)

        # Update document frequency
        unique_terms = set(tokens)
        for term in unique_terms:
            self._df[term] = self._df.get(term, 0) + 1

    def remove(self, doc_id: str) -> bool:
        """Remove a document from the index."""
        if doc_id not in self._docs:
            return False
        self._remove_df(doc_id)
        del self._docs[doc_id]
        self._doc_count = len(self._docs)
        return True

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Search the index with a query.

        Args:
            query: search text
            top_k: max results to return

        Returns:
            List of (doc_id, score) tuples, sorted by relevance.
            Scores are cosine similarity (0-1).
        """
        if not self._docs:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_tfidf = self._compute_tfidf(query_tokens)
        if not query_tfidf:
            return []

        scores = []
        for doc_id, doc_tokens in self._docs.items():
            doc_tfidf = self._compute_tfidf(doc_tokens)
            sim = self._cosine_similarity(query_tfidf, doc_tfidf)
            if sim > 0:
                scores.append((doc_id, round(sim, 4)))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _compute_tfidf(self, tokens: List[str]) -> Dict[str, float]:
        """Compute TF-IDF vector for a token list."""
        if not tokens:
            return {}

        # Term frequency (normalized)
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        max_tf = max(tf.values())
        for t in tf:
            tf[t] = 0.5 + 0.5 * (tf[t] / max_tf)  # augmented TF

        # IDF
        tfidf = {}
        n = max(self._doc_count, 1)
        for term, freq in tf.items():
            df = self._df.get(term, 0)
            idf = math.log((n + 1) / (df + 1)) + 1  # smoothed IDF
            tfidf[term] = freq * idf

        return tfidf

    def _cosine_similarity(self, a: Dict[str, float],
                           b: Dict[str, float]) -> float:
        """Cosine similarity between two sparse TF-IDF vectors."""
        # Dot product (only shared terms contribute)
        shared = set(a.keys()) & set(b.keys())
        if not shared:
            return 0.0

        dot = sum(a[t] * b[t] for t in shared)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    def _remove_df(self, doc_id: str) -> None:
        """Remove a document's contribution to document frequency."""
        if doc_id not in self._docs:
            return
        unique_terms = set(self._docs[doc_id])
        for term in unique_terms:
            if term in self._df:
                self._df[term] -= 1
                if self._df[term] <= 0:
                    del self._df[term]

    @property
    def doc_count(self) -> int:
        """Number of documents in the index."""
        return self._doc_count

    def clear(self) -> None:
        """Clear the entire index."""
        self._docs.clear()
        self._df.clear()
        self._doc_count = 0
