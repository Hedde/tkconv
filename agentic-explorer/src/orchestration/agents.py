"""Agent factory for parliamentary data analysis."""

import logging
from typing import Awaitable, Callable, List, Optional

from agents.case_agent import create_case_agent
from agents.document_agent import create_document_agent
from agents.person_agent import create_person_agent
from agents.voting_agent import create_voting_agent
from orchestration.callbacks import tool_call_debug_handler
from semantic_kernel.agents import Agent
from semantic_kernel.contents.chat_message_content import ChatMessageContent

logger = logging.getLogger(__name__)


async def create_agent_list(
    on_intermediate_message: Optional[
        Callable[[ChatMessageContent], Awaitable[None]]
    ] = None,
) -> List[Agent]:
    """
    Create the list of specialized agents for parliamentary data analysis.

    Args:
        on_intermediate_message: Optional callback for intermediate agent messages

    Returns:
        List of configured agents ready for orchestration

    Raises:
        RuntimeError: If agent creation fails
    """
    try:
        logger.info("Creating specialized parliamentary data agents")

        # Create all specialized agents
        person_agent = await create_person_agent(
            on_intermediate_message=on_intermediate_message or tool_call_debug_handler
        )

        document_agent = await create_document_agent(
            on_intermediate_message=on_intermediate_message or tool_call_debug_handler
        )

        voting_agent = await create_voting_agent(
            on_intermediate_message=on_intermediate_message or tool_call_debug_handler
        )

        case_agent = await create_case_agent(
            on_intermediate_message=on_intermediate_message or tool_call_debug_handler
        )

        agents_list = [person_agent, document_agent, voting_agent, case_agent]
        logger.info(
            f"Successfully created {len(agents_list)} specialized agent(s): {[agent.name for agent in agents_list]}"
        )

        return agents_list

    except Exception as e:
        logger.error(f"Failed to create agents: {e}", exc_info=True)
        raise RuntimeError(f"Agent creation failed: {e}") from e


async def agents() -> List[Agent]:
    """
    Factory function for creating the default specialized agent configuration.

    Returns:
        List of specialized agents with default configuration
    """
    return await create_agent_list()
