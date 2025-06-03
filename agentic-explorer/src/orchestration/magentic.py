import os
from datetime import datetime

from pydantic import PrivateAttr
from semantic_kernel.agents import MagenticOrchestration
from semantic_kernel.agents.orchestration.magentic import StandardMagenticManager
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template.kernel_prompt_template import KernelPromptTemplate
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig

from utils.identity import SYSTEM_IDENTITY


# Helper to load prompt files
def load_prompt(filename):
    path = os.path.join(os.path.dirname(__file__), "prompts", filename)
    with open(path, "r") as f:
        return f.read()


# Observable manager for streaming system/progress events
class ObservableMagenticManager(StandardMagenticManager):
    _event_callback: callable = PrivateAttr()

    def __init__(self, *args, event_callback=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_callback = event_callback

    async def plan(self, magentic_context):
        if self._event_callback:
            await self._event_callback(
                "system",
                step="planning",
                message="Analyseren welke specialisten nodig zijn...",
            )
        result = await super().plan(magentic_context)
        if self._event_callback:
            await self._event_callback(
                "system",
                step="planning_done",
                message="Plan klaar - juiste specialisten worden ingezet",
            )
        return result

    async def create_progress_ledger(self, magentic_context):
        if self._event_callback:
            await self._event_callback(
                "system",
                step="progress_ledger",
                message="Evalueren of alle benodigde informatie verzameld is...",
            )
        result = await super().create_progress_ledger(magentic_context)
        if self._event_callback:
            await self._event_callback(
                "system",
                step="progress_ledger_done",
                message="Alle informatie compleet - antwoord wordt voorbereid",
            )
        return result

    async def prepare_final_answer(self, magentic_context):
        if self._event_callback:
            await self._event_callback(
                "system", step="finalizing", message="Antwoord aan het afronden"
            )
        # Patch: render prompt with SK syntax and KernelArguments
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
        assert response is not None
        return response

    async def _create_agent_response(self, magentic_context):
        """Override to stream agent selection and response details."""
        if self._event_callback:
            await self._event_callback(
                "system",
                step="agent_selection",
                message="Agent aan het selecteren voor taak",
            )

        # Call parent method to get the actual response
        result = await super()._create_agent_response(magentic_context)

        # Try to extract agent information from the result
        if hasattr(result, "name") and result.name:
            agent_name = result.name
            if self._event_callback:
                await self._event_callback(
                    "system",
                    step="agent_selected",
                    message=f"Agent {agent_name} geselecteerd",
                    agent=agent_name,
                )

        return result

    async def _evaluate_completion(self, magentic_context):
        """Override to stream completion evaluation details."""
        if self._event_callback:
            await self._event_callback(
                "system",
                step="evaluating_completion",
                message="Evalueren of taak voltooid is",
            )

        result = await super()._evaluate_completion(magentic_context)

        if self._event_callback:
            completion_status = "voltooid" if result else "nog niet voltooid"
            await self._event_callback(
                "system",
                step="completion_evaluated",
                message=f"Taak status: {completion_status}",
                is_complete=result,
            )

        return result

    async def _select_next_speaker(self, magentic_context):
        """Override to stream next speaker selection."""
        if self._event_callback:
            await self._event_callback(
                "system",
                step="selecting_speaker",
                message="Volgende spreker aan het selecteren",
            )

        result = await super()._select_next_speaker(magentic_context)

        if self._event_callback and result:
            speaker_name = getattr(result, "name", "Onbekende agent")
            await self._event_callback(
                "system",
                step="speaker_selected",
                message=f"Volgende spreker: {speaker_name}",
                speaker=speaker_name,
            )

        return result


# Factory for orchestration, optionally with observable manager
async def create_magentic_orchestration(
    agents, agent_response_callback, event_callback=None
):
    """Create and return a MagenticOrchestration instance. If event_callback is provided, use ObservableMagenticManager."""
    manager_cls = (
        ObservableMagenticManager if event_callback else StandardMagenticManager
    )
    manager_kwargs = {}
    if event_callback:
        manager_kwargs["event_callback"] = event_callback

    # Get OpenAI credentials with strict checking
    openai_model = os.getenv("OPENAI_MODEL")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_model:
        raise RuntimeError("OPENAI_MODEL environment variable is not set")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    # Load custom prompts
    final_answer_prompt = load_prompt("final_answer_prompt.txt")
    progress_ledger_prompt = load_prompt("progress_ledger_prompt.txt")

    # Create manager with recursion limits to prevent infinite loops while allowing Address Intelligence Router flow
    manager_instance = manager_cls(
        chat_completion_service=OpenAIChatCompletion(
            ai_model_id=openai_model,
            api_key=openai_api_key,
        ),
        final_answer_prompt=final_answer_prompt,
        progress_ledger_prompt=progress_ledger_prompt,
        # Optimized recursion limits based on log analysis - agent finds data but needs more rounds to present properly
        max_round_count=4,  # Increased to 4 - ParliamentaryDataAgent needs more rounds for comprehensive database queries
        max_reset_count=1,  # Increased to 1 - allow one reset when data is found but needs refinement  
        max_stall_count=2,  # Increased to 2 - allow more tolerance when agent is processing parliamentary data
        **manager_kwargs,
    )

    # Pass the raw identity string (SK syntax)
    return MagenticOrchestration(
        members=agents,
        manager=manager_instance,
        agent_response_callback=agent_response_callback,
    )
