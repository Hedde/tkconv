from typing import Dict, List

# Import the actual embedding generation function
from .embedding_generator import generate_embedding_vector

# Global cache for embeddings, keyed by request_id
# For a production app with multiple workers, use a shared cache (e.g., Redis)
embedding_cache_by_request_id: Dict[str, List[float]] = {}


async def get_or_create_embedding(query_text: str, request_id: str) -> List[float]:
    """Generates an embedding for the query text or retrieves it from cache if available for this request_id."""
    if not query_text:
        return []

    cached_vector = retrieve_embedding(request_id)
    if cached_vector:
        return cached_vector

    print(
        f"Embedding cache MISS for request_id: {request_id}. Generating embedding for query: '{query_text[:50]}...'"
    )
    vector = await generate_embedding_vector(
        query_text
    )  # Use generate_embedding_vector
    store_embedding(request_id, vector)
    return vector


def store_embedding(request_id: str, vector: List[float]):
    print(f"Storing embedding in cache for request_id: {request_id}")
    embedding_cache_by_request_id[request_id] = vector


def retrieve_embedding(request_id: str) -> List[float] | None:
    print(f"Attempting to retrieve embedding from cache for request_id: {request_id}")
    vector = embedding_cache_by_request_id.get(request_id)
    if vector:
        print(f"Cache HIT for request_id: {request_id}")
    else:
        print(f"Cache MISS for request_id: {request_id}")
    return vector


def clear_embedding(request_id: str):
    if request_id in embedding_cache_by_request_id:
        print(f"Clearing embedding from cache for request_id: {request_id}")
        del embedding_cache_by_request_id[request_id]
    else:
        print(f"No embedding found in cache to clear for request_id: {request_id}")
