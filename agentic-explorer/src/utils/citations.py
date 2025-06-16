"""
Citation utility for all parliamentary agents.

Provides standardized citation formatting with agent-specific metadata extensions.
"""

from typing import Dict, List, Optional, Union


class CitationBuilder:
    """Builds standardized citations for parliamentary agents."""

    def __init__(self):
        self.sources: List[Dict[str, str]] = []

    def add_source(
        self,
        id: str,
        title: str,
        type: str,
        subject: str,
        **kwargs: Union[str, int, None],
    ) -> "CitationBuilder":
        """
        Add a source with common fields and agent-specific metadata.

        Common fields:
        - id: Unique identifier
        - title: Display title
        - type: Source type (Document, Agendapunt, Persoon, etc.)
        - subject: Brief description

        Agent-specific kwargs (examples):
        - publication_date: For documents
        - document_nummer: For documents
        - official_url: For documents
        - fractie: For voting sources
        - stem_type: For voting sources
        - aantal_stemmingen: For voting sources
        - status: For case sources
        - start_datum/datum: For case/activity sources
        - uri: For web sources
        """
        source = {
            "id": str(id),
            "title": title,
            "type": type,
            "subject": subject,
        }

        # Add agent-specific metadata
        for key, value in kwargs.items():
            if value is not None and value != "":
                source[key] = str(value)

        self.sources.append(source)
        return self

    def build(self) -> str:
        """Build the complete citation block."""
        if not self.sources:
            return ""

        lines = ["USED_SOURCES_START"]
        for source in self.sources:
            # Build source line with all attributes
            attrs = []
            for key, value in source.items():
                attrs.append(f'{key}="{value}"')
            lines.append(f"SOURCE: {', '.join(attrs)}")
        lines.append("USED_SOURCES_END")

        return "\n".join(lines)

    @classmethod
    def for_documents(cls, documents: List[Dict]) -> str:
        """Helper for DocumentAgent citations."""
        builder = cls()
        for doc in documents:
            builder.add_source(
                id=doc.get("id", doc.get("nummer", "")),
                title=doc.get("onderwerp", "Document"),
                type=doc.get("soort", "Document"),
                subject=doc.get("onderwerp", "Parliamentary document"),
                publication_date=doc.get("datum", ""),
                document_nummer=doc.get("nummer", ""),
                official_url=doc.get("official_url", ""),
            )
        return builder.build()

    @classmethod
    def for_voting(cls, voting_data: List[Dict]) -> str:
        """Helper for VotingAgent citations."""
        builder = cls()
        for vote in voting_data:
            builder.add_source(
                id=f"stemming-{vote.get('id', '')}",
                title=vote.get("onderwerp", "Stemming"),
                type="Stemming",
                subject="Fractie stemming",
                fractie=vote.get("actorFractie", ""),
                stem_type=vote.get("soort", ""),
                aantal_stemmingen=vote.get("aantal", ""),
            )
        return builder.build()

    @classmethod
    def for_persons(cls, persons: List[Dict]) -> str:
        """Helper for PersonAgent citations."""
        builder = cls()
        for person in persons:
            builder.add_source(
                id=person.get("id", ""),
                title=f"{person.get('roepnaam', '')} {person.get('achternaam', '')}".strip(),
                type="Persoon",
                subject="Kamerlid informatie",
            )
        return builder.build()

    @classmethod
    def for_cases(cls, cases: List[Dict]) -> str:
        """Helper for CaseAgent citations."""
        builder = cls()
        for case in cases:
            builder.add_source(
                id=case.get("id", case.get("nummer", "")),
                title=case.get("titel", case.get("onderwerp", "Zaak")),
                type="Zaak",
                subject="Parlementaire procedure",
                status=case.get("status", ""),
                start_datum=case.get("gestartOp", case.get("datum", "")),
            )
        return builder.build()


# Common citation instructions for all agents
CITATION_INSTRUCTIONS = """
🚨 VERPLICHTE BRONVERMELDING - ALTIJD VERPLICHT:

**REGEL 1: ALTIJD CITATIONS TOEVOEGEN**
Voeg AAN HET EINDE van ELKE response ALTIJD deze bronnenblok toe:

USED_SOURCES_START
SOURCE: id="example-id", title="Example Title", type="SourceType", subject="Description"
USED_SOURCES_END

**REGEL 2: GEEN UITZONDERINGEN**
⚠️ VERPLICHT: Elke database query result MOET als SOURCE worden vermeld!
⚠️ VERPLICHT: Ook bij "geen resultaten" of "data niet beschikbaar" moet je uitleggen WELKE queries je hebt uitgevoerd!
⚠️ VERPLICHT: Zelfs bij eenvoudige vragen moet je bronnen vermelden!

**REGEL 3: ENFORCEMENT**
- Je response is NIET compleet zonder citations
- COMPLETION_SIGNALS zijn pas geldig MET citations
- Geen citations = incomplete response = FOUT

**REGEL 4: MINIMAL CITATIONS**
Als je GEEN data vindt:
USED_SOURCES_START
SOURCE: id="database-query", title="Database search performed", type="Query", subject="No results found for [onderwerp]", query_executed="SELECT ... FROM ..."
USED_SOURCES_END

**REGEL 5: MULTIPLE QUERIES**
Elke uitgevoerde query moet als aparte SOURCE:
USED_SOURCES_START
SOURCE: id="query-1", title="Zaak search", type="Query", subject="Search for jeugdzorg cases", results_found="3"
SOURCE: id="query-2", title="Activiteit search", type="Query", subject="Search for recent activities", results_found="1"
USED_SOURCES_END

Gebruik de CitationBuilder utility in je code voor consistente formatting.
"""
