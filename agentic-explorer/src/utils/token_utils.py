"""
Token counting utilities for managing context window size in agents.
"""

import logging
from typing import Any, Dict, List, Optional

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    logging.warning("tiktoken not available, using rough token estimation")


def get_encoder_for_model(model_name: str = "gpt-4o-mini"):
    """Get tiktoken encoder for the specified model."""
    if not TIKTOKEN_AVAILABLE:
        return None

    try:
        return tiktoken.encoding_for_model(model_name)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, encoder=None) -> int:
    """Count tokens in text. Falls back to word count estimation if tiktoken unavailable."""
    if not text:
        return 0

    if encoder and TIKTOKEN_AVAILABLE:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass

    # Fallback: rough estimation (1 token ≈ 0.75 words for English/Dutch)
    return int(len(text.split()) * 1.33)


def estimate_document_tokens(doc: Dict[str, Any], encoder=None) -> int:
    """Estimate token count for a document, checking content, summary, and title."""
    total_tokens = 0

    # Count tokens in different fields
    for field in ["content", "summary", "title"]:
        if field in doc and doc[field]:
            total_tokens += count_tokens(str(doc[field]), encoder)

    # Add some overhead for metadata
    total_tokens += 50

    return total_tokens


def select_documents_within_budget(
    documents: List[Dict[str, Any]],
    max_tokens: int = 4000,
    reserved_tokens: int = 1000,
    encoder=None,
) -> List[Dict[str, Any]]:
    """
    Select documents that fit within the token budget.
    Prioritizes by score (if available) and tries to include as many relevant docs as possible.
    """
    if not documents:
        return []

    budget = max_tokens - reserved_tokens
    selected = []
    used_tokens = 0

    # Sort by score (descending) if available
    sorted_docs = sorted(documents, key=lambda x: x.get("score", 0), reverse=True)

    for doc in sorted_docs:
        doc_tokens = estimate_document_tokens(doc, encoder)

        if used_tokens + doc_tokens <= budget:
            selected.append(doc)
            used_tokens += doc_tokens
            logging.debug(
                f"Selected doc {doc.get('id', 'unknown')} ({doc_tokens} tokens)"
            )
        else:
            logging.debug(
                f"Skipped doc {doc.get('id', 'unknown')} ({doc_tokens} tokens) - would exceed budget"
            )

    logging.info(
        f"Selected {len(selected)}/{len(documents)} documents using {used_tokens}/{budget} tokens"
    )
    return selected


def trim_document_content(
    doc: Dict[str, Any], max_tokens: int = 1000, encoder=None
) -> Dict[str, Any]:
    """
    Trim document content to fit within token limit.
    Prefers summary over content, and truncates if necessary.
    """
    trimmed_doc = doc.copy()

    # Try summary first
    if "summary" in doc and doc["summary"]:
        summary_tokens = count_tokens(doc["summary"], encoder)
        if summary_tokens <= max_tokens:
            # Remove content if summary fits
            if "content" in trimmed_doc:
                del trimmed_doc["content"]
            return trimmed_doc

    # Try content if summary doesn't exist or is too long
    if "content" in doc and doc["content"]:
        content = doc["content"]
        content_tokens = count_tokens(content, encoder)

        if content_tokens > max_tokens:
            # Truncate content
            if encoder and TIKTOKEN_AVAILABLE:
                try:
                    tokens = encoder.encode(content)
                    truncated_tokens = tokens[: max_tokens - 10]  # Leave some margin
                    truncated_content = encoder.decode(truncated_tokens) + "..."
                    trimmed_doc["content"] = truncated_content
                except Exception:
                    # Fallback to character-based truncation
                    char_limit = int(max_tokens * 3)  # Rough estimate
                    trimmed_doc["content"] = content[:char_limit] + "..."
            else:
                # Fallback to character-based truncation
                char_limit = int(max_tokens * 3)  # Rough estimate
                trimmed_doc["content"] = content[:char_limit] + "..."

        # Remove summary if we're using content
        if "summary" in trimmed_doc:
            del trimmed_doc["summary"]

    return trimmed_doc
