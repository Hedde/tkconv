import json
import logging
import os
from pathlib import Path
from typing import Optional

from api.streaming import magentic_ask_stream
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from orchestration.agents import agents
from orchestration.callbacks import agent_response_callback
from orchestration.constants import (
    STREAMING_MAX_RESET_COUNT,
    STREAMING_MAX_ROUND_COUNT,
    STREAMING_MAX_STALL_COUNT,
)
from orchestration.magentic import ObservableMagenticManager, load_prompt
from pydantic import BaseModel, Field
from semantic_kernel.agents import MagenticOrchestration
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig
from utils.embedding_cache_store import clear_embedding, get_or_create_embedding
from utils.logging import extract_request_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/magentic", tags=["parliamentary-data"])

# Configuration constants
MAX_ROUND_COUNT = STREAMING_MAX_ROUND_COUNT
MAX_RESET_COUNT = STREAMING_MAX_RESET_COUNT
MAX_STALL_COUNT = STREAMING_MAX_STALL_COUNT
QUERY_REWRITE_SKILL_PATH = (
    Path(__file__).parent.parent
    / "skills"
    / "query_rewriting_skill"
    / "QueryRewriteFunction"
)


class PromptRequest(BaseModel):
    """Request model for parliamentary data queries."""

    prompt: str = Field(
        ..., description="The user's question about parliamentary data", min_length=1
    )
    request_id: Optional[str] = Field(None, description="Optional request tracking ID")


class QueryResponse(BaseModel):
    """Response model for parliamentary data queries."""

    result: str = Field(..., description="The agent's response")
    request_id: str = Field(..., description="Request tracking ID")


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(..., description="Error description")
    detail: Optional[str] = Field(None, description="Additional error details")
    request_id: Optional[str] = Field(None, description="Request tracking ID")


def _get_openai_credentials() -> tuple[str, str]:
    """Get OpenAI credentials from environment variables."""
    openai_model = os.getenv("OPENAI_MODEL")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_model or not openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI credentials not configured",
        )

    return openai_model, openai_api_key


async def _rewrite_query(user_prompt: str, request_id: str) -> str:
    """Rewrite user query using the query rewriting skill."""
    try:
        openai_model, openai_api_key = _get_openai_credentials()

        kernel = Kernel()
        kernel.add_service(
            OpenAIChatCompletion(ai_model_id=openai_model, api_key=openai_api_key)
        )

        # Load query rewriting skill configuration
        prompt_file = QUERY_REWRITE_SKILL_PATH / "skprompt.txt"
        config_file = QUERY_REWRITE_SKILL_PATH / "config.json"

        if not prompt_file.exists() or not config_file.exists():
            logger.warning(
                f"Query rewrite skill not found for request {request_id}, using original query"
            )
            return user_prompt

        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_template = f.read()
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)

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

        rewrite_args = KernelArguments(question=user_prompt)
        rewrite_result = await kernel.invoke(query_rewrite_fn, rewrite_args)

        if rewrite_result and rewrite_result.value:
            rewritten_text = str(rewrite_result.value).strip()
            if rewritten_text:
                logger.info(
                    f"Query rewritten for request {request_id}: '{rewritten_text}'"
                )
                return rewritten_text

        logger.warning(f"Query rewrite failed for request {request_id}, using original")
        return user_prompt

    except Exception as e:
        logger.error(
            f"Error during query rewriting for request {request_id}: {e}", exc_info=True
        )
        return user_prompt


async def _process_embedding(query: str, request_id: str) -> None:
    """Generate and cache embedding for the query."""
    try:
        logger.info(f"Generating embedding for request {request_id}")
        query_vector = await get_or_create_embedding(query, request_id)
        if not query_vector:
            logger.warning(f"Failed to generate embedding for request {request_id}")
    except Exception as e:
        logger.error(
            f"Error generating embedding for request {request_id}: {e}", exc_info=True
        )


async def _create_orchestration(
    openai_model: str, openai_api_key: str
) -> MagenticOrchestration:
    """Create and configure the Magentic orchestration."""
    agents_list = await agents()

    return MagenticOrchestration(
        members=agents_list,
        manager=ObservableMagenticManager(
            chat_completion_service=OpenAIChatCompletion(
                ai_model_id=openai_model, api_key=openai_api_key
            ),
            final_answer_prompt=load_prompt("final_answer_prompt.txt"),
            max_round_count=MAX_ROUND_COUNT,
            max_reset_count=MAX_RESET_COUNT,
            max_stall_count=MAX_STALL_COUNT,
        ),
        agent_response_callback=agent_response_callback,
    )


@router.post(
    "/ask",
    response_model=QueryResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
    },
)
async def ask_parliamentary_data(request: Request, body: PromptRequest) -> JSONResponse:
    """
    Query parliamentary data using AI agents.

    This endpoint processes natural language queries about Dutch parliamentary data
    and returns comprehensive answers using specialized AI agents.
    """
    request_id = body.request_id or extract_request_id(request)

    try:
        logger.info(f"Processing parliamentary data query for request {request_id}")

        # Get OpenAI credentials
        openai_model, openai_api_key = _get_openai_credentials()

        # Rewrite query for better search results
        rewritten_query = await _rewrite_query(body.prompt, request_id)

        # Generate embedding for semantic search
        await _process_embedding(rewritten_query, request_id)

        # Create and run orchestration
        magentic_orch = await _create_orchestration(openai_model, openai_api_key)

        runtime = InProcessRuntime()
        runtime.start()

        try:
            agent_task = f"User query: {rewritten_query} Request ID: {request_id}"
            logger.info(f"Executing agent task for request {request_id}")

            orchestration_result = await magentic_orch.invoke(
                task=agent_task,
                runtime=runtime,
            )

            result = await orchestration_result.get()
            result_text = getattr(result, "content", str(result))

            logger.info(f"Parliamentary data query completed for request {request_id}")

            return JSONResponse({"result": result_text, "request_id": request_id})

        finally:
            await runtime.stop_when_idle()
            clear_embedding(request_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error processing request {request_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process parliamentary data query: {str(e)}",
        )


@router.post("/ask/stream")
async def ask_parliamentary_data_stream(request: Request, body: PromptRequest):
    """
    Query parliamentary data with streaming response.

    This endpoint provides real-time streaming of the AI agent's analysis process,
    allowing clients to see intermediate steps and tool calls.
    """
    request_id = body.request_id or extract_request_id(request)
    logger.info(f"Starting streaming parliamentary data query for request {request_id}")

    return await magentic_ask_stream(
        body.prompt, request_id=request_id, request=request
    )
