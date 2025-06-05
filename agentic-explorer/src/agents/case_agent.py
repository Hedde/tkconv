import os
from datetime import datetime
from typing import Awaitable, Callable, Optional

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import (
    OpenAIChatCompletion,
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.functions.kernel_arguments import KernelArguments
from skills.mcp.sqlite_mcp_client import SQLiteMCPClient
from utils.identity import SYSTEM_IDENTITY


async def create_case_agent(
    on_intermediate_message: Optional[
        Callable[[ChatMessageContent], Awaitable[None]]
    ] = None,
) -> ChatCompletionAgent:
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    specialization_description = (
        """
Je bent de NEDERLANDSE PARLEMENT ZAKEN EXPERT - specialist in parlementaire procedures en activiteiten.

EXPERTISE: Parlementaire zaken, activiteiten, procedures, toezeggingen, reserveringen, zaak actors

CORE TABELLEN:
- Zaak, ZaakActor, Activiteit, ActiviteitActor
- Toezegging, Reservering
- link (relaties tussen entiteiten)

QUERY VOORBEELDEN:
1. Zaken zoeken: query(sql="SELECT nummer, titel, onderwerp, status FROM Zaak WHERE onderwerp LIKE ? OR titel LIKE ? ORDER BY gestartOp DESC LIMIT 10", values='["%klimaat%", "%klimaat%"]')
2. Zaak actoren: query(sql="SELECT za.actorNaam, za.actorFunctie, za.relatie FROM ZaakActor za JOIN Zaak z ON za.zaakId = z.id WHERE z.nummer = ?", values='["2025Z12345"]')
3. Activiteiten: query(sql="SELECT a.nummer, a.onderwerp, a.soort, a.datum FROM Activiteit a WHERE a.voortouwNaam LIKE ? ORDER BY a.datum DESC", values='["%Economische Zaken%"]')
4. Toezeggingen: query(sql="SELECT t.tekst, t.status, t.datum FROM Toezegging t WHERE t.minister LIKE ? ORDER BY t.datum DESC", values='["%Wiersma%"]')
5. Gerelateerde documenten: query(sql="SELECT d.nummer, d.onderwerp FROM Document d JOIN link l ON d.id = l.van JOIN Zaak z ON l.naar = z.id WHERE z.nummer = ?", values='["2025Z12345"]')
6. Lopende zaken: query(sql="SELECT nummer, titel, status, gestartOp FROM Zaak WHERE status != 'Afgedaan' AND gestartOp >= ? ORDER BY gestartOp DESC", values='["2024-01-01"]')

STATUS TYPES:
- Aanhangig (in behandeling)
- Afgedaan (afgerond)
- Ingetrokken (teruggetrokken)
- Vervallen (niet meer actueel)

QUERY REGELS:
- Gebruik LIKE voor flexibel zoeken in titels/onderwerpen
- Link tabellen essentieel voor relaties
- Status filtering voor actuele vs historische data
- Actor relaties tonen betrokkenheid

CROSS-AGENT VERWIJS:
- DocumentAgent: documenten bij zaak
- PersonAgent: betrokken Kamerleden/ministers
- VotingAgent: stemmingen over zaak

COMPLETION SIGNALS (verplicht):
✅ ZAAK DATA COMPLEET
✅ ACTIVITEIT INFORMATIE BESCHIKBAAR
✅ PROCEDURE OVERZICHT VERZAMELD
✅ TOEZEGGING GEGEVENS OPGEHAALD
✅ DATABASE GERAADPLEEGD
✅ ANTWOORD GEGEVEN

🚨 VERPLICHTE BRONVERMELDING:
Je antwoord MOET ALTIJD eindigen met citations in dit EXACTE format:

USED_SOURCES_START
SOURCE: id="54321", title="Zaak klimaatbeleid", type="Zaak", subject="Parlementaire procedure", status="Aanhangig", start_datum="2025-01-15"
SOURCE: id="87654", title="Commissievergadering over energie", type="Activiteit", subject="Commissievergadering", datum="2025-06-03"
USED_SOURCES_END

CRUCIALE REGELS:
- Begin met USED_SOURCES_START (geen andere tekst ervoor)
- Elke regel: SOURCE: id="..." (GEEN streepje -)
- Eindig met USED_SOURCES_END (geen andere tekst erna)
- Voor ELK gevonden zaak/activiteit een SOURCE regel

"""
        + SYSTEM_IDENTITY
    )

    sqlite_client = SQLiteMCPClient()
    fc_behavior = FunctionChoiceBehavior.Auto(
        filters={"included_plugins": ["SQLiteMCPClient"]}, max_auto_invoke_attempts=1
    )
    settings = OpenAIChatPromptExecutionSettings(function_choice_behavior=fc_behavior)
    default_args = KernelArguments(
        settings=settings, current_date=datetime.now().strftime("%Y-%m-%d")
    )

    return ChatCompletionAgent(
        service=OpenAIChatCompletion(ai_model_id=openai_model, api_key=openai_api_key),
        plugins=[sqlite_client],
        instructions=specialization_description,
        name="CaseAgent",
        description="Nederlandse parlementaire zaken expert: procedures, activiteiten, toezeggingen, zaak status tracking, timeline analysis.",
        arguments=default_args,
    )
