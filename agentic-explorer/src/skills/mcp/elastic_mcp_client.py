import json
import logging
import os
from typing import Annotated, Any, Dict, List, Optional

from semantic_kernel.connectors.mcp import MCPStdioPlugin
from semantic_kernel.contents.text_content import TextContent
from semantic_kernel.functions import KernelArguments, kernel_function

# Import a function to retrieve embeddings from the shared cache
from utils.embedding_cache_store import retrieve_embedding

# Constants
DEFAULT_TOP_K = 5
DEFAULT_NUM_CANDIDATES = 50
DEFAULT_BOOST_TITLE = 3.0
DEFAULT_BOOST_SUMMARY = 1.5
DEFAULT_BOOST_CONTENT = 1.0
DEFAULT_BOOST_CONCEPTS = 2.0

# Field names for search
SEARCH_FIELDS = [
    f"title^{DEFAULT_BOOST_TITLE}",
    f"summary^{DEFAULT_BOOST_SUMMARY}",
    f"content^{DEFAULT_BOOST_CONTENT}",
    f"key_concepts_llm^{DEFAULT_BOOST_CONCEPTS}",
]

# Default source fields to fetch
DEFAULT_SOURCE_FIELDS = [
    "id",
    "title",
    "summary",
    "source_metadata",
    "uri",
    "publication_date",
    "document_type",
]

# Logging constants
LOG_PREFIX_INFO = "Elastic MCP:"
LOG_PREFIX_DEBUG = "🔍 DEBUG:"

# Mock response configuration
MOCK_RESPONSE_COUNT = 3


