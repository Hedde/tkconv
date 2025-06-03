from typing import List

from sentence_transformers import SentenceTransformer

# --- Model Singleton Pattern ---
# Lazily load the model upon first use and keep it in memory.
_model_instance: SentenceTransformer | None = None
_model_name = "all-MiniLM-L6-v2"  # Produces 384-dim embeddings


def _get_model() -> SentenceTransformer:
    global _model_instance
    if _model_instance is None:
        print(
            f"Loading SentenceTransformer model for embedding generation: {_model_name}"
        )
        _model_instance = SentenceTransformer(_model_name)
        print(f"SentenceTransformer model '{_model_name}' loaded.")
    return _model_instance


async def generate_embedding_vector(query_text: str) -> List[float]:
    """Generates a 384-dimensional dense vector embedding for the given text query."""
    if not query_text:
        return []

    model = _get_model()
    # SentenceTransformer.encode can be a blocking CPU-bound operation.
    # For async context, consider running in a thread pool if it becomes a bottleneck.
    # For now, direct call for simplicity, assuming it's acceptable for current workload.
    embedding = model.encode(query_text)
    return embedding.tolist()  # Convert numpy array to list
