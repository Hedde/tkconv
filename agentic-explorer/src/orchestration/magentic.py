"""Magentic orchestration configuration and management."""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from orchestration.constants import (
    DEFAULT_MAX_RESET_COUNT,
    DEFAULT_MAX_ROUND_COUNT,
    DEFAULT_MAX_STALL_COUNT,
    SystemSteps,
)
from pydantic import PrivateAttr
from semantic_kernel.agents import Agent, MagenticOrchestration
from semantic_kernel.agents.orchestration.magentic import StandardMagenticManager
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template.kernel_prompt_template import KernelPromptTemplate
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig
from utils.identity import SYSTEM_IDENTITY

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(filename: str) -> str:
    """Load a prompt template from file."""
    prompt_path = PROMPTS_DIR / filename

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8")


class ObservableMagenticManager(StandardMagenticManager):
    """Enhanced Magentic manager with event streaming capabilities."""

    _event_callback: Optional[callable] = PrivateAttr(default=None)

    def __init__(self, *args, event_callback: Optional[callable] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_callback = event_callback

    async def _emit_event(
        self, event_type: str, step: str, message: str, **kwargs
    ) -> None:
        """Emit an event if callback is configured."""
        if self._event_callback:
            await self._event_callback(event_type, step=step, message=message, **kwargs)

    async def plan(self, magentic_context) -> any:
        """Plan agent execution with progress tracking."""
        await self._emit_event(
            SystemSteps.PLANNING,
            SystemSteps.PLANNING,
            "Analyseren welke specialisten nodig zijn...",
        )

        result = await super().plan(magentic_context)

        await self._emit_event(
            SystemSteps.PLANNING_DONE,
            SystemSteps.PLANNING_DONE,
            "Plan klaar - juiste specialisten worden ingezet",
        )

        return result

    async def create_progress_ledger(self, magentic_context) -> any:
        """Create progress ledger with tracking."""
        await self._emit_event(
            SystemSteps.PROGRESS_LEDGER,
            SystemSteps.PROGRESS_LEDGER,
            "Evalueren of alle benodigde informatie verzameld is...",
        )

        result = await super().create_progress_ledger(magentic_context)

        await self._emit_event(
            SystemSteps.PROGRESS_LEDGER_DONE,
            SystemSteps.PROGRESS_LEDGER_DONE,
            "Alle informatie compleet - antwoord wordt voorbereid",
        )

        return result

    async def prepare_final_answer(self, magentic_context) -> ChatMessageContent:
        """Prepare final answer with tracking."""
        await self._emit_event(
            SystemSteps.FINALIZING, SystemSteps.FINALIZING, "Antwoord aan het afronden"
        )

        prompt_template = KernelPromptTemplate(
            prompt_template_config=PromptTemplateConfig(
                template=self.final_answer_prompt
            )
        )

        args = KernelArguments(
            task=magentic_context.task,
            system_identity=SYSTEM_IDENTITY,
            current_date=datetime.now().strftime("%Y-%m-%d"),
        )

        magentic_context.chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=await prompt_template.render(Kernel(), args),
            )
        )

        response = await self.chat_completion_service.get_chat_message_content(
            magentic_context.chat_history,
            self.prompt_execution_settings,
        )

        if response is None:
            raise RuntimeError("Failed to generate final answer")

        return response

    async def _create_agent_response(self, magentic_context) -> any:
        """Create agent response with selection tracking."""
        await self._emit_event(
            SystemSteps.AGENT_SELECTION,
            SystemSteps.AGENT_SELECTION,
            "Agent aan het selecteren voor taak",
        )

        result = await super()._create_agent_response(magentic_context)

        if hasattr(result, "name") and result.name:
            await self._emit_event(
                SystemSteps.AGENT_SELECTED,
                SystemSteps.AGENT_SELECTED,
                f"Agent {result.name} geselecteerd",
                agent=result.name,
            )

        return result

    async def _evaluate_completion(self, magentic_context) -> bool:
        """Evaluate completion with status tracking."""
        await self._emit_event(
            SystemSteps.EVALUATING_COMPLETION,
            SystemSteps.EVALUATING_COMPLETION,
            "Evalueren of taak voltooid is",
        )

        result = await super()._evaluate_completion(magentic_context)

        completion_status = "voltooid" if result else "nog niet voltooid"
        await self._emit_event(
            SystemSteps.COMPLETION_EVALUATED,
            SystemSteps.COMPLETION_EVALUATED,
            f"Taak status: {completion_status}",
            is_complete=result,
        )

        return result

    async def _select_next_speaker(self, magentic_context) -> any:
        """Select next speaker with tracking."""
        await self._emit_event(
            SystemSteps.SELECTING_SPEAKER,
            SystemSteps.SELECTING_SPEAKER,
            "Volgende spreker aan het selecteren",
        )

        result = await super()._select_next_speaker(magentic_context)

        if result:
            speaker_name = getattr(result, "name", "Onbekende agent")
            await self._emit_event(
                SystemSteps.SPEAKER_SELECTED,
                SystemSteps.SPEAKER_SELECTED,
                f"Volgende spreker: {speaker_name}",
                speaker=speaker_name,
            )

        return result


def _get_openai_credentials() -> tuple[str, str]:
    """Get OpenAI credentials from environment."""
    openai_model = os.getenv("OPENAI_MODEL")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_model:
        raise RuntimeError("OPENAI_MODEL environment variable is not set")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    return openai_model, openai_api_key


async def create_magentic_orchestration(
    agents: List[Agent],
    agent_response_callback: callable,
    event_callback: Optional[callable] = None,
    max_round_count: int = DEFAULT_MAX_ROUND_COUNT,
    max_reset_count: int = DEFAULT_MAX_RESET_COUNT,
    max_stall_count: int = DEFAULT_MAX_STALL_COUNT,
) -> MagenticOrchestration:
    """
    Create a configured MagenticOrchestration instance.

    Args:
        agents: List of agents to orchestrate
        agent_response_callback: Callback for agent responses
        event_callback: Optional callback for system events
        max_round_count: Maximum orchestration rounds
        max_reset_count: Maximum resets allowed
        max_stall_count: Maximum stalls allowed

    Returns:
        Configured MagenticOrchestration instance

    Raises:
        RuntimeError: If configuration fails
    """
    try:
        manager_cls = (
            ObservableMagenticManager if event_callback else StandardMagenticManager
        )
        manager_kwargs = {"event_callback": event_callback} if event_callback else {}

        openai_model, openai_api_key = _get_openai_credentials()

        final_answer_prompt = load_prompt("final_answer_prompt.txt")
        progress_ledger_prompt = load_prompt("progress_ledger_prompt.txt")

        manager_instance = manager_cls(
            chat_completion_service=OpenAIChatCompletion(
                ai_model_id=openai_model,
                api_key=openai_api_key,
            ),
            final_answer_prompt=final_answer_prompt,
            progress_ledger_prompt=progress_ledger_prompt,
            max_round_count=max_round_count,
            max_reset_count=max_reset_count,
            max_stall_count=max_stall_count,
            **manager_kwargs,
        )

        return MagenticOrchestration(
            members=agents,
            manager=manager_instance,
            agent_response_callback=agent_response_callback,
        )

    except Exception as e:
        raise RuntimeError(f"Failed to create Magentic orchestration: {e}") from e
