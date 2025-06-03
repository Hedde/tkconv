# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import os

import uvicorn

# FastAPI imports
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from semantic_kernel.agents import (
    Agent,
    ChatCompletionAgent,
    MagenticOrchestration,
    OpenAIAssistantAgent,
)
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.contents import ChatMessageContent

from api.endpoints import router
from orchestration.magentic import ObservableMagenticManager, load_prompt
from utils.logging import configure_logging, extract_request_id

# --- Embedding utilities are now in their respective utils/ files ---
# import hashlib # No longer needed here
# from utils.embedding_cache_store import store_embedding, retrieve_embedding, clear_embedding, get_or_create_embedding # No longer needed here
# from utils.embedding_generator import generate_embedding_vector # No longer needed here
# from typing import List # No longer needed here

# Global or per-application embedding service # REMOVED INSTANCE
# embedding_service = EmbeddingSkill()

# async def get_or_create_embedding(query_text: str, request_id: str) -> List[float]: # REMOVED
#     """Generates an embedding for the query text or retrieves it from cache if available for this request_id."""
#     if not query_text:
#         return []
#
#     cached_vector = retrieve_embedding(request_id)
#     if cached_vector:
#         # print(f"Embedding cache HIT for request_id: {request_id}") # Logging done in store
#         return cached_vector
#
#     print(f"Embedding cache MISS for request_id: {request_id}. Generating embedding for query: '{query_text[:50]}...'")
#     vector = await generate_embedding_vector(query_text) # USE NEW FUNCTION
#     store_embedding(request_id, vector)
#     # print(f"Stored embedding for request_id: {request_id}") # Logging done in store
#     return vector
#
# def clear_embedding_cache_for_request(request_id: str): # Moved to embedding_cache_store
#     """Clears the embedding from cache for a given request_id after processing is complete."""
#     if request_id in embedding_cache_by_request_id:
#         del embedding_cache_by_request_id[request_id]
#         print(f"Cleared embedding cache for request_id: {request_id}")
# --- End of Additions ---

"""
The following sample demonstrates how to create a Magentic orchestration with two agents:
- A Research agent that can perform web searches
- A Coder agent that can run code using the code interpreter

Read more about Magentic here:
https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/

This sample demonstrates the basic steps of creating and starting a runtime, creating
a Magentic orchestration with two agents and a Magentic manager, invoking the
orchestration, and finally waiting for the results.

The Magentic manager requires a chat completion model that supports structured output.
"""

configure_logging()


async def agents() -> list[Agent]:
    """Return a list of agents that will participate in the Magentic orchestration.

    Feel free to add or remove agents.
    """
    research_agent = ChatCompletionAgent(
        name="ResearchAgent",
        description="A helpful assistant with access to web search. Ask it to perform web searches.",
        instructions=(
            "You are a Researcher. You find information without additional computation or quantitative analysis."
        ),
        # This agent requires the gpt-4o-search-preview model to perform web searches.
        # Feel free to explore with other agents that support web search, for example,
        # the `OpenAIResponseAgent` or `AzureAIAgent` with bing grounding.
        service=OpenAIChatCompletion(ai_model_id="gpt-4o-search-preview"),
    )

    # Get model and API key from environment
    openai_model = os.getenv("OPENAI_MODEL")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_model:
        raise RuntimeError("OPENAI_MODEL environment variable is not set")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    # Create an OpenAI Assistant agent with code interpreter capability
    client, model = OpenAIAssistantAgent.setup_resources(
        ai_model_id=openai_model,
        api_key=openai_api_key,
    )
    code_interpreter_tool, code_interpreter_tool_resources = (
        OpenAIAssistantAgent.configure_code_interpreter_tool()
    )
    definition = await client.beta.assistants.create(
        model=model,
        name="CoderAgent",
        description="A helpful assistant that writes and executes code to process and analyze data.",
        instructions="You solve questions using code. Please provide detailed analysis and computation process.",
        tools=code_interpreter_tool,
        tool_resources=code_interpreter_tool_resources,
    )
    coder_agent = OpenAIAssistantAgent(
        client=client,
        definition=definition,
    )

    return [research_agent, coder_agent]


def agent_response_callback(message: ChatMessageContent) -> None:
    """Observer function to print the messages from the agents."""
    print(f"**{message.name}**\n{message.content}")


