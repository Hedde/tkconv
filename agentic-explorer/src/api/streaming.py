"""Streaming API endpoints for parliamentary data queries."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi.responses import StreamingResponse
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig

from orchestration.agents import agents
from orchestration.callbacks import make_streaming_callback
from orchestration.constants import (
    STREAMING_MAX_RESET_COUNT,
    STREAMING_MAX_ROUND_COUNT,
    STREAMING_MAX_STALL_COUNT,
    StreamEvents,
    SystemSteps,
)
from orchestration.magentic import create_magentic_orchestration
from utils.embedding_cache_store import (
    clear_embedding,
    retrieve_embedding,
    store_embedding,
)
from utils.embedding_generator import generate_embedding_vector
from utils.logging import configure_logging, extract_request_id, get_pipeline_logger

# Constants
TOKEN_STREAMING_DELAY = 0.005
SKILLS_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "query_rewriting_skill"
    / "QueryRewriteFunction"
)

configure_logging()
logger = get_pipeline_logger("magentic_stream")


def _now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat() + "Z"


async def _get_or_create_embedding(query_text: str, request_id: str) -> List[float]:
    """
    Generate or retrieve embedding for query text.

    Args:
        query_text: The query to embed
        request_id: Request identifier for caching

    Returns:
        Embedding vector
    """
    if not query_text:
        return []

    cached_vector = retrieve_embedding(request_id)
    if cached_vector:
        return cached_vector

    logger.info(f"Generating embedding for request {request_id}")
    vector = await generate_embedding_vector(query_text)
    store_embedding(request_id, vector)
    return vector


def _deduplicate_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate citations based on unique identifiers.

    Args:
        citations: List of citation dictionaries

    Returns:
        Deduplicated citations
    """
    if not citations:
        return []

    seen_ids = set()
    deduplicated = []

    for citation in citations:
        # Determine unique identifier
        unique_id = citation.get(
            "document_id", citation.get("id", citation.get("title", None))
        )

        if not unique_id:
            unique_id = "-".join(str(v) for v in citation.values() if v)

        if unique_id not in seen_ids:
            seen_ids.add(unique_id)
            deduplicated.append(citation)

    logger.info(
        f"Citations: {len(citations)} → {len(deduplicated)} after deduplication"
    )
    return deduplicated


async def _put_event_on_queue(
    queue: asyncio.Queue, event_name: str, request_id: str, **kwargs
) -> None:
    """Emit an event to the streaming queue."""
    payload = {
        "event": event_name,
        "timestamp": _now_iso(),
        "request_id": request_id,
        **kwargs,
    }

    await queue.put(json.dumps(payload))
    logger.info(
        kwargs.get("message", event_name),
        extra={"extra_payload": payload, "request_id": request_id},
    )


async def _rewrite_query_for_stream(original_prompt: str, request_id: str) -> str:
    """
    Rewrite query using the query rewriting skill.

    Args:
        original_prompt: Original user query
        request_id: Request identifier

    Returns:
        Rewritten query or original if rewriting fails
    """
    try:
        openai_model = os.getenv("OPENAI_MODEL")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not openai_model or not openai_api_key:
            logger.warning(f"OpenAI credentials missing for request {request_id}")
            return original_prompt

        kernel = Kernel()
        kernel.add_service(
            OpenAIChatCompletion(ai_model_id=openai_model, api_key=openai_api_key)
        )

        # Load skill configuration
        prompt_file = SKILLS_PATH / "skprompt.txt"
        config_file = SKILLS_PATH / "config.json"

        if not prompt_file.exists() or not config_file.exists():
            logger.warning(f"Query rewrite skill not found for request {request_id}")
            return original_prompt

        prompt_template = prompt_file.read_text(encoding="utf-8")
        config_data = json.loads(config_file.read_text(encoding="utf-8"))

        prompt_config = PromptTemplateConfig(
            template=prompt_template,
            name="QueryRewriteFunction",
            description=config_data["description"],
            template_format="semantic-kernel",
            input_variables=[
                {
                    "name": "question",
                    "description": "De originele gebruikersvraag",
                    "is_required": True,
                }
            ],
            execution_settings=config_data.get("execution_settings", {}),
        )

        query_rewrite_fn = kernel.add_function(
            plugin_name="query_rewriting_skill",
            function_name="QueryRewriteFunction",
            prompt_template_config=prompt_config,
        )

        rewrite_result = await kernel.invoke(
            query_rewrite_fn, KernelArguments(question=original_prompt)
        )

        if rewrite_result and rewrite_result.value:
            rewritten_text = str(rewrite_result.value).strip()
            if rewritten_text:
                logger.info(f"Query rewritten for request {request_id}")
                return rewritten_text

        logger.warning(f"Query rewrite failed for request {request_id}")
        return original_prompt

    except Exception as e:
        logger.error(
            f"Error rewriting query for request {request_id}: {e}", exc_info=True
        )
        return original_prompt


