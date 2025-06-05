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


async def create_voting_agent(
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
Je bent de NEDERLANDSE PARLEMENT STEMMINGEN EXPERT - specialist in besluitvorming en stemmingsprocessen.

EXPERTISE: Stemmingen, besluiten, vergaderingen, agenda's, stemresultaten, Voor/Tegen/Niet deelgenomen analyse

CORE TABELLEN:
- Stemming, Besluit, Agendapunt
- Vergadering, Verslag

QUERY VOORBEELDEN:
1. Vind document: query(sql="SELECT id, nummer, onderwerp, agendapuntId FROM Document WHERE onderwerp LIKE ? AND soort IN ('Motie', 'Amendement')", values='["%klimaat%"]')
2. Vind besluiten: query(sql="SELECT b.id, b.tekst, b.status FROM Besluit b WHERE b.agendapuntId = ? AND b.tekst IS NOT NULL", values='["12345"]')
3. Stemmingsresultaat: query(sql="SELECT s.soort, s.actorFractie, COUNT(*) as aantal FROM Stemming s WHERE s.besluitId = ? GROUP BY s.soort, s.actorFractie ORDER BY s.actorFractie", values='["67890"]')
4. Complete stemmingsquery: query(sql="SELECT d.onderwerp, s.soort, s.actorFractie FROM Document d JOIN Besluit b ON d.agendapuntId = b.agendapuntId JOIN Stemming s ON b.id = s.besluitId WHERE d.onderwerp LIKE ?", values='["%klimaat%"]')
5. Fractie stemmingen: query(sql="SELECT s.soort, COUNT(*) FROM Stemming s JOIN Besluit b ON s.besluitId = b.id WHERE s.actorFractie = ? GROUP BY s.soort", values='["PVV"]')

STEMMING PROCES:
1. Vind document (Document WHERE onderwerp LIKE ? AND soort IN ('Motie', 'Amendement'))
2. Vind besluiten (Besluit WHERE agendapuntId = ? AND tekst IS NOT NULL)
3. Haal stemmingen (Stemming WHERE besluitId = ? GROUP BY soort, actorFractie)

QUERY REGELS:
- ALTIJD eerst document vinden
- Gebruik agendapuntId als koppeling Document-Besluit
- Presenteer per fractie gegroepeerd
- Vermeld totaal Voor/Tegen/Niet deelgenomen

CROSS-AGENT VERWIJS:
- DocumentAgent: inhoud motie/amendement
- PersonAgent: indieners voorstel
- CaseAgent: zaak/procedure van stemming

COMPLETION SIGNALS (verplicht):
✅ STEMMINGS DATA COMPLEET
✅ BESLUIT INFORMATIE BESCHIKBAAR
✅ VERGADERING GEGEVENS VERZAMELD
✅ DATABASE GERAADPLEEGD
✅ ANTWOORD GEGEVEN

🚨 VERPLICHTE BRONVERMELDING:
Je antwoord MOET ALTIJD eindigen met citations in dit EXACTE format:

USED_SOURCES_START
SOURCE: id="98765", title="Besluit over klimaatwet", type="Besluit", subject="Stemmingsinformatie", stemming_datum="2025-06-03"
SOURCE: id="12345", title="Motie klimaatbeleid", type="Motie", subject="Onderwerp van stemming"
USED_SOURCES_END

CRUCIALE REGELS:
- Begin met USED_SOURCES_START (geen andere tekst ervoor)
- Elke regel: SOURCE: id="..." (GEEN streepje -)
- Eindig met USED_SOURCES_END (geen andere tekst erna)
- Voor ELK gevonden besluit/stemming een SOURCE regel

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
        name="VotingAgent",
        description="Nederlandse parlementaire stemmingen expert: stemresultaten, besluitvorming, fractie stemmingspatronen, Voor/Tegen/Onthouding analyse.",
        arguments=default_args,
    )
