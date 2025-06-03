import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi.responses import StreamingResponse
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig

from orchestration.agents import agents
from orchestration.callbacks import make_streaming_callback
from orchestration.magentic import create_magentic_orchestration

# --- Additions for Embedding Generation and Caching ---
# from skills.embedding_skill import EmbeddingSkill # REMOVED
from utils.embedding_cache_store import (
    clear_embedding,
    retrieve_embedding,
    store_embedding,
)
from utils.embedding_generator import generate_embedding_vector  # USE NEW FUNCTION
from utils.logging import configure_logging, extract_request_id, get_pipeline_logger

# embedding_service_streaming = EmbeddingSkill() # REMOVED INSTANCE


async def get_or_create_embedding_for_stream(
    query_text: str, request_id: str
) -> List[float]:
    """Generates an embedding for the query text or retrieves it from cache if available for this request_id."""
    if not query_text:
        return []
    cached_vector = retrieve_embedding(request_id)
    if cached_vector:
        return cached_vector
    logger.info(
        f"STREAM: Embedding cache MISS for request_id: {request_id}. Generating embedding..."
    )
    vector = await generate_embedding_vector(query_text)  # USE NEW FUNCTION
    store_embedding(request_id, vector)
    return vector


# --- End of Additions ---

configure_logging()
logger = get_pipeline_logger("magentic_stream")


def now_iso():
    return datetime.utcnow().isoformat() + "Z"