async def magentic_ask_stream(
    prompt: str, request_id: Optional[str] = None, request=None
) -> StreamingResponse:
    """
    Process a parliamentary data query with streaming response.

    Args:
        prompt: User's query
        request_id: Optional request identifier
        request: FastAPI request object

    Returns:
        StreamingResponse with real-time updates
    """
    # Initialize queues and callback
    internal_event_queue = asyncio.Queue()
    client_event_queue = asyncio.Queue()
    streaming_callback = make_streaming_callback(internal_event_queue)

    # Determine request ID
    if not request_id and request is not None:
        request_id = extract_request_id(request)
    if not request_id:
        import uuid

        request_id = str(uuid.uuid4())

    all_citations = []

    async def _orchestrate_and_process_events():
        """Main orchestration logic with event processing."""
        nonlocal all_citations

        try:
            # Query rewriting
            rewritten_query = await _rewrite_query_for_stream(prompt, request_id)

            # Embedding generation
            await _get_or_create_embedding(rewritten_query, request_id)
            agent_task = f"User query: {rewritten_query} Request ID: {request_id}"

            # Citation processing task
            async def _process_internal_events():
                """Process internal events and forward to client."""
                while True:
                    event_json = await internal_event_queue.get()
                    event_data = json.loads(event_json)

                    if event_data.get("event") == StreamEvents.CITATIONS_FOUND:
                        if "citations" in event_data:
                            all_citations.extend(event_data["citations"])
                        logger.info(f"Total citations: {len(all_citations)}")
                        internal_event_queue.task_done()
                        continue

                    # Forward other events
                    if event_data.get("event") == StreamEvents.THOUGHT:
                        logger.info("Forwarding thought to client")

                    await client_event_queue.put(event_json)

                    # Check for termination signal
                    if event_data.get("event") == "done_internal_processing_signal":
                        logger.info("Internal event processing complete")
                        internal_event_queue.task_done()
                        break

                    internal_event_queue.task_done()

            consumer_task = asyncio.create_task(_process_internal_events())

            try:
                # Execute orchestration with timing
                start_time = datetime.now(timezone.utc)

                await _put_event_on_queue(
                    client_event_queue,
                    StreamEvents.SYSTEM,
                    request_id,
                    step=SystemSteps.RECEIVED,
                    message="Request received",
                )

                # Initialize agents
                agents_start = datetime.now(timezone.utc)
                await _put_event_on_queue(
                    client_event_queue,
                    StreamEvents.SYSTEM,
                    request_id,
                    step=SystemSteps.INIT_AGENTS,
                    message="Initializing agents...",
                )

                agents_list = await agents()
                agents_duration = int(
                    (datetime.now(timezone.utc) - agents_start).total_seconds() * 1000
                )

                await _put_event_on_queue(
                    client_event_queue,
                    StreamEvents.SYSTEM,
                    request_id,
                    step=SystemSteps.INIT_AGENTS_DONE,
                    message="Agents initialized",
                    duration_ms=agents_duration,
                )

                # Start orchestration
                orch_start = datetime.now(timezone.utc)
                await _put_event_on_queue(
                    client_event_queue,
                    StreamEvents.SYSTEM,
                    request_id,
                    step=SystemSteps.START_ORCHESTRATION,
                    message="Starting orchestration...",
                )

                # Create event callback for manager
                async def _manager_event_callback(event_name, **kwargs):
                    await _put_event_on_queue(
                        client_event_queue, event_name, request_id, **kwargs
                    )

                # Create and run orchestration
                orchestration = await create_magentic_orchestration(
                    agents_list,
                    streaming_callback,
                    event_callback=_manager_event_callback,
                    max_round_count=STREAMING_MAX_ROUND_COUNT,
                    max_reset_count=STREAMING_MAX_RESET_COUNT,
                    max_stall_count=STREAMING_MAX_STALL_COUNT,
                )

                runtime = InProcessRuntime()
                runtime.start()

                orchestration_result = await orchestration.invoke(
                    task=agent_task,
                    runtime=runtime,
                )

                orch_duration = int(
                    (datetime.now(timezone.utc) - orch_start).total_seconds() * 1000
                )
                await _put_event_on_queue(
                    client_event_queue,
                    StreamEvents.SYSTEM,
                    request_id,
                    step=SystemSteps.ORCHESTRATION_STARTED,
                    message="Orchestration started",
                    duration_ms=orch_duration,
                )

                # Get final result
                answer_start = datetime.now(timezone.utc)
                await _put_event_on_queue(
                    client_event_queue,
                    StreamEvents.SYSTEM,
                    request_id,
                    step=SystemSteps.WAITING_FOR_RESULT,
                    message="Waiting for result...",
                )

                result = await orchestration_result.get()
                answer_duration = int(
                    (datetime.now(timezone.utc) - answer_start).total_seconds() * 1000
                )

                await _put_event_on_queue(
                    client_event_queue,
                    StreamEvents.SYSTEM,
                    request_id,
                    step=SystemSteps.RESULT_READY,
                    message="Result ready",
                    duration_ms=answer_duration,
                )

                # Stream answer tokens
                answer_text = getattr(result, "content", str(result))
                for token in answer_text:
                    await _put_event_on_queue(
                        client_event_queue, StreamEvents.TOKEN, request_id, text=token
                    )
                    await asyncio.sleep(TOKEN_STREAMING_DELAY)

                # Send final completion event
                total_duration = int(
                    (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                )
                done_payload = {
                    "event": StreamEvents.DONE,
                    "timestamp": _now_iso(),
                    "request_id": request_id,
                    "total_duration_ms": total_duration,
                }

                if all_citations:
                    deduplicated_citations = _deduplicate_citations(all_citations)
                    done_payload["answer_json"] = json.dumps(
                        {"citations": deduplicated_citations}
                    )

                await client_event_queue.put(json.dumps(done_payload))

            except Exception as e:
                logger.error(f"Error in orchestration: {e}", exc_info=True)
                error_payload = {
                    "event": StreamEvents.DONE,
                    "error": str(e),
                    "timestamp": _now_iso(),
                    "request_id": request_id,
                    "total_duration_ms": 0,
                }
                await client_event_queue.put(json.dumps(error_payload))

            finally:
                # Clean up
                await internal_event_queue.put(
                    json.dumps({"event": "done_internal_processing_signal"})
                )
                await consumer_task

                if "runtime" in locals():
                    await runtime.stop_when_idle()

                clear_embedding(request_id)
                logger.info(f"Cleanup complete for request {request_id}")

        except Exception as e:
            logger.error(f"Critical error in orchestration: {e}", exc_info=True)
            await client_event_queue.put(
                json.dumps(
                    {
                        "event": StreamEvents.DONE,
                        "error": "Internal server error",
                        "timestamp": _now_iso(),
                        "request_id": request_id,
                    }
                )
            )

    # Start orchestration task
    asyncio.create_task(_orchestrate_and_process_events())

    # SSE response generator
    async def _sse_response():
        """Generate Server-Sent Events stream."""
        while True:
            message = await client_event_queue.get()
            yield f"data: {message}\n\n"

            if json.loads(message).get("event") == StreamEvents.DONE:
                client_event_queue.task_done()
                break

            client_event_queue.task_done()

    return StreamingResponse(_sse_response(), media_type="text/event-stream")


# Public API for backwards compatibility
deduplicate_citations = _deduplicate_citations
