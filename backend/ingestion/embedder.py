"""Embedding function for ChromaDB using sentence-transformers."""

import logging
from typing import cast

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

logger = logging.getLogger(__name__)

# Lazy-loaded model instance
_model = None


def _get_model(model_name: str = "all-mpnet-base-v2"):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", model_name)
        _model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded")
    return _model


class LocalEmbeddingFunction(EmbeddingFunction[Documents]):
    """Implements Chroma's EmbeddingFunction protocol using a local
    sentence-transformer model.  Passed to Chroma collection so
    embedding happens automatically on add/query.
    """

    def __init__(self, model_name: str = "all-mpnet-base-v2"):
        self._model_name = model_name

    def __call__(self, input: Documents) -> Embeddings:
        model = _get_model(self._model_name)
        embeddings = model.encode(input, show_progress_bar=False)
        return cast(Embeddings, embeddings.tolist())
