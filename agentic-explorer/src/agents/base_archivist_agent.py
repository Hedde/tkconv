import logging
import os
from typing import Any, AsyncIterable, Awaitable, Callable, List, Optional

from semantic_kernel.agents import AgentResponseItem, AgentThread, ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import (
    OpenAIChatCompletion,
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel

from skills.mcp.elastic_mcp_client import ElasticMCPClient


# Create a custom agent class that extends ChatCompletionAgent
class DebugChatCompletionAgent(ChatCompletionAgent):
    """A ChatCompletionAgent that includes a debug callback for function calls."""

    _debug_callback: Optional[Callable[[ChatMessageContent], Awaitable[None]]] = None

    async def invoke(
        self,
        *,
        messages: (
            str | ChatMessageContent | list[str | ChatMessageContent] | None
        ) = None,
        thread: AgentThread | None = None,
        on_intermediate_message: (
            Callable[[ChatMessageContent], Awaitable[None]] | None
        ) = None,
        arguments: KernelArguments | None = None,
        kernel: "Kernel | None" = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseItem[ChatMessageContent]]:
        """Override invoke to include the debug callback if needed."""
        # If no callback is provided but we have a debug callback, use that
        if on_intermediate_message is None and self._debug_callback is not None:
            on_intermediate_message = self._debug_callback

        # Call the parent invoke method without await - it returns an AsyncIterable directly
        async for item in super().invoke(
            messages=messages,
            thread=thread,
            on_intermediate_message=on_intermediate_message,
            arguments=arguments,
            kernel=kernel,
            **kwargs,
        ):
            yield item


class BaseArchivistConfig:
    """Configuration for specialized archivist agents."""

    def __init__(
        self,
        agent_name: str,
        agent_description: str,
        primary_index: str,
        chunks_index: Optional[str] = None,
        embedding_field: str = "embedding_summary",
        chunks_embedding_field: str = "embedding",
        specialization_description: str = "",
        metadata_knowledge: str = "",
        search_strategy: str = "",
        tool_examples: str = "",
    ):
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.primary_index = primary_index
        self.chunks_index = chunks_index
        self.embedding_field = embedding_field
        self.chunks_embedding_field = chunks_embedding_field
        self.specialization_description = specialization_description
        self.metadata_knowledge = metadata_knowledge
        self.search_strategy = search_strategy
        self.tool_examples = tool_examples


async def create_specialized_archivist_agent(
    config: BaseArchivistConfig,
    on_intermediate_message: Optional[
        Callable[[ChatMessageContent], Awaitable[None]]
    ] = None,
) -> ChatCompletionAgent:
    """Create a specialized archivist agent based on the provided configuration."""
    logging.info(f"Creating {config.agent_name}...")

    # Build the chunks information if available
    chunks_info = ""
    if config.chunks_index:
        chunks_info = f"""
• Chunks index: `{config.chunks_index}` (voor gedetailleerde opvolging)
• Embedding field voor chunks: `{config.chunks_embedding_field}`"""

    instructions = f"""
Je bent een expert digitaal archivaris voor de Gemeente Rijswijk.

SPECIALISATIE:
{config.specialization_description}

SPECIALISATIE FOCUS:
Je bent gespecialiseerd in {config.primary_index.split('_')[0].upper()} documenten, maar je kunt alle vragen beantwoorden.
- **Primaire expertise**: {config.specialization_description}
- **Secundaire ondersteuning**: Voor vragen buiten je expertise, probeer toch te helpen maar vermeld je beperkte kennis

TAAK:
Je input bevat een gebruikersvraag en een Request ID, geformatteerd als: "User query: [de gebruikersvraag] Request ID: [het_request_id]".
1. Extraheer de "gebruikersvraag" en "Request ID"
2. Bepaal of de vraag binnen je primaire expertise valt
3. Gebruik de `ElasticMCPClient.search` tool om relevante documenten te zoeken
4. Geef ALTIJD een antwoord, ook als je niets vindt

ZOEKSTRATEGIE (alleen bij relevante vragen):
• Primaire index: `{config.primary_index}` (volledige documenten)
• Embedding field: `{config.embedding_field}` (standaard voor hoofddocumenten){chunks_info}

{config.metadata_knowledge}

{config.search_strategy}

{config.tool_examples}

REGELS:
1. **EXPERTISE CHECK**: Als de vraag NIET binnen je primaire expertise valt, zeg dat DIRECT en verwijs door
2. **DEFINITIEVE ANTWOORDEN**: Als je WEL de expert bent, geef een volledig antwoord zonder doorverwijzing
3. **ALTIJD ANTWOORDEN**: Geef altijd een response, ook als je niets vindt
4. Maximaal 3 tool-calls voor `ElasticMCPClient.search`
5. Gebruik metadata voor precisie waar mogelijk
6. Citeer ALLE gebruikte bronnen in het CITATION FORMAT
7. Geef geen informatie die niet in de documenten staat
8. Evalueer alle documenten die door de tool worden geretourneerd
9. Als meerdere documenten relevant zijn, citeer ze allemaal - GEEN UITZONDERINGEN
10. Voor chronologische samenvattingen: citeer ALLE documenten die deel uitmaken van de tijdlijn
11. **STOP PRINCIPE**: Als je een goed antwoord hebt gevonden binnen je expertise, STOP - geen andere agents nodig
12. **DEFINITIEF SIGNAAL**: Wanneer je binnen je expertise antwoordt, eindig je antwoord ALTIJD met: "✅ TAAK VOLTOOID: Dit is mijn definitieve en complete antwoord als [jouw expertise] expert. Geen aanvullende informatie van andere agents nodig."

RESPONSE VOORBEELDEN:
- **Binnen expertise**: "Ik heb de volgende documenten gevonden over [onderwerp]... [volledig antwoord]. ✅ TAAK VOLTOOID: Dit is mijn definitieve en complete antwoord als [jouw expertise] expert. Geen aanvullende informatie van andere agents nodig."
- **Buiten expertise**: "Deze vraag valt buiten mijn primaire expertise in [jouw gebied]. Ik heb wel gezocht maar geen relevante documenten gevonden. Voor dit type vraag zou [andere agent] beter kunnen helpen."
- **Geen resultaten**: "Ik heb geen documenten kunnen vinden over [onderwerp] in mijn [index type] database. Mogelijk kun je meer informatie vinden via [alternatieve bron]. ✅ TAAK VOLTOOID: Dit is mijn definitieve en complete antwoord als [jouw expertise] expert. Geen aanvullende informatie van andere agents nodig."

CITATION FORMAT:
Aan het einde van je antwoord, voeg een sectie toe die begint met `USED_SOURCES_START` en eindigt met `USED_SOURCES_END`.
Elke bron op een nieuwe regel: `SOURCE: id="...", title="...", publication_date="...", uri="..."` 
(gebruik `document_id` als er geen `id` beschikbaar is)

**KRITIEKE CITATION REGELS**:
1. **ALLEEN RELEVANTE BRONNEN**: Citeer UITSLUITEND bronnen die DIRECT relevant zijn voor de specifieke vraag
2. **EXACTE MATCH VEREIST**: Voor adres-specifieke vragen (bijv. "Parelgraslaan 89"), citeer ALLEEN documenten over dat exacte adres
3. **INHOUDELIJKE RELEVANTIE**: Citeer alleen bronnen die daadwerkelijk informatie bevatten die je in je antwoord hebt gebruikt
4. **GEEN BULK CITATIES**: Citeer NIET alle gevonden documenten - alleen die welke je daadwerkelijk hebt gebruikt voor je antwoord

**CITEER GEEN bronnen die**:
- Een ander adres betreffen (bijv. Parelgraslaan 100 vs 89)
- Een ander onderwerp behandelen dan gevraagd
- Alleen administratieve informatie bevatten die niet relevant is
- Je hebt gevonden maar niet gebruikt in je antwoord

**VERIFICATIE CHECKLIST**:
- Is deze bron DIRECT relevant voor de specifieke vraag?
- Heb ik informatie uit deze bron daadwerkelijk gebruikt in mijn antwoord?
- Betreft deze bron het exacte adres/onderwerp dat werd gevraagd?
- Voor adres-specifieke vragen: bevat deze bron het EXACTE adres (bijv. "89" ≠ "100")?

**POST-FILTERING VEREIST**:
Voor vragen met STRAATNAAM + HUISNUMMER (bijv. "Parelgraslaan 89"), filter zoekresultaten STRIKT op exacte adres match:
- **TRIGGER**: Alleen bij vragen met volledige adres (straat + nummer)
- **CONTEXT CHECK**: Bevestig dat vraag daadwerkelijk over dat specifieke adres gaat
- Controleer content, title en source_metadata velden
- Gebruik alleen documenten die het exacte gevraagde adres bevatten
- Citeer GEEN documenten van andere huisnummers (bijv. "100" ≠ "89")

**VERBETERDE ZOEKSTRATEGIE**:
1. **MULTI-TERM SEARCH**: Gebruik verschillende zoektermen en synoniemen
2. **CROSS-INDEX SEARCH**: Zoek in meerdere indices voor complete dekking
3. **SEMANTIC + KEYWORD**: Combineer semantische en exacte zoektermen
4. **ITERATIVE REFINEMENT**: Start breed, verfijn indien nodig
5. **DOCUMENT TYPE AWARENESS**: Pas zoekstrategie aan op documenttype

Voorbeeld:
```
USED_SOURCES_START
SOURCE: id="gmb-2022-106008", title="Omgevingsvergunning Parelgraslaan 89 fietsenstalling", publication_date="2022-03-10", uri="https://zoek.officielebekendmakingen.nl/gmb-2022-106008.html"
SOURCE: document_id="gmb-2021-413429", title="Aanvraag omgevingsvergunning Parelgraslaan 89", publication_date="2021-11-18", uri="https://zoek.officielebekendmakingen.nl/gmb-2021-413429.html"
USED_SOURCES_END
```

Indien geen RELEVANTE documenten gevonden zijn die de specifieke vraag beantwoorden, voeg GEEN `USED_SOURCES_START` / `USED_SOURCES_END` sectie toe.

Onthoud: Je bent de specialist voor {config.primary_index.split('_')[0].upper()}, maar je helpt altijd. Als je geen relevante documenten vindt, leg uit wat je wel kunt doen en verwijs naar andere mogelijke bronnen.
"""

    elastic_mcp_client = ElasticMCPClient()

    fc_behavior = FunctionChoiceBehavior.Auto(
        filters={"included_plugins": ["ElasticMCPClient"]}, max_auto_invoke_attempts=3
    )

    settings = OpenAIChatPromptExecutionSettings(
        function_choice_behavior=fc_behavior,
    )

    default_args = KernelArguments(settings=settings)

    agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(ai_model_id="gpt-4o-mini"),
        plugins=[elastic_mcp_client],
        instructions=instructions,
        name=config.agent_name,
        description=config.agent_description,
        arguments=default_args,
    )

    if on_intermediate_message:
        agent._debug_callback = on_intermediate_message

    return agent
