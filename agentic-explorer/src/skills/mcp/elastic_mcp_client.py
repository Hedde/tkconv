import json
import logging
import os
from typing import Annotated, Any, Dict, List

from semantic_kernel.connectors.mcp import MCPStdioPlugin
from semantic_kernel.contents.text_content import TextContent
from semantic_kernel.functions import KernelArguments, kernel_function

# Import a function to retrieve embeddings from the shared cache
from utils.embedding_cache_store import retrieve_embedding


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

    _DEFAULT_TOP_K = 5
    # Only fetch lightweight, high-level fields unless caller explicitly asks otherwise.
    _DEFAULT_SOURCE_FIELDS = [
        "id",
        "title",
        "summary",
        "source_metadata",
        "uri",
        "publication_date",
        "document_type",
    ]
    _indices_cache: List[str] = []
    _mappings_cache: Dict[str, Any] = {}

    def __init__(self) -> None:
        self.base_url: str = os.getenv("MCP_URL", "http://localhost:6277").rstrip("/")
        self._log = logging.getLogger("mcp.elastic_client")

    # ─────────────────────────────────────────── internal helper ──
    async def _call_tool(self, name: str, **kwargs):
        """Launch `@elastic/mcp-server-elasticsearch` via npx and invoke *name*.

        The Node process is started on-demand via MCPStdioPlugin (SSE over stdio)
        so the Python app stays dependency-free.
        """
        es_url = os.getenv("ES_URL")
        es_api_key = os.getenv("ES_API_KEY", "")
        self._log.info(
            "Starting MCPStdioPlugin with ES_URL=%s, tool=%s, args=%s",
            es_url,
            name,
            kwargs,
        )

        cmd = f'ES_URL="{es_url}" ES_API_KEY="{es_api_key}" npx -y @elastic/mcp-server-elasticsearch'
        self._log.info("Command to run Node MCP plugin: %s", cmd)

        try:
            async with MCPStdioPlugin(
                name="ElasticMCP",
                command="sh",
                args=["-c", cmd],
                load_tools=True,
                load_prompts=False,
            ) as mcp_plugin:
                self._log.info(
                    "MCPStdioPlugin started successfully, methods available: %s",
                    dir(mcp_plugin),
                )
                tool = getattr(mcp_plugin, name, None)
                if not tool:
                    raise RuntimeError(f"Tool {name} not found in MCP plugin")
                self._log.info("Calling MCP tool %s with args: %s", name, kwargs)
                result = await tool(**kwargs)
                self._log.info("MCP tool %s completed successfully", name)
                return result
        except Exception as e:
            self._log.error("Error calling MCP tool %s: %s", name, e, exc_info=True)
            # Custom error handling could be added here
            # For now, we'll re-raise the exception to let Semantic Kernel handle it
            raise

    # ─────────────────────────────────────────── public SK tools ──

    @kernel_function(
        name="search",
        description="Search an Elastic index and return up to `top_k` hits. By default only lightweight fields (id, title, summary…) are fetched. Can perform hybrid search if a pre-computed query_vector is found in cache for the given request_id.",
    )
    async def search(
        self,
        index: Annotated[
            str, "Name of the index to search – must be in list_indices()"
        ],
        query: Annotated[
            str | None,
            "Optional plain-text query; used for keyword part of hybrid search or if query_body is not provided",
        ] = None,
        request_id: Annotated[
            str
            | None,  # Changed to Optional, agent might not always have it initially.
            "The request ID used to retrieve a pre-computed query vector from cache for KNN search. If not provided or vector not found, falls back to keyword-only search.",
        ] = None,  # Make it optional, so agent can call without if needed (fallback)
        query_body: Annotated[
            Dict[str, Any] | None,
            "Full Elasticsearch DSL body to execute. If provided, it's assumed this body already includes the KNN clause or is structured for hybrid search, or that hybrid search is not intended with this body.",
        ] = None,
        queryBody: Annotated[
            Dict[str, Any] | None,
            "Alias for query_body – camelCase version used in MCP contract",
        ] = None,
        embedding_field: Annotated[
            str | None,
            "Name of the field in Elasticsearch that contains the document embeddings. Defaults to 'embedding_summary'.",
        ] = "embedding_summary",
        top_k: Annotated[
            int | None, "Maximum number of hits to return (defaults to 5)"
        ] = None,
        num_candidates: Annotated[
            int | None, "Number of candidates for KNN search. Defaults to 50."
        ] = 50,
        arguments: KernelArguments | None = None,
    ) -> List[Dict[str, Any]]:
        if query_body is None and queryBody is not None:
            query_body = queryBody

        top_k = top_k or self._DEFAULT_TOP_K
        final_query_body: Dict[str, Any]
        query_vector: List[float] | None = None

        if request_id:
            self._log.info(
                f"Attempting to retrieve pre-computed vector using request_id: {request_id}"
            )
            query_vector = retrieve_embedding(request_id)  # Retrieve from shared cache
            if query_vector:
                self._log.info(
                    f"Successfully retrieved query_vector for request_id: {request_id}"
                )
            else:
                self._log.warning(
                    f"No query_vector found in cache for request_id: {request_id}. Proceeding without vector search."
                )
        else:
            self._log.warning(
                "No request_id provided to search function. Cannot retrieve pre-computed vector."
            )

        if query_body is not None:
            final_query_body = query_body
            final_query_body.setdefault("size", top_k)
            if query_vector and "knn" not in final_query_body:
                self._log.warning(
                    "query_body provided without a 'knn' clause, but a query_vector was retrieved from cache. "
                    "The provided query_body will be used as is. If hybrid search with this query_body was intended, "
                    "the query_body itself must include the knn clause."
                )
        elif query_vector is not None:  # query_body is None, but we have a vector
            if not embedding_field:
                self._log.error(
                    "embedding_field name is required for KNN search when query_vector is available."
                )
                return []

            knn_clause = {
                "field": embedding_field,
                "query_vector": query_vector,
                "k": top_k,
                "num_candidates": num_candidates or 50,
            }

            # Enhanced keyword part for hybrid search
            keyword_query_part = {
                "multi_match": {
                    "query": query or "",
                    "fields": [
                        "title^3",
                        "summary^1.5",
                        "content^1",
                        "key_concepts_llm^2",
                    ],
                    "operator": "or",  # More recall
                }
            }

            final_query_body = {
                "knn": knn_clause,
                # The 'query' part is combined with 'knn' by Elasticsearch for hybrid search scoring
                "query": keyword_query_part,
                "size": top_k,
            }
            self._log.info(
                f"Constructed hybrid query with KNN (vector from cache) and multi_match (keyword). Embedding field: {embedding_field}, Query: {query}"
            )
        else:  # No query_body and no query_vector (either no request_id or not found in cache)
            # Enhanced keyword-only search
            final_query_body = {
                "query": {
                    "multi_match": {
                        "query": query or "",
                        "fields": [
                            "title^3",
                            "summary^1.5",
                            "content^1",
                            "key_concepts_llm^2",
                        ],
                        "operator": "or",  # More recall
                    }
                },
                "size": top_k,
            }
            self._log.info(
                f"Constructed keyword-only (multi_match) query because no query_vector was available/retrieved. Query: {query}"
            )

        if "_source" not in final_query_body:
            final_query_body["_source"] = self._DEFAULT_SOURCE_FIELDS

        final_query_body.setdefault("size", top_k)

        try:
            mcp_payload = {"index": index, "queryBody": final_query_body}
            result = await self._call_tool("search", **mcp_payload)
            self._log.info(
                "SEARCH REQUEST to MCP for index %s: %s",
                index,
                json.dumps(mcp_payload, indent=2),
            )
            self._log.info("SEARCH RESULT from MCP for index %s: %r", index, result)
        except Exception as e:
            self._log.error("SEARCH FAILED for index %s: %s", index, e, exc_info=True)
            return [
                {
                    "id": f"mock_{i}",
                    "index": index,
                    "score": 1.0 / (i + 1),
                    "title": f"Mock title {i + 1}",
                }
                for i in range(min(top_k, 3))
            ]

        hits: List[Dict[str, Any]] = []
        for idx_line, item in enumerate(result):
            if isinstance(item, dict):
                data = dict(item)
            else:
                try:
                    data = json.loads(str(item))
                except Exception:
                    data = {"id": str(item), "text": str(item)}
            data.setdefault("index", index)
            data.setdefault("score", 1.0 / (idx_line + 1))
            hits.append(data)
        return hits

    # ────────────────────────────────────────────────────────────────
    @kernel_function(
        name="list_indices",
        description="Return a JSON array with all available MCP index names. Use reload=true to refresh the local cache.",
    )
    async def list_indices(
        self,
        reload: Annotated[bool, "Set to true to bypass the client-side cache"] = False,
        arguments: KernelArguments | None = None,
    ) -> List[str]:
        if self._indices_cache and not reload:
            return self._indices_cache

        try:
            result = await self._call_tool("list_indices")
            self._log.info("Raw list_indices result: %r", result)
            indices = []
            if result and isinstance(result, list):
                for item in result:
                    if isinstance(item, TextContent) and item.text.strip().startswith(
                        "["
                    ):
                        raw_json = json.loads(item.text)
                        if all(isinstance(el, str) for el in raw_json):
                            indices = raw_json
                        else:
                            indices = [el.get("index", str(el)) for el in raw_json]
                        break
            self._indices_cache = indices
        except Exception as e:
            self._log.warning("list_indices failed: %s", e)
        return self._indices_cache

    # ────────────────────────────────────────────────────────────────
    @kernel_function(
        name="get_mappings",
        description="Return the full Elasticsearch mapping (properties schema) for the specified index. Result equals GET /<index>/_mapping.",
    )
    async def get_mappings(
        self,
        index: Annotated[str, "Name of the index (see list_indices)"],
        reload: Annotated[bool, "Force fetch from server instead of cache"] = False,
        arguments: KernelArguments | None = None,
    ) -> Dict[str, Any]:
        if index in self._mappings_cache and not reload:
            return self._mappings_cache[index]

        try:
            result = await self._call_tool("get_mappings", index=index)
            items = (
                result["content"]
                if isinstance(result, dict) and "content" in result
                else result
            )
            mapping_json: Dict[str, Any] = {}
            for item in items:
                txt = getattr(item, "text", None) or item
                if not isinstance(txt, str):
                    continue
                txt = txt.strip()
                if "{" in txt and "properties" in txt:
                    json_part = txt[txt.find("{") :]
                    try:
                        mapping_json = json.loads(json_part)
                        break
                    except Exception:
                        continue
            self._mappings_cache[index] = mapping_json
        except Exception as e:
            self._log.warning("get_mappings failed for %s: %s", index, e)
        return self._mappings_cache.get(index, {})