class ElasticMCPClient:
    """Native Semantic-Kernel plugin that wraps an *Elasticsearch* Municipal Content Platform (MCP) server.

    Exposes three tools that are part of the public MCP contract:

        • list_indices   → array[str] of available index names
        • get_mappings   → JSON mapping for one index (properties schema)
        • search         → search an index and return a list of hits (dict)

    Output conventions
    -------------------
    search returns a *JSON array* where each element **must** contain at
    least these top-level keys:
        id        – unique document identifier (string)
        index     – the index that produced the hit (string)
        score     – relevance score (float; 1.0 = highest)
    Optionally you can include: title, text, summary, snippet, content, uri, …

    This thin wrapper ensures that type-hints + description strings are rich
    enough for Semantic-Kernel to auto-generate correct Function-Calling
    schemas.  The LLM therefore **knows** the exact arguments & return shape
    without ever having to call a separate "discover tools" endpoint.
    """

    def __init__(self) -> None:
        """Initialize Elasticsearch MCP client with environment configuration."""
        self.base_url: str = os.getenv("MCP_URL", "http://localhost:6277").rstrip("/")
        self._log = logging.getLogger("mcp.elastic_client")

        # Cache for performance optimization
        self._indices_cache: List[str] = []
        self._mappings_cache: Dict[str, Any] = {}

        self._log.info(f"{LOG_PREFIX_INFO} Initialized with base_url: {self.base_url}")

    async def _call_tool(self, name: str, **kwargs) -> Any:
        """
        Launch Elasticsearch MCP server and invoke specified tool.

        Args:
            name: Tool name to invoke
            **kwargs: Tool arguments

        Returns:
            Tool execution result

        Raises:
            RuntimeError: If tool execution fails
        """
        es_url = os.getenv("ES_URL")
        es_api_key = os.getenv("ES_API_KEY", "")

        self._log.info(f"{LOG_PREFIX_INFO} Invoking tool {name} with ES_URL={es_url}")

        cmd = f'ES_URL="{es_url}" ES_API_KEY="{es_api_key}" npx -y @elastic/mcp-server-elasticsearch'
        self._log.debug(f"{LOG_PREFIX_INFO} Command: {cmd}")

        try:
            async with MCPStdioPlugin(
                name="ElasticMCP",
                command="sh",
                args=["-c", cmd],
                load_tools=True,
                load_prompts=False,
            ) as mcp_plugin:
                tool = getattr(mcp_plugin, name, None)
                if not tool:
                    raise RuntimeError(f"Tool {name} not found in MCP plugin")

                self._log.info(f"{LOG_PREFIX_INFO} Calling tool {name}")
                result = await tool(**kwargs)
                self._log.info(f"{LOG_PREFIX_INFO} Tool {name} completed successfully")
                return result

        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Tool {name} failed: {e}", exc_info=True)
            raise

    def _build_hybrid_search_query(
        self,
        query: Optional[str],
        query_vector: List[float],
        embedding_field: str,
        top_k: int,
        num_candidates: int,
    ) -> Dict[str, Any]:
        """
        Build hybrid search query combining KNN and keyword search.

        Args:
            query: Text query for keyword search
            query_vector: Vector for semantic search
            embedding_field: Field containing document embeddings
            top_k: Number of results to return
            num_candidates: KNN candidate count

        Returns:
            Elasticsearch query body
        """
        knn_clause = {
            "field": embedding_field,
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": num_candidates,
        }

        keyword_query = {
            "multi_match": {
                "query": query or "",
                "fields": SEARCH_FIELDS,
                "operator": "or",
            }
        }

        return {
            "knn": knn_clause,
            "query": keyword_query,
            "size": top_k,
        }

    def _build_keyword_only_query(
        self, query: Optional[str], top_k: int
    ) -> Dict[str, Any]:
        """
        Build keyword-only search query.

        Args:
            query: Text query
            top_k: Number of results to return

        Returns:
            Elasticsearch query body
        """
        return {
            "query": {
                "multi_match": {
                    "query": query or "",
                    "fields": SEARCH_FIELDS,
                    "operator": "or",
                }
            },
            "size": top_k,
        }

    def _create_mock_response(self, index: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Create mock search response for fallback scenarios.

        Args:
            index: Index name for mock results
            top_k: Number of mock results

        Returns:
            Mock search results
        """
        return [
            {
                "id": f"mock_{i}",
                "index": index,
                "score": 1.0 / (i + 1),
                "title": f"Mock title {i + 1}",
            }
            for i in range(min(top_k, MOCK_RESPONSE_COUNT))
        ]

    def _normalize_search_results(
        self, result: Any, index: str
    ) -> List[Dict[str, Any]]:
        """
        Normalize search results to consistent format.

        Args:
            result: Raw search results from MCP
            index: Index name for context

        Returns:
            Normalized results with required fields
        """
        hits = []

        for idx, item in enumerate(result):
            if isinstance(item, dict):
                data = dict(item)
            else:
                try:
                    data = json.loads(str(item))
                except Exception:
                    data = {"id": str(item), "text": str(item)}

            # Ensure required fields
            data.setdefault("index", index)
            data.setdefault("score", 1.0 / (idx + 1))
            hits.append(data)

        return hits

    def _log_search_operation(
        self,
        index: str,
        query: Optional[str],
        has_vector: bool,
        result_count: int,
    ) -> None:
        """
        Log search operation details.

        Args:
            index: Search index
            query: Query text
            has_vector: Whether vector search was used
            result_count: Number of results returned
        """
        search_type = "hybrid" if has_vector else "keyword-only"
        self._log.info(
            f"{LOG_PREFIX_INFO} {search_type} search on '{index}' "
            f"with query '{query}' returned {result_count} results"
        )

    @kernel_function(
        name="search",
        description="Advanced search with hybrid semantic and keyword capabilities for parliamentary documents",
    )
    async def search(
        self,
        index: Annotated[str, "Target index name from list_indices()"],
        query: Annotated[str, "Text query for keyword search"] = "",
        request_id: Annotated[str, "Request ID for cached vector retrieval"] = "",
        query_body: Annotated[str, "Custom Elasticsearch DSL as JSON string"] = "",
        queryBody: Annotated[str, "Alias for query_body"] = "",
        embedding_field: Annotated[
            str, "Document embedding field"
        ] = "embedding_summary",
        top_k: Annotated[int, "Maximum results"] = DEFAULT_TOP_K,
        num_candidates: Annotated[int, "KNN candidates"] = DEFAULT_NUM_CANDIDATES,
        arguments: Optional[KernelArguments] = None,
    ) -> List[Dict[str, Any]]:
        """Execute advanced search with hybrid semantic and keyword capabilities."""
        # Resolve parameters
        query = query.strip() if query else None
        request_id = request_id.strip() if request_id else None

        # Parse query body if provided
        parsed_query_body = None
        if query_body and query_body.strip():
            try:
                parsed_query_body = json.loads(query_body)
            except json.JSONDecodeError:
                self._log.warning(
                    f"{LOG_PREFIX_INFO} Invalid query_body JSON: {query_body}"
                )
        elif queryBody and queryBody.strip():
            try:
                parsed_query_body = json.loads(queryBody)
            except json.JSONDecodeError:
                self._log.warning(
                    f"{LOG_PREFIX_INFO} Invalid queryBody JSON: {queryBody}"
                )

        top_k = max(1, top_k) if top_k else DEFAULT_TOP_K
        num_candidates = (
            max(1, num_candidates) if num_candidates else DEFAULT_NUM_CANDIDATES
        )
        final_query_body: Dict[str, Any]
        query_vector: Optional[List[float]] = None

        # Attempt vector retrieval if request_id provided
        if request_id:
            self._log.info(
                f"{LOG_PREFIX_INFO} Retrieving vector for request_id: {request_id}"
            )
            query_vector = retrieve_embedding(request_id)

            if query_vector:
                self._log.info(f"{LOG_PREFIX_INFO} Vector retrieved successfully")
            else:
                self._log.warning(
                    f"{LOG_PREFIX_INFO} No vector found for request_id: {request_id}"
                )

        # Build appropriate query
        if parsed_query_body is not None:
            # Use provided query body
            final_query_body = parsed_query_body
            final_query_body.setdefault("size", top_k)

            if query_vector and "knn" not in final_query_body:
                self._log.warning(
                    f"{LOG_PREFIX_INFO} Custom query_body without KNN clause but vector available"
                )

        elif query_vector is not None:
            # Build hybrid search query
            if not embedding_field:
                self._log.error(
                    f"{LOG_PREFIX_INFO} embedding_field required for vector search"
                )
                return []

            final_query_body = self._build_hybrid_search_query(
                query,
                query_vector,
                embedding_field,
                top_k,
                num_candidates,
            )
            self._log.info(f"{LOG_PREFIX_INFO} Built hybrid search query")

        else:
            # Build keyword-only query
            final_query_body = self._build_keyword_only_query(query, top_k)
            self._log.info(f"{LOG_PREFIX_INFO} Built keyword-only query")

        # Set default source fields if not specified
        if "_source" not in final_query_body:
            final_query_body["_source"] = DEFAULT_SOURCE_FIELDS

        final_query_body.setdefault("size", top_k)

        # Execute search
        try:
            mcp_payload = {"index": index, "queryBody": final_query_body}

            self._log.debug(
                f"{LOG_PREFIX_INFO} Search payload: {json.dumps(mcp_payload, indent=2)}"
            )

            result = await self._call_tool("search", **mcp_payload)
            hits = self._normalize_search_results(result, index)

            self._log_search_operation(
                index, query, query_vector is not None, len(hits)
            )
            return hits

        except Exception as e:
            self._log.error(
                f"{LOG_PREFIX_INFO} Search failed for index {index}: {e}", exc_info=True
            )
            return self._create_mock_response(index, top_k)

    @kernel_function(
        name="list_indices",
        description="Discover available Elasticsearch indices with optional cache refresh",
    )
    async def list_indices(
        self,
        reload: Annotated[bool, "Force refresh from server"] = False,
        arguments: Optional[KernelArguments] = None,
    ) -> List[str]:
        """List all available search indices."""
        if self._indices_cache and not reload:
            return self._indices_cache

        try:
            result = await self._call_tool("list_indices")
            self._log.debug(f"{LOG_PREFIX_INFO} Raw indices result: {result}")

            indices = []
            if result and isinstance(result, list):
                for item in result:
                    if isinstance(item, TextContent) and item.text.strip().startswith(
                        "["
                    ):
                        try:
                            raw_json = json.loads(item.text)
                            if all(isinstance(el, str) for el in raw_json):
                                indices = raw_json
                            else:
                                indices = [el.get("index", str(el)) for el in raw_json]
                            break
                        except json.JSONDecodeError:
                            continue

            self._indices_cache = indices
            self._log.info(f"{LOG_PREFIX_INFO} Retrieved {len(indices)} indices")

        except Exception as e:
            self._log.warning(f"{LOG_PREFIX_INFO} List indices failed: {e}")

        return self._indices_cache

    @kernel_function(
        name="get_mappings",
        description="Retrieve Elasticsearch mapping schema for detailed index structure analysis",
    )
    async def get_mappings(
        self,
        index: Annotated[str, "Index name from list_indices()"],
        reload: Annotated[bool, "Force refresh from server"] = False,
        arguments: Optional[KernelArguments] = None,
    ) -> Dict[str, Any]:
        """Get comprehensive mapping information for specified index."""
        if index in self._mappings_cache and not reload:
            return self._mappings_cache[index]

        try:
            result = await self._call_tool("get_mappings", index=index)

            # Extract mapping content
            items = (
                result["content"]
                if isinstance(result, dict) and "content" in result
                else result
            )

            mapping_json: Dict[str, Any] = {}

            if isinstance(items, (list, tuple)):
                for item in items:
                    text = getattr(item, "text", None) or str(item)
                    if not isinstance(text, str):
                        continue

                    text = text.strip()
                    if "{" in text and "properties" in text:
                        json_start = text.find("{")
                        json_part = text[json_start:]
                        try:
                            mapping_json = json.loads(json_part)
                            break
                        except json.JSONDecodeError:
                            continue

            self._mappings_cache[index] = mapping_json
            self._log.info(f"{LOG_PREFIX_INFO} Mapping retrieved for index: {index}")

        except Exception as e:
            self._log.warning(f"{LOG_PREFIX_INFO} Get mappings failed for {index}: {e}")

        return self._mappings_cache.get(index, {})

    def clear_cache(self) -> None:
        """Clear all cached data for fresh retrieval."""
        self._indices_cache.clear()
        self._mappings_cache.clear()
        self._log.info(f"{LOG_PREFIX_INFO} Cache cleared")