# Function to deduplicate citations based on document_id or other unique identifiers
def deduplicate_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate citations based on document_id or title if available.

    Args:
        citations: List of citation dictionaries

    Returns:
        List of deduplicated citations
    """
    if not citations:
        return []

    # Track seen items by unique identifier
    seen_ids = set()
    deduplicated = []

    for citation in citations:
        # Determine the unique identifier for this citation
        # Prefer document_id, fallback to id, then title, then use all fields concatenated
        unique_id = citation.get(
            "document_id", citation.get("id", citation.get("title", None))
        )

        # If no suitable unique ID found, create one from all values
        if not unique_id:
            unique_id = "-".join([str(v) for v in citation.values() if v])

        # If we haven't seen this ID before, add it to the results
        if unique_id not in seen_ids:
            seen_ids.add(unique_id)
            deduplicated.append(citation)

    logger.info(
        f"Citations deduplication: {len(citations)} input → {len(deduplicated)} output"
    )
    return deduplicated


# Renamed helper to be more generic
async def _put_event_on_queue(
    target_queue: asyncio.Queue, event_name: str, request_id: str, **kwargs
):
    payload = {
        "event": event_name,
        "timestamp": now_iso(),
        "request_id": request_id,
        **kwargs,
    }
    await target_queue.put(json.dumps(payload))
    logger.info(
        kwargs.get("message", event_name),
        extra={"extra_payload": payload, "request_id": request_id},
    )


async def magentic_ask_stream(prompt: str, request_id: str | None = None, request=None):
    # Queue for events from agent callbacks (make_streaming_callback)
    internal_event_queue = asyncio.Queue()
    # Queue for events to be sent to the SSE client
    client_event_queue = asyncio.Queue()

    streaming_callback_for_agents = make_streaming_callback(internal_event_queue)

    if not request_id and request is not None:
        request_id = extract_request_id(request)
    if not request_id:
        import uuid

        request_id = str(uuid.uuid4())

    all_citations_for_request = []

    async def orchestrate_and_process_events():
        nonlocal all_citations_for_request  # Allow modification from nested consumer

        # --- ADDED: Query Rewriting, Embedding Generation and Task String Construction ---
        original_user_prompt = prompt  # Store original prompt
        rewritten_query = original_user_prompt  # Default to original
        agent_task = original_user_prompt  # Default task if rewrite/embedding fails

        try:
            # --- Initialize Kernel for Query Rewriting ---
            kernel = Kernel()
            openai_model_env = os.getenv("OPENAI_MODEL")  # Renamed to avoid conflict
            openai_api_key_env = os.getenv(
                "OPENAI_API_KEY"
            )  # Renamed to avoid conflict
            if not openai_model_env or not openai_api_key_env:
                raise RuntimeError(
                    "OPENAI_MODEL or OPENAI_API_KEY environment variable is not set for skill execution in stream"
                )

            kernel.add_service(
                OpenAIChatCompletion(
                    ai_model_id=openai_model_env, api_key=openai_api_key_env
                ),
            )

            # --- Rewrite User Prompt ---
            logging.info(
                f"STREAM: Rewriting query for request_id: {request_id}. Original: '{original_user_prompt}'"
            )
            # Assuming this file (streaming.py) is in bestuurai-agentic/src/api/
            current_dir = os.path.dirname(os.path.abspath(__file__))
            skills_base_path = os.path.join(
                current_dir, "..", "skills"
            )  # Path to the 'skills' directory

            prompt_file_path = os.path.join(
                skills_base_path,
                "query_rewriting_skill",
                "QueryRewriteFunction",
                "skprompt.txt",
            )
            config_file_path = os.path.join(
                skills_base_path,
                "query_rewriting_skill",
                "QueryRewriteFunction",
                "config.json",
            )

            with open(prompt_file_path, "r", encoding="utf-8") as f:
                prompt_template_str = (
                    f.read()
                )  # Renamed to avoid conflict with prompt variable
            with open(config_file_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            prompt_config = PromptTemplateConfig(
                template=prompt_template_str,
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

            rewrite_args = KernelArguments(question=original_user_prompt)
            rewrite_result = await kernel.invoke(query_rewrite_fn, rewrite_args)

            if rewrite_result and rewrite_result.value:
                rewritten_query_text = str(rewrite_result.value).strip()
                if rewritten_query_text:
                    rewritten_query = rewritten_query_text
                    logging.info(
                        f"STREAM: Rewritten query for request_id: {request_id}: '{rewritten_query}'"
                    )
                else:
                    logging.warning(
                        f"STREAM: Query rewrite for request_id: {request_id} resulted in empty string. Using original query."
                    )
            else:
                logging.warning(
                    f"STREAM: Query rewrite for request_id: {request_id} failed or returned None. Using original query."
                )

        except Exception as e:
            logging.error(
                f"STREAM ERROR: Failed during query rewriting for {request_id}: {e}",
                exc_info=True,
            )
            # Fallback to original_user_prompt is already handled by rewritten_query default

        # --- Embedding Generation using rewritten_query ---
        try:
            logger.info(
                f"STREAM: Attempting to generate/cache embedding for request_id: {request_id} for query: '{rewritten_query[:50]}...'"
            )
            # Generate/retrieve embedding using the (potentially) rewritten query
            _ = await get_or_create_embedding_for_stream(rewritten_query, request_id)
            # The vector is now in the shared cache, accessible by request_id

            # Construct the task string for the agent using the (potentially) rewritten_query
            agent_task = f"User query: {rewritten_query} Request ID: {request_id}"
            logger.info(f"STREAM: Constructed agent task for Magentic: {agent_task}")

        except Exception as e:
            logger.error(
                f"STREAM ERROR: Failed to generate/cache embedding for {request_id} (using query: '{rewritten_query}'): {e}",
                exc_info=True,
            )
            # If embedding fails, agent_task will use the original prompt (or rewritten if that part succeeded)
            # Ensure agent_task is sensible: if rewritten_query failed, it's original_user_prompt.
            # If embedding failed after successful rewrite, it uses rewritten_query.
            # This is complex, ensure agent_task is consistently what we intend.
            # For now, if embedding fails, it will use the last value of rewritten_query.
            # If rewrite also failed, that is original_user_prompt.
            agent_task = f"User query: {rewritten_query} Request ID: {request_id}"  # Re-affirm task string
        # --- END Embedding Generation and Task Construction ---

        # Task to consume from internal_event_queue, process, and forward to client_event_queue
        async def consume_internal_events():
            while True:
                item_json_str = await internal_event_queue.get()
                data = json.loads(item_json_str)

                if data.get("event") == "citations_found":
                    if "citations" in data and isinstance(data["citations"], list):
                        all_citations_for_request.extend(data["citations"])
                    logger.info(
                        f"INTERNAL: Accumulated citations: {len(all_citations_for_request)}"
                    )
                    internal_event_queue.task_done()
                    continue  # Do not forward this internal event to client_event_queue

                # Forward other events (e.g., "thought") to the client_event_queue
                if data.get("event") == "thought":
                    logger.info(
                        f"INTERNAL: Forwarding thought to client queue: {item_json_str}"
                    )
                await client_event_queue.put(item_json_str)

                # Check for special marker if this queue should stop processing
                if data.get("event") == "done_internal_processing_signal":
                    logger.info(
                        "INTERNAL: consume_internal_events received done signal."
                    )
                    internal_event_queue.task_done()
                    break
                internal_event_queue.task_done()

        consumer_task = asyncio.create_task(consume_internal_events())

        try:
            t0 = datetime.utcnow()
            await _put_event_on_queue(
                client_event_queue,
                "system",
                request_id=request_id,
                step="received",
                message="Request received",
            )

            t_agents = datetime.utcnow()
            await _put_event_on_queue(
                client_event_queue,
                "system",
                request_id=request_id,
                step="init_agents",
                message="Initializing agents...",
            )
            agents_list = await agents()
            await _put_event_on_queue(
                client_event_queue,
                "system",
                request_id=request_id,
                step="init_agents_done",
                message="Agents initialized",
                duration_ms=int((datetime.utcnow() - t_agents).total_seconds() * 1000),
            )

            t_orch = datetime.utcnow()
            await _put_event_on_queue(
                client_event_queue,
                "system",
                request_id=request_id,
                step="start_orchestration",
                message="Starting orchestration...",
            )

            # Pass client_event_queue for MagenticManager's direct progress updates
            async def manager_event_callback(event_name, **kwargs_cb):
                await _put_event_on_queue(
                    client_event_queue, event_name, request_id=request_id, **kwargs_cb
                )

            magentic_orch = await create_magentic_orchestration(
                agents_list,
                streaming_callback_for_agents,  # This feeds internal_event_queue
                event_callback=manager_event_callback,  # This feeds client_event_queue directly
            )
            runtime = InProcessRuntime()
            runtime.start()

            orchestration_result = await magentic_orch.invoke(
                task=agent_task,  # MODIFIED: Use the potentially enriched agent_task
                runtime=runtime,
            )
            await _put_event_on_queue(
                client_event_queue,
                "system",
                request_id=request_id,
                step="orchestration_started",
                message="Orchestration started",
                duration_ms=int((datetime.utcnow() - t_orch).total_seconds() * 1000),
            )

            t_answer = datetime.utcnow()
            await _put_event_on_queue(
                client_event_queue,
                "system",
                request_id=request_id,
                step="waiting_for_result",
                message="Waiting for result...",
            )
            value = (
                await orchestration_result.get()
            )  # Final result from MagenticManager
            await _put_event_on_queue(
                client_event_queue,
                "system",
                request_id=request_id,
                step="result_ready",
                message="Result ready",
                duration_ms=int((datetime.utcnow() - t_answer).total_seconds() * 1000),
            )

            # Stream MagenticManager's final answer tokens to client_event_queue
            answer_text = getattr(value, "content", str(value))
            for token in answer_text:
                await _put_event_on_queue(
                    client_event_queue, "token", request_id=request_id, text=token
                )
                await asyncio.sleep(
                    0.005
                )  # Adjusted sleep for potentially faster streaming

            # Orchestration is done, now prepare and send the final "done" event with citations
            done_payload_dict = {
                "event": "done",
                "timestamp": now_iso(),
                "request_id": request_id,
                "total_duration_ms": int(
                    (datetime.utcnow() - t0).total_seconds() * 1000
                ),
            }
            if all_citations_for_request:
                # Apply deduplication to citations before including them
                deduplicated_citations = deduplicate_citations(
                    all_citations_for_request
                )
                answer_obj = {"citations": deduplicated_citations}
                # If frontend expects other meta, it should be added to answer_obj here
                # e.g., follow_up = getattr(value, "metadata", {}).get("meta", {}).get("follow_up")
                # if follow_up: answer_obj.setdefault("meta", {})["follow_up"] = follow_up
                done_payload_dict["answer_json"] = json.dumps(answer_obj)

            await client_event_queue.put(json.dumps(done_payload_dict))

        except Exception as e:
            logger.error(f"Error in orchestrate_and_process_events: {e}", exc_info=True)
            # Ensure a done event is sent even if an error occurs
            error_done_payload = {
                "event": "done",
                "error": str(e),
                "timestamp": now_iso(),
                "request_id": request_id,
                "total_duration_ms": int(
                    (datetime.utcnow() - t0).total_seconds() * 1000
                    if "t0" in locals()
                    else 0
                ),
            }
            await client_event_queue.put(json.dumps(error_done_payload))
        finally:
            # Signal internal consumer to stop & wait for it
            logger.info(
                "INTERNAL: Sending done_internal_processing_signal to internal_event_queue"
            )
            await internal_event_queue.put(
                json.dumps({"event": "done_internal_processing_signal"})
            )
            await consumer_task
            logger.info("INTERNAL: consumer_task finished.")
            if "runtime" in locals() and hasattr(runtime, "stop_when_idle"):
                await runtime.stop_when_idle()
                logger.info("Runtime stopped.")
            # --- ADDED: Clear embedding from cache in finally block ---
            clear_embedding(request_id)
            logger.info(
                f"STREAM: Cleared embedding cache for request_id: {request_id} in finally block."
            )
            # --- END ADDED ---

    # Launch the main orchestration and event processing task in the background
    asyncio.create_task(orchestrate_and_process_events())

    # SSE response generator that reads from client_event_queue
    async def sse_response():
        while True:
            msg = await client_event_queue.get()
            yield f"data: {msg}\n\n"
            if json.loads(msg).get("event") == "done":
                client_event_queue.task_done()
                break  # Stop SSE after "done" event
            client_event_queue.task_done()

    return StreamingResponse(sse_response(), media_type="text/event-stream")