async def main():
    """Main function to run the agents."""
    # 1. Create a Magentic orchestration with two agents and a Magentic manager
    # Note, the Standard Magentic manager uses prompts that have been tuned very
    # carefully but it accepts custom prompts for advanced users and scenarios.
    # For even more advanced scenarios, you can subclass the MagenticManagerBase
    # and implement your own manager logic.
    # The standard manager also requires a chat completion model that supports
    # structured output.

    # Get OpenAI credentials with strict checking
    openai_model = os.getenv("OPENAI_MODEL")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_model:
        raise RuntimeError("OPENAI_MODEL environment variable is not set")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    magentic_orchestration = MagenticOrchestration(
        members=await agents(),
        manager=ObservableMagenticManager(
            chat_completion_service=OpenAIChatCompletion(
                ai_model_id=openai_model,
                api_key=openai_api_key,
            ),
            final_answer_prompt=load_prompt("final_answer_prompt.txt"),
            # Optimized recursion limits based on log analysis - agent finds data but needs more rounds to present properly
            max_round_count=6,  # Increased to 6 - agent finds data successfully but needs more rounds for comprehensive answers
            max_reset_count=1,  # Reduced to 1 - resets were happening too aggressively when agent found valid but limited data  
            max_stall_count=3,  # Increased to 3 - allow more tolerance when agent is processing found data
        ),
        agent_response_callback=agent_response_callback,
    )

    # 2. Create a runtime and start it
    runtime = InProcessRuntime()
    runtime.start()

    # 3. Invoke the orchestration with a task and the runtime
    orchestration_result = await magentic_orchestration.invoke(
        task=(
            "I am preparing a report on the energy efficiency of different machine learning model architectures. "
            "Compare the estimated training and inference energy consumption of ResNet-50, BERT-base, and GPT-2 "
            "on standard datasets (e.g., ImageNet for ResNet, GLUE for BERT, WebText for GPT-2). "
            "Then, estimate the CO2 emissions associated with each, assuming training on an Azure Standard_NC6s_v3 VM "
            "for 24 hours. Provide tables for clarity, and recommend the most energy-efficient model "
            "per task type (image classification, text classification, and text generation)."
        ),
        runtime=runtime,
    )

    # 4. Wait for the results
    value = await orchestration_result.get()

    print(f"\nFinal result:\n{value}")

    # 5. Stop the runtime when idle
    await runtime.stop_when_idle()

    """
    Sample output:
    **ResearchAgent**
    Estimating the energy consumption and associated CO₂ emissions for training and inference of ResNet-50, BERT-base...

    **CoderAgent**
    Here is the comparison of energy consumption and CO₂ emissions for each model (ResNet-50, BERT-base, and GPT-2)
    over a 24-hour period:

    | Model     | Training Energy (kWh) | Inference Energy (kWh) | Total Energy (kWh) | CO₂ Emissions (kg) |
    |-----------|------------------------|------------------------|---------------------|---------------------|
    | ResNet-50 | 21.11                  | 0.08232                | 21.19232            | 19.50               |
    | BERT-base | 0.048                  | 0.23736                | 0.28536             | 0.26                |
    | GPT-2     | 42.22                  | 0.35604                | 42.57604            | 39.17               |

    ### Recommendations:
    ...

    **CoderAgent**
    Here are the recalibrated results for energy consumption and CO₂ emissions, assuming a more conservative approach
    for models like GPT-2:

    | Model            | Training Energy (kWh) | Inference Energy (kWh) | Total Energy (kWh) | CO₂ Emissions (kg) |
    |------------------|------------------------|------------------------|---------------------|---------------------|
    | ResNet-50        | 21.11                  | 0.08232                | 21.19232            | 19.50               |
    | BERT-base        | 0.048                  | 0.23736                | 0.28536             | 0.26                |
    | GPT-2 (Adjusted) | 42.22                  | 0.35604                | 42.57604            | 39.17               |

    ...

    **ResearchAgent**
    Estimating the energy consumption and associated CO₂ emissions for training and inference of machine learning ...

    **ResearchAgent**
    Estimating the energy consumption and CO₂ emissions of training and inference for ResNet-50, BERT-base, and ...

    **CoderAgent**
    Here is the estimated energy use and CO₂ emissions for a full day of operation for each model on an Azure ...

    **ResearchAgent**
    Recent analyses have highlighted the substantial energy consumption and carbon emissions associated with ...

    **CoderAgent**
    Here's the refined estimation for the energy use and CO₂ emissions for optimized models on an Azure ...

    **CoderAgent**
    To provide precise estimates for CO₂ emissions based on Azure's regional data centers' carbon intensity, we need ...

    **ResearchAgent**
    To refine the CO₂ emission estimates for training and inference of ResNet-50, BERT-base, and GPT-2 on an Azure ...

    **CoderAgent**
    Here's the refined comparative table for energy consumption and CO₂ emissions for ResNet-50, BERT-base, and GPT-2,
    taking into account carbon intensity data for Azure's West Europe and Sweden Central regions:

    | Model      | Energy (kWh) | CO₂ Emissions West Europe (kg) | CO₂ Emissions Sweden Central (kg) |
    |------------|--------------|--------------------------------|-----------------------------------|
    | ResNet-50  | 5.76         | 0.639                          | 0.086                            |
    | BERT-base  | 9.18         | 1.019                          | 0.138                            |
    | GPT-2      | 12.96        | 1.439                          | 0.194                            |

    **Refined Recommendations:**

    ...

    Final result:
    Here is the comprehensive report on energy efficiency and CO₂ emissions for ResNet-50, BERT-base, and GPT-2 models
    when trained and inferred on an Azure Standard_NC6s_v3 VM for 24 hours.

    ### Energy Consumption and CO₂ Emissions:

    Based on refined analyses, here are the estimated energy consumption and CO₂ emissions for each model:

    | Model      | Energy (kWh) | CO₂ Emissions West Europe (kg) | CO₂ Emissions Sweden Central (kg) |
    |------------|--------------|--------------------------------|-----------------------------------|
    | ResNet-50  | 5.76         | 0.639                          | 0.086                            |
    | BERT-base  | 9.18         | 1.019                          | 0.138                            |
    | GPT-2      | 12.96        | 1.439                          | 0.194                            |

    ### Recommendations for Energy Efficiency:

    ...
    """


# FastAPI app
app = FastAPI(title="Magentic Orchestration Demo")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],  # For demo, allow all. Change to ["http://localhost:xxxx"] for production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

# class PromptRequest(BaseModel): # REMOVED - Assuming it was only for the @app.post("/magentic/ask")
#     prompt: str
#     request_id: str | None = None

# @app.post("/magentic/ask") # REMOVED THIS ENTIRE ENDPOINT
# async def magentic_ask(request: Request, body: PromptRequest):
#     ...

# Commenting out duplicate /magentic/ask/stream endpoint to defer to api.endpoints router
# @app.post("/magentic/ask/stream") # THIS CAN BE FULLY REMOVED NOW
# async def magentic_ask_stream(request: PromptRequest):
#     ...


if __name__ == "__main__":
    # Run as web server with uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8888, reload=False)
