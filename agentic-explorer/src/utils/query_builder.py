import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class SearchPhase(Enum):
    """Search phases for the Universal Query Builder."""

    BROAD = "broad"
    NARROW = "narrow"
    CHUNKS = "chunks"


@dataclass
class QueryTemplate:
    """Template for query construction with placeholders."""

    index: str
    query: Optional[str] = None
    query_body: Optional[Dict[str, Any]] = None
    embedding_field: str = "embedding_summary"
    top_k: int = 5
    size: int = 5
    sort: Optional[List[Dict[str, Any]]] = None
    source_fields: Optional[List[str]] = None


@dataclass
class DomainConfig:
    """Domain-specific configuration for agents."""

    primary_index: str
    chunks_index: Optional[str] = None
    domain_must: Optional[List[Dict[str, Any]]] = None
    domain_should: Optional[List[Dict[str, Any]]] = None
    domain_filter: Optional[List[Dict[str, Any]]] = None
    embedding_field: str = "embedding_summary"
    chunks_embedding_field: str = "embedding"


class UniversalQueryBuilder:
    """
    Universal Query Builder (UQB) - centralized search logic for all domain agents.

    Implements BREED-NAAR-SMAL strategy with phase-based queries:
    - Phase 1: BROAD → embedding only, top_k=5
    - Phase 2: NARROW → query_body filters (min_should_match, metadata, date)
    - Phase 3: CHUNKS → detail level with document_id filter
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._address_patterns = [
            r"\b([A-Z][a-z]+(?:straat|laan|weg|plein|park|singel|gracht))\s+(\d+[a-z]?)\b",
            r"\b(\d+[a-z]?)\s+([A-Z][a-z]+(?:straat|laan|weg|plein|park|singel|gracht))\b",
        ]

    def detect_address(self, query: str) -> Optional[str]:
        """
        Detect Dutch addresses in query text.

        Returns:
            Detected address string or None
        """
        for pattern in self._address_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                if pattern.endswith(r")\s+(\d+[a-z]?)\b"):  # street number format
                    street, number = match.groups()
                    return f"{street} {number}"
                else:  # number street format
                    number, street = match.groups()
                    return f"{street} {number}"
        return None

    def detect_temporal_context(self, query: str) -> Dict[str, Any]:
        """
        Detect temporal context in query (dates, periods, chronological keywords).

        Returns:
            Dictionary with temporal filters and sort preferences
        """
        temporal_context = {
            "has_temporal": False,
            "chronological": False,
            "sort_by_date": False,
            "date_filters": [],
        }

        # Chronological keywords
        chronological_keywords = [
            "chronologisch",
            "tijdlijn",
            "volgorde",
            "geschiedenis",
            "ontwikkeling",
            "verloop",
            "samenvatting",
        ]

        if any(keyword in query.lower() for keyword in chronological_keywords):
            temporal_context["chronological"] = True
            temporal_context["sort_by_date"] = True
            temporal_context["has_temporal"] = True

        # Recent/latest keywords
        recent_keywords = ["recent", "laatste", "nieuw", "actueel"]
        if any(keyword in query.lower() for keyword in recent_keywords):
            temporal_context["sort_by_date"] = True
            temporal_context["has_temporal"] = True

        return temporal_context

    def build_broad_query(
        self, user_query: str, config: DomainConfig, request_id: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Build Phase 1: BROAD query - embedding only, high recall.

        Args:
            user_query: Original user query
            config: Domain configuration
            request_id: Request ID for caching
            **kwargs: Additional parameters

        Returns:
            Query parameters for ElasticMCPClient.search
        """
        return {
            "index": config.primary_index,
            "query": user_query,
            "request_id": request_id,
            "embedding_field": config.embedding_field,
            "top_k": kwargs.get("top_k", 5),
        }

    def build_narrow_query(
        self,
        user_query: str,
        config: DomainConfig,
        request_id: str,
        address: Optional[str] = None,
        temporal_context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Build Phase 2: NARROW query - structured query_body with domain filters.

        Args:
            user_query: Original user query
            config: Domain configuration
            request_id: Request ID for caching
            address: Detected address
            temporal_context: Temporal context information
            **kwargs: Additional parameters

        Returns:
            Query parameters with structured query_body
        """
        query_body = {
            "query": {"bool": {"must": [], "should": [], "filter": []}},
            "size": kwargs.get("size", 10),
        }

        # Add domain-specific must clauses
        if config.domain_must:
            query_body["query"]["bool"]["must"].extend(config.domain_must)
        else:
            # Default multi_match query
            query_body["query"]["bool"]["must"].append(
                {
                    "multi_match": {
                        "query": user_query,
                        "fields": ["title^3", "summary^2", "content^1"],
                        "operator": "or",
                    }
                }
            )

        # Add domain-specific should clauses
        if config.domain_should:
            query_body["query"]["bool"]["should"].extend(config.domain_should)

        # Add domain-specific filters
        if config.domain_filter:
            query_body["query"]["bool"]["filter"].extend(config.domain_filter)

        # Add address filter if detected
        if address:
            address_filter = {
                "bool": {
                    "should": [
                        {"match_phrase": {"content": address}},
                        {"match_phrase": {"title": address}},
                        {
                            "match_phrase": {
                                "source_metadata.Gebiedsmarkering (Adres)": address
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            }
            query_body["query"]["bool"]["filter"].append(address_filter)

        # Add temporal sorting if needed
        if temporal_context and temporal_context.get("sort_by_date"):
            sort_order = "asc" if temporal_context.get("chronological") else "desc"
            query_body["sort"] = [{"publication_date": {"order": sort_order}}]

        # Add source fields
        if kwargs.get("source_fields"):
            query_body["_source"] = kwargs["source_fields"]

        return {
            "index": config.primary_index,
            "query": user_query,
            "request_id": request_id,
            "embedding_field": config.embedding_field,
            "query_body": query_body,
        }

    def build_chunks_query(
        self,
        detail_term: str,
        config: DomainConfig,
        request_id: str,
        document_ids: List[str],
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """
        Build Phase 3: CHUNKS query - detail level with document_id filter.

        Args:
            detail_term: Specific term to search for in chunks
            config: Domain configuration
            request_id: Request ID for caching
            document_ids: Document IDs from previous search
            **kwargs: Additional parameters

        Returns:
            Query parameters for chunks search or None if no chunks index
        """
        if not config.chunks_index or not document_ids:
            return None

        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {"multi_match": {"query": detail_term, "fields": ["content"]}},
                        {"terms": {"document_id": document_ids}},
                    ]
                }
            },
            "_source": ["content", "document_id", "chunk_id", "position"],
            "size": kwargs.get("size", 10),
        }

        return {
            "index": config.chunks_index,
            "query": detail_term,
            "request_id": request_id,
            "embedding_field": config.chunks_embedding_field,
            "query_body": query_body,
        }

    def build_query(
        self,
        user_query: str,
        config: DomainConfig,
        request_id: str,
        phase: SearchPhase = SearchPhase.BROAD,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Main entry point for building queries based on phase and configuration.

        Args:
            user_query: Original user query
            config: Domain configuration
            request_id: Request ID for caching
            phase: Search phase (BROAD, NARROW, CHUNKS)
            **kwargs: Additional parameters

        Returns:
            Query parameters for ElasticMCPClient.search
        """
        self.logger.info(f"Building {phase.value} query for: {user_query[:50]}...")

        # Detect context
        address = self.detect_address(user_query)
        temporal_context = self.detect_temporal_context(user_query)

        if address:
            self.logger.info(f"Detected address: {address}")
        if temporal_context["has_temporal"]:
            self.logger.info(f"Detected temporal context: {temporal_context}")

        # Build query based on phase
        if phase == SearchPhase.BROAD:
            return self.build_broad_query(user_query, config, request_id, **kwargs)
        elif phase == SearchPhase.NARROW:
            return self.build_narrow_query(
                user_query, config, request_id, address, temporal_context, **kwargs
            )
        elif phase == SearchPhase.CHUNKS:
            detail_term = kwargs.get("detail_term", user_query)
            document_ids = kwargs.get("document_ids", [])
            return self.build_chunks_query(
                detail_term, config, request_id, document_ids, **kwargs
            )
        else:
            raise ValueError(f"Unknown search phase: {phase}")

    def extract_document_ids(self, search_results: List[Dict[str, Any]]) -> List[str]:
        """
        Extract document IDs from search results for chunks queries.

        Args:
            search_results: Results from ElasticMCPClient.search

        Returns:
            List of document IDs
        """
        document_ids = []
        for result in search_results:
            doc_id = result.get("id") or result.get("document_id")
            if doc_id:
                document_ids.append(doc_id)
        return document_ids


# Global instance for reuse
query_builder = UniversalQueryBuilder()
