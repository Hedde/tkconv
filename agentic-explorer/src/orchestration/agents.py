"""Agent factory for parliamentary data analysis."""

import logging
from typing import Awaitable, Callable, List, Optional

from semantic_kernel.agents import Agent
from semantic_kernel.contents.chat_message_content import ChatMessageContent

from agents.parliamentary_data_agent import create_parliamentary_data_agent
from orchestration.callbacks import tool_call_debug_handler

logger = logging.getLogger(__name__)


async def create_agent_list(
    on_intermediate_message: Optional[
        Callable[[ChatMessageContent], Awaitable[None]]
    ] = None,
) -> List[Agent]:
    """
    Create the list of agents for parliamentary data analysis.

    Args:
        on_intermediate_message: Optional callback for intermediate agent messages

    Returns:
        List of configured agents ready for orchestration

    Raises:
        RuntimeError: If agent creation fails
    """
    try:
        logger.info("Creating parliamentary data agent")

        parliamentary_data_agent = await create_parliamentary_data_agent(
            on_intermediate_message=on_intermediate_message or tool_call_debug_handler
        )

        agents_list = [parliamentary_data_agent]
        logger.info(f"Successfully created {len(agents_list)} agent(s)")

        return agents_list

    except Exception as e:
        logger.error(f"Failed to create agents: {e}", exc_info=True)
        raise RuntimeError(f"Agent creation failed: {e}") from e


async def agents() -> List[Agent]:
    """
    Factory function for creating the default agent configuration.

    Returns:
        List of agents with default configuration
    """
    return await create_agent_list()
