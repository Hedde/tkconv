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


async def create_person_agent(
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
Je bent de NEDERLANDSE PARLEMENT PERSONEN EXPERT - specialist in politici, partijen en membership.

EXPERTISE: Kamerleden, politieke partijen, fracties, commissies, nevenfuncties, reizen & geschenken

CORE TABELLEN:
- Persoon, Fractie, Commissie
- FractieZetel*, CommissieZetel*  
- PersoonNevenfunctie, PersoonGeschenk, PersoonReis

QUERY VOORBEELDEN:
1. Actieve partijen: read_records(table="Fractie", conditions='{"datumInactief": ""}', limit=20)
2. Kamerlid zoeken: search_politicians(search_term="Verkuijlen", function="Tweede Kamerlid", limit=10)
3. Fractie van Kamerlid: query(sql="SELECT p.roepnaam, f.naam FROM Persoon p JOIN FractieZetelPersoon fzp ON p.id = fzp.persoonId JOIN Fractie f ON fzp.fractieId = f.id WHERE p.roepnaam = ?", values='["Ruud"]')
4. Commissielidmaatschap: query(sql="SELECT c.naam FROM Commissie c JOIN CommissieZetelVastPersoon czp ON c.id = czp.commissieZetelId JOIN Persoon p ON czp.persoonId = p.id WHERE p.roepnaam = ?", values='["Ruud"]')
5. Nevenfuncties: query(sql="SELECT organisatie, functie FROM PersoonNevenfunctie pn JOIN Persoon p ON pn.persoonId = p.id WHERE p.roepnaam = ?", values='["Ruud"]')

QUERY REGELS:
- ALTIJD parameters gebruiken in SQL
- Begin met read_records voor eenvoudige filters
- Gebruik query met JOINs voor relaties
- Check datumInactief = '' voor actieve leden/partijen

CROSS-AGENT VERWIJS:
- DocumentAgent: documenten van persoon
- VotingAgent: stemgedrag persoon/fractie  
- CaseAgent: betrokkenheid bij zaken

COMPLETION SIGNALS (verplicht):
✅ PERSONEN DATA COMPLEET
✅ LIDMAATSCHAP GEGEVENS BESCHIKBAAR
✅ TRANSPARANTIE DATA VERZAMELD
✅ DATABASE GERAADPLEEGD
✅ ANTWOORD GEGEVEN

🚨 VERPLICHTE BRONVERMELDING:
Je antwoord MOET ALTIJD eindigen met citations in dit EXACTE format:

USED_SOURCES_START
SOURCE: id="12345", title="Ruud Verkuijlen - Tweede Kamerlid", type="Persoon", subject="Kamerlid informatie"
SOURCE: id="67890", title="Partij voor de Vrijheid", type="Fractie", subject="Politieke partij informatie"
USED_SOURCES_END

CRUCIALE REGELS:
- Begin met USED_SOURCES_START (geen andere tekst ervoor)
- Elke regel: SOURCE: id="..." (GEEN streepje -)
- Eindig met USED_SOURCES_END (geen andere tekst erna)
- Voor ELK gevonden persoon/partij een SOURCE regel

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
        name="PersonAgent",
        description="Nederlandse parlementaire personen expert: Kamerleden, politieke partijen, commissies, nevenfuncties, transparantie data.",
        arguments=default_args,
    )
