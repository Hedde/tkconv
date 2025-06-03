import os

from semantic_kernel.agents import Agent

from agents.algemene_informatie_agent import create_algemene_informatie_agent
from agents.vergunningen_agent import create_vergunningen_agent
from agents.parliamentary_data_agent import create_parliamentary_data_agent

# from agents.coder_agent import create_coder_agent
# from agents.research_agent import create_research_agent
from orchestration.callbacks import tool_call_debug_handler


async def agents() -> list[Agent]:
    """Return a list of domain-specialized agents that will participate in the Magentic orchestration."""
    # research_agent = await create_research_agent()
    # coder_agent = await create_coder_agent()

    # Create the domain-based agents with the tool call debug handler
    # vergunningen_agent = await create_vergunningen_agent(
    #     on_intermediate_message=tool_call_debug_handler
    # )

    # algemene_informatie_agent = await create_algemene_informatie_agent(
    #     on_intermediate_message=tool_call_debug_handler
    # )

    parliamentary_data_agent = await create_parliamentary_data_agent(
        on_intermediate_message=tool_call_debug_handler
    )

    return [
        parliamentary_data_agent,
        # vergunningen_agent,
        # algemene_informatie_agent,
    ]  # , research_agent]
