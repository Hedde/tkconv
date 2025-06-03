import json
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from semantic_kernel.agents import MagenticOrchestration
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig

from api.streaming import deduplicate_citations, magentic_ask_stream
from orchestration.agents import agents
from orchestration.callbacks import agent_response_callback
from orchestration.magentic import ObservableMagenticManager, load_prompt

# Import new embedding and cache utilities
from utils.embedding_cache_store import clear_embedding, get_or_create_embedding
from utils.logging import extract_request_id

router = APIRouter()


class PromptRequest(BaseModel):
    prompt: str
    request_id: str | None = None


@router.post("/magentic/ask")
async def magentic_ask(request: Request, body: PromptRequest):
    # Determine request_id and user_prompt
    request_id = body.request_id or extract_request_id(request)
    user_prompt = body.prompt

    # --- Initialize Kernel for Query Rewriting ---
    kernel = Kernel()
    # Assuming OPENAI_MODEL and OPENAI_API_KEY are set for the main agent's chat completion
    # We can reuse them for the skill's completion service if appropriate, or use a different one.
    # For simplicity, using the same one here. Adjust if a different model/key is needed for the skill.
    openai_model = os.getenv("OPENAI_MODEL")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_model or not openai_api_key:
        # Already checked later, but good to be explicit if skill needs it
        raise RuntimeError(
            "OPENAI_MODEL or OPENAI_API_KEY environment variable is not set for skill execution"
        )

    kernel.add_service(
        OpenAIChatCompletion(ai_model_id=openai_model, api_key=openai_api_key),
    )

    # --- Rewrite User Prompt ---
    rewritten_query = user_prompt  # Default to original if rewrite fails
    try:
        logging.info(
            f"Endpoint /magentic/ask: Rewriting query for request_id: {request_id}. Original: '{user_prompt}'"
        )

        prompt_file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "skills",
            "query_rewriting_skill",
            "QueryRewriteFunction",
            "skprompt.txt",
        )
        config_file_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "skills",
            "query_rewriting_skill",
            "QueryRewriteFunction",
            "config.json",
        )

        with open(prompt_file_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        prompt_config = PromptTemplateConfig(
            template=prompt_template,
            name="QueryRewriteFunction",
            description=config_data["description"],
            template_format="semantic-kernel",
            input_variables=[
                # Manually construct based on your config.json structure
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

        rewrite_args = KernelArguments(question=user_prompt)
        rewrite_result = await kernel.invoke(query_rewrite_fn, rewrite_args)

        # Ensure rewrite_result and its value are not None before stripping
        if rewrite_result and rewrite_result.value:
            rewritten_query_text = str(rewrite_result.value).strip()
            if rewritten_query_text:  # Check if not empty after stripping
                rewritten_query = rewritten_query_text
                logging.info(
                    f"Endpoint /magentic/ask: Rewritten query for request_id: {request_id}: '{rewritten_query}'"
                )
            else:
                logging.warning(
                    f"Endpoint /magentic/ask: Query rewrite for request_id: {request_id} resulted in empty string. Using original query."
                )
        else:
            logging.warning(
                f"Endpoint /magentic/ask: Query rewrite for request_id: {request_id} failed or returned None. Using original query."
            )

    except Exception as e:
        logging.error(
            f"Endpoint /magentic/ask: ERROR during query rewriting for request_id {request_id}: {e}",
            exc_info=True,
        )
        # Fallback to original user_prompt is already handled by rewritten_query default
    # --- End of Query Rewriting ---

    # --- Generate and cache embedding ---
    try:
        # print(f"Endpoint /magentic/ask: Attempting to generate/cache embedding for request_id: {request_id}")
        # Using logger for consistency
        logging.info(
            f"Endpoint /magentic/ask: Attempting to generate/cache embedding for request_id: {request_id} using query: '{rewritten_query}'"
        )
        query_vector = await get_or_create_embedding(
            rewritten_query, request_id
        )  # Use rewritten_query
        if not query_vector:
            logging.warning(
                f"Endpoint /magentic/ask: Failed to generate query_vector for request_id: {request_id}"
            )
    except Exception as e:
        logging.error(
            f"Endpoint /magentic/ask: ERROR generating or caching embedding for request_id {request_id}: {e}",
            exc_info=True,
        )
        # Fall through, agent might handle lack of vector if search tool is robust
    # --- End of Embedding Generation ---

    agents_list = await agents()

    magentic_orch = MagenticOrchestration(
        members=agents_list,
        manager=ObservableMagenticManager(
            chat_completion_service=OpenAIChatCompletion(
                ai_model_id=openai_model, api_key=openai_api_key
            ),
            final_answer_prompt=load_prompt("final_answer_prompt.txt"),
            # Optimized recursion limits based on log analysis - agent finds data but needs more rounds to present properly
            max_round_count=6,  # Increased to 6 - agent finds data successfully but needs more rounds for comprehensive answers
            max_reset_count=1,  # Reduced to 1 - resets were happening too aggressively when agent found valid but limited data  
            max_stall_count=3,  # Increased to 3 - allow more tolerance when agent is processing found data
        ),
        agent_response_callback=agent_response_callback,
    )
    runtime = InProcessRuntime()
    runtime.start()

    # --- Construct task string with user_prompt and request_id ---
    agent_task = (
        f"User query: {rewritten_query} Request ID: {request_id}"  # Use rewritten_query
    )
    logging.info(
        f"Endpoint /magentic/ask: Constructed agent task for Magentic: {agent_task}"
    )
    # --- End of Task Construction ---

    orchestration_result = await magentic_orch.invoke(
        task=agent_task,  # Pass the combined string
        runtime=runtime,
    )
    value = await orchestration_result.get()
    await runtime.stop_when_idle()

    # --- Clear embedding from cache ---
    clear_embedding(request_id)
    # --- End of Cache Clearing ---

    result_text = getattr(value, "content", str(value))
    logging.getLogger("pipeline.magentic").info(
        f"Endpoint /magentic/ask: Request completed for request_id: {request_id}"
    )
    return JSONResponse({"result": result_text, "request_id": request_id})


@router.post("/magentic/ask/stream")
async def magentic_ask_stream_endpoint(request: Request, body: PromptRequest):
    request_id = body.request_id or extract_request_id(request)
    return await magentic_ask_stream(
        body.prompt, request_id=request_id, request=request
    )
