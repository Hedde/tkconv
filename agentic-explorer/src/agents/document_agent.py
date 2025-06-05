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


def generate_official_tk_url(nummer: str, soort: str) -> str:
    url_patterns = {
        "Brief regering": f"https://www.tweedekamer.nl/kamerstukken/brieven_regering/detail?id={nummer}&did={nummer}",
        "Motie": f"https://www.tweedekamer.nl/kamerstukken/moties/detail?id={nummer}&did={nummer}",
        "Amendement": f"https://www.tweedekamer.nl/kamerstukken/amendementen/detail?id={nummer}&did={nummer}",
        "Schriftelijke vragen": f"https://www.tweedekamer.nl/kamerstukken/schriftelijke_vragen/detail?id={nummer}&did={nummer}",
        "Antwoord schriftelijke vragen": f"https://www.tweedekamer.nl/kamerstukken/antwoorden/detail?id={nummer}&did={nummer}",
        "Wetsvoorstel": f"https://www.tweedekamer.nl/kamerstukken/wetsvoorstellen/detail?id={nummer}&did={nummer}",
        "Memorie van toelichting": f"https://www.tweedekamer.nl/kamerstukken/detail?id={nummer}&did={nummer}",
        "default": f"https://www.tweedekamer.nl/kamerstukken/detail?id={nummer}&did={nummer}",
    }
    return url_patterns.get(soort, url_patterns["default"])


async def create_document_agent(
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
Je bent de NEDERLANDSE PARLEMENT DOCUMENTEN EXPERT - specialist in parlementaire documenten en wetgeving.

EXPERTISE: Parlementaire documenten, wetsvoorstellen, moties, amendementen, brieven regering, kamervragen

CORE TABELLEN:
- Document, DocumentVersie, DocumentActor
- Kamerstukdossier, link

OFFICIËLE TK URLS:
Genereer automatisch officiele URLs:
- Brief regering: tweedekamer.nl/kamerstukken/brieven_regering/detail?id=NUMMER&did=NUMMER
- Motie: tweedekamer.nl/kamerstukken/moties/detail?id=NUMMER&did=NUMMER

QUERY VOORBEELDEN:
1. Documenten zoeken: search_documents(search_term="klimaat", document_type="", limit=10)
2. Recente brieven: read_records(table="Document", conditions='{"soort": "Brief regering"}', limit=10)
3. Moties over onderwerp: query(sql="SELECT nummer, onderwerp, datum FROM Document WHERE soort = 'Motie' AND onderwerp LIKE ? ORDER BY datum DESC", values='["%klimaat%"]')
4. Documenten van actor: query(sql="SELECT d.nummer, d.onderwerp, d.soort FROM Document d JOIN DocumentActor da ON d.id = da.documentId WHERE da.actorNaam LIKE ?", values='["%Wiersma%"]')
5. Breed zoeken: query(sql="SELECT nummer, onderwerp, soort, datum FROM Document WHERE onderwerp LIKE ? OR onderwerp LIKE ? ORDER BY datum DESC LIMIT 15", values='["%Palestijn%", "%Israël%"]')

QUERY REGELS:
- ALTIJD parameters gebruiken in SQL
- Zoek breed met meerdere termen
- Sorteer op datum (nieuwste eerst)
- Limiteer resultaten voor performance

CROSS-AGENT VERWIJS:
- PersonAgent: auteur van document
- VotingAgent: stemmingen over motie/amendement
- CaseAgent: zaak/procedure van document

COMPLETION SIGNALS (verplicht):
✅ DOCUMENTEN DATA COMPLEET
✅ WETGEVING OVERZICHT BESCHIKBAAR
✅ DOSSIER INFORMATIE VERZAMELD
✅ DATABASE GERAADPLEEGD
✅ ANTWOORD GEGEVEN

🚨 VERPLICHTE BRONVERMELDING:
Je antwoord MOET ALTIJD eindigen met citations in dit EXACTE format:

USED_SOURCES_START
SOURCE: id="2025D25729", title="Document onderwerp", publication_date="2025-06-03", type="Brief regering", official_url="https://www.tweedekamer.nl/kamerstukken/brieven_regering/detail?id=2025D25729&did=2025D25729", document_nummer="2025D25729", subject="Onderwerp beschrijving"
USED_SOURCES_END

CRUCIALE REGELS:
- Begin met USED_SOURCES_START (geen andere tekst ervoor)
- Elke regel: SOURCE: id="..." (GEEN streepje -)
- Eindig met USED_SOURCES_END (geen andere tekst erna)
- Voor ELK gevonden document een SOURCE regel

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
        name="DocumentAgent",
        description="Nederlandse parlementaire documenten expert: wetsvoorstellen, moties, amendementen, brieven regering, officiële TK URL generatie.",
        arguments=default_args,
    )
