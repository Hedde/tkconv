"""
Shared templates and patterns to reduce duplication across domain agents.
This module provides standardized templates that can be customized per agent.
"""

from typing import Dict, List


def get_metadata_knowledge_template(
    agent_domain: str, specific_metadata: Dict[str, List[str]] = None
) -> str:
    """
    Generate standardized metadata knowledge section with domain-specific customizations.

    Args:
        agent_domain: The domain of the agent (e.g., "BELASTINGEN", "EVENEMENTEN")
        specific_metadata: Domain-specific metadata fields to add
    """

    base_template = """
METADATA KENNIS CROSS-INDEX:

**CVDR METADATA:**
- `regeling_type`: verordening, beleidsregel
- `onderwerp`: {cvdr_onderwerpen}
- `inwerkingtreding_datum`: geldigheid regeling
- `artikelen`: specifieke artikelnummers

**WEB METADATA:**
- `page_type`: {web_page_types}
- `breadcrumb`: navigatiepad
- `last_modified`: actualiteit informatie
- `tags`: {web_tags}

**OEP METADATA:**
- `Type vergunning`: {oep_vergunning_types}
- `Bekendmakingtype`: {oep_bekendmaking_types}
- `Gebiedsmarkering (Adres)`: specifieke locaties
- `Beleidsonderwerp`: {oep_beleidsonderwerpen}
"""

    # Default metadata per domain
    domain_metadata = {
        "BELASTINGEN": {
            "cvdr_onderwerpen": "belasting, heffing, leges, OZB, riool, afval",
            "web_page_types": "procedure, formulier, informatie, contact",
            "web_tags": "belasting, OZB, riool, afval, bezwaar, betaling",
            "oep_vergunning_types": "beschikking, waardering",
            "oep_bekendmaking_types": "besluit, beschikking",
            "oep_beleidsonderwerpen": "belasting, WOZ, heffingen",
        },
        "EVENEMENTEN": {
            "cvdr_onderwerpen": "evenementen, APV, leges",
            "web_page_types": "procedure, informatie, nieuws",
            "web_tags": "evenementen, subsidie, wijkfeest",
            "oep_vergunning_types": "evenementvergunning, APV-vergunning",
            "oep_bekendmaking_types": "besluit, aanvraag",
            "oep_beleidsonderwerpen": "evenementen, openbare orde",
        },
        "VERGUNNINGEN": {
            "cvdr_onderwerpen": "bouw, omgeving, welstand, monumenten, leges",
            "web_page_types": "procedure, formulier, informatie",
            "web_tags": "vergunning, bouw, omgeving, welstand",
            "oep_vergunning_types": "omgevingsvergunning, bouwvergunning, sloopvergunning",
            "oep_bekendmaking_types": "besluit, aanvraag, verleend",
            "oep_beleidsonderwerpen": "bouwen, milieu, monumenten",
        },
        "IDENTITEIT": {
            "cvdr_onderwerpen": "leges, tarieven, procedures",
            "web_page_types": "procedure, formulier, informatie",
            "web_tags": "paspoort, identiteitskaart, rijbewijs, uittreksel",
            "oep_vergunning_types": "verklaring, uittreksel",
            "oep_bekendmaking_types": "besluit, verklaring",
            "oep_beleidsonderwerpen": "identiteit, documenten, burgerlijke stand",
        },
        "ZORG": {
            "cvdr_onderwerpen": "WMO, bijstand, participatie, jeugdhulp",
            "web_page_types": "procedure, informatie, formulier",
            "web_tags": "WMO, zorg, ondersteuning, bijstand",
            "oep_vergunning_types": "WMO-beschikking, bijstandsbesluit",
            "oep_bekendmaking_types": "besluit, toewijzing, afwijzing",
            "oep_beleidsonderwerpen": "WMO, participatie, jeugd, zorg",
        },
        "VERKEER": {
            "cvdr_onderwerpen": "verkeer, parkeren, APV, leges",
            "web_page_types": "procedure, informatie, formulier",
            "web_tags": "parkeren, verkeer, vergunning, mobiliteit",
            "oep_vergunning_types": "parkeervergunning, ontheffing verkeer",
            "oep_bekendmaking_types": "besluit, vergunning, verkeersbesluit",
            "oep_beleidsonderwerpen": "verkeer, parkeren, mobiliteit",
        },
        "WONEN": {
            "cvdr_onderwerpen": "huisvesting, woonruimteverdeling, woningbouw",
            "web_page_types": "procedure, formulier, informatie, dienst",
            "web_tags": "verhuizen, BRP, woningzoekenden, sociale huur",
            "oep_vergunning_types": "beschikking, toewijzing",
            "oep_bekendmaking_types": "besluit, bekendmaking",
            "oep_beleidsonderwerpen": "huisvesting, woningbouw, woonruimteverdeling",
        },
        "ONDERNEMER": {
            "cvdr_onderwerpen": "horeca, bedrijven, markt, APV, reclame",
            "web_page_types": "procedure, formulier, informatie, advies",
            "web_tags": "ondernemen, horeca, markt, bedrijf, vergunning",
            "oep_vergunning_types": "horecavergunning, exploitatievergunning, standplaatsvergunning",
            "oep_bekendmaking_types": "besluit, vergunning",
            "oep_beleidsonderwerpen": "horeca, bedrijven, markt, ondernemen",
        },
        "MILIEU": {
            "cvdr_onderwerpen": "afval, milieu, duurzaamheid, handhaving",
            "web_page_types": "informatie, procedure, schema, tips",
            "web_tags": "afval, milieu, duurzaamheid, inzameling, subsidie",
            "oep_vergunning_types": "milieuvergunning, afvalbesluit",
            "oep_bekendmaking_types": "besluit, vergunning, project",
            "oep_beleidsonderwerpen": "milieu, afval, duurzaamheid, circulaire economie",
        },
        "ALGEMEEN": {
            "cvdr_onderwerpen": "organisatie, contact, algemeen",
            "web_page_types": "informatie, nieuws, contact, dienst",
            "web_tags": "contact, openingstijden, nieuws, gemeente",
            "oep_vergunning_types": "besluit, bekendmaking, beleid",
            "oep_bekendmaking_types": "raadsbesluit, beleidsstuk",
            "oep_beleidsonderwerpen": "algemeen bestuur, organisatie, beleid",
        },
    }

    # Get domain-specific metadata or use defaults
    metadata = domain_metadata.get(agent_domain.upper(), domain_metadata["ALGEMEEN"])

    # Override with specific metadata if provided
    if specific_metadata:
        metadata.update(specific_metadata)

    return base_template.format(**metadata)


def get_search_strategy_template(
    agent_domain: str, primary_index: str, search_patterns: Dict[str, str] = None
) -> str:
    """
    Generate standardized search strategy with domain-specific patterns.

    Args:
        agent_domain: The domain of the agent
        primary_index: Primary index to start with (CVDR, WEB, OEP, ROO)
        search_patterns: Domain-specific search patterns per index
    """

    base_template = """
CROSS-INDEX ZOEKPLAN {domain_title}:

🎯 **BREED-NAAR-SMAL STRATEGIE** (ALTIJD TOEPASSEN):
1️⃣ **BREED ZOEKEN**: Start ALTIJD zonder specifieke persoon/locatie/situatie
2️⃣ **EVALUEREN**: Controleer of gevonden documenten de specifieke situatie dekken  
3️⃣ **AANVULLEN**: Voeg specifiekere zoekopdracht toe indien nodig

🔍 **DRIE-FASE ZOEKSTRATEGIE**:
**FASE 1 - {primary_index} ({primary_description})**: {primary_purpose}
**FASE 2 - {secondary_index} ({secondary_description})**: {secondary_purpose}
**FASE 3 - {tertiary_index} ({tertiary_description})**: {tertiary_purpose}

📋 **ZOEKPATRONEN PER INDEX**:
- **CVDR**: "{cvdr_pattern}"
- **Web**: "{web_pattern}"
- **OEP**: "{oep_pattern}" (alleen bij specifieke vragen)

⚡ **PERFORMANCE REGELS**:
- Maximaal 3 tool calls totaal
- Start met {primary_index} voor {primary_focus}
- Ga naar {secondary_index} voor {secondary_focus}
- Gebruik {tertiary_index} alleen voor {tertiary_focus}
- Combineer informatie uit alle relevante bronnen
"""

    # Index descriptions
    index_info = {
        "CVDR": ("Regelgeving", "verordeningen en beleid"),
        "WEB": ("Procedures", "praktische informatie en formulieren"),
        "OEP": ("Besluiten", "specifieke vergunningen en besluiten"),
        "ROO": ("Organisatie", "contactgegevens en organisatiestructuur"),
    }

    # Default search patterns per domain
    default_patterns = {
        "BELASTINGEN": {
            "cvdr_pattern": "OZB rioolheffing afvalstoffenheffing leges belasting tarief",
            "web_pattern": "bezwaar belasting betaling regeling kwijtschelding formulier",
            "oep_pattern": "WOZ waardering belasting beschikking [adres]",
        },
        "EVENEMENTEN": {
            "cvdr_pattern": "toetsingskader evenementen APV artikel 2:24 leges",
            "web_pattern": "evenement organiseren subsidie wijkfeest procedure geluidsnormen",
            "oep_pattern": "evenementvergunning [locatie] toestemming besluit",
        },
        "VERGUNNINGEN": {
            "cvdr_pattern": "bouwverordening omgevingsvergunning welstand leges",
            "web_pattern": "vergunning aanvragen procedure formulier omgevingsloket",
            "oep_pattern": "omgevingsvergunning verleend besluit [type/locatie]",
        },
        # Add more domains as needed
    }

    # Determine index order based on primary
    if primary_index == "CVDR":
        secondary_index, tertiary_index = "WEB", "OEP"
        primary_focus = "regelgeving en tarieven"
        secondary_focus = "procedures en praktische info"
        tertiary_focus = "specifieke besluiten/vergunningen"
    elif primary_index == "WEB":
        secondary_index, tertiary_index = "CVDR", "OEP"
        primary_focus = "procedures en praktische informatie"
        secondary_focus = "regelgeving en voorschriften"
        tertiary_focus = "specifieke besluiten/vergunningen"
    elif primary_index == "ROO":
        secondary_index, tertiary_index = "WEB", "OEP"
        primary_focus = "organisatie en contactgegevens"
        secondary_focus = "algemene informatie"
        tertiary_focus = "algemene besluiten"
    else:  # OEP
        secondary_index, tertiary_index = "CVDR", "WEB"
        primary_focus = "specifieke besluiten"
        secondary_focus = "regelgeving"
        tertiary_focus = "procedures"

    # Get patterns
    patterns = search_patterns or default_patterns.get(
        agent_domain.upper(),
        {
            "cvdr_pattern": f"{agent_domain.lower()} regelgeving verordening",
            "web_pattern": f"{agent_domain.lower()} procedure aanvragen informatie",
            "oep_pattern": f"{agent_domain.lower()} besluit vergunning [specifiek]",
        },
    )

    return base_template.format(
        domain_title=agent_domain.upper(),
        primary_index=primary_index,
        primary_description=index_info[primary_index][0],
        primary_purpose=index_info[primary_index][1],
        secondary_index=secondary_index,
        secondary_description=index_info[secondary_index][0],
        secondary_purpose=index_info[secondary_index][1],
        tertiary_index=tertiary_index,
        tertiary_description=index_info[tertiary_index][0],
        tertiary_purpose=index_info[tertiary_index][1],
        primary_focus=primary_focus,
        secondary_focus=secondary_focus,
        tertiary_focus=tertiary_focus,
        **patterns,
    )


def get_tool_examples_header() -> str:
    """Get standardized tool examples header."""
    return """
CROSS-INDEX TOOL CALL VOORBEELDEN:

🌟 **UNIVERSEEL BREED-NAAR-SMAL PRINCIPE**:
Voor ALLE {domain}-specifieke vragen, gebruik ALTIJD deze aanpak:

**STAP 1 - BREED ZOEKEN** (zonder specifieke persoon/locatie/situatie):
Zoek eerst naar het ONDERWERP/PROCEDURE zonder beperkende termen
**STAP 2 - EVALUEREN & AANVULLEN**: 
Controleer of gevonden informatie de specifieke situatie dekt
"""


def get_performance_footer() -> str:
    """Get standardized performance footer."""
    return """
**MAXIMAAL 3 TOOL CALLS** voor optimale performance!

🎯 **CROSS-INDEX COMBINATIE STRATEGIE**:
1. **Start met {primary_index}** voor {primary_purpose}
2. **Ga naar {secondary_index}** voor {secondary_purpose}
3. **Gebruik {tertiary_index}** alleen voor {tertiary_purpose}
4. **Combineer informatie** uit alle relevante bronnen in één compleet antwoord
"""


def get_standard_json_template(
    index_name: str, query: str, fields_config: Dict = None
) -> str:
    """
    Generate standardized Elasticsearch query JSON template.

    Args:
        index_name: The index to search
        query: The search query
        fields_config: Custom field configuration
    """

    default_config = {
        "title_boost": 3,
        "content_boost": 2,
        "minimum_should_match": "50%",
        "size": 5,
    }

    if fields_config:
        default_config.update(fields_config)

    return f"""```json
{{
  "tool_name": "ElasticMCPClient-search",
  "arguments": {{
    "index": "{index_name}_INDEX",
    "query": "{query}",
    "request_id": "req_123",
    "embedding_field": "embedding_summary",
    "query_body": {{
      "query": {{
        "bool": {{
          "should": [
            {{
              "multi_match": {{
                "query": "[main query terms]",
                "fields": [
                  "title^{default_config['title_boost']}",
                  "content^{default_config['content_boost']}"
                ]
              }}
            }},
            {{
              "multi_match": {{
                "query": "[secondary terms]",
                "fields": [
                  "content^{default_config['content_boost']}"
                ]
              }}
            }},
            {{
              "match": {{
                "content": "[term1]"
              }}
            }},
            {{
              "match": {{
                "content": "[term2]"
              }}
            }},
            {{
              "match": {{
                "content": "[term3]"
              }}
            }}
          ],
          "minimum_should_match": "{default_config['minimum_should_match']}"
        }}
      }},
      "size": {default_config['size']}
    }}
  }}
}}
```"""


def get_definitive_answer_principle(agent_expertise: str) -> str:
    """Get standardized definitive answer principle."""
    return f"""
🎯 DEFINITIEF ANTWOORD PRINCIPE:
Wanneer ik een antwoord geef binnen mijn expertise ({agent_expertise}), is dit DEFINITIEF en COMPLEET. Er is GEEN behoefte aan aanvullende input van andere agents.
"""


def get_cross_index_strategy_description(
    primary_index: str, secondary_index: str, tertiary_index: str
) -> str:
    """Get standardized cross-index strategy description."""

    index_descriptions = {
        "CVDR": "Regelgeving en verordeningen",
        "WEB": "Procedures en praktische informatie",
        "OEP": "Specifieke besluiten en vergunningen",
        "ROO": "Organisatie en contactgegevens",
    }

    return f"""
🔍 CROSS-INDEX ZOEKSTRATEGIE:
Ik gebruik een gestructureerde aanpak om alle relevante informatie te verzamelen:
1. **{primary_index}**: {index_descriptions[primary_index]}
2. **{secondary_index}**: {index_descriptions[secondary_index]}
3. **{tertiary_index}**: {index_descriptions[tertiary_index]}

Maximaal 3 tool calls voor optimale performance en volledigheid.
"""


def create_agent_configuration_dry(
    agent_name: str,
    agent_domain: str,
    primary_index: str,
    expertise_areas: List[str],
    typical_questions: List[str],
    cross_references_exclude: str,
    specific_metadata: Dict[str, str] = None,
    search_patterns: Dict[str, str] = None,
) -> Dict[str, str]:
    """
    Create a complete agent configuration using DRY templates.

    Args:
        agent_name: Name of the agent (e.g., "BelastingEnHeffingenAgent")
        agent_domain: Domain of the agent (e.g., "BELASTINGEN")
        primary_index: Primary index to start with
        expertise_areas: List of expertise areas
        typical_questions: List of typical questions
        cross_references_exclude: Agent name to exclude from cross-references
        specific_metadata: Domain-specific metadata overrides
        search_patterns: Domain-specific search patterns

    Returns:
        Dictionary with all agent configuration strings
    """

    from .agent_references import get_agent_cross_references

    # Generate expertise section
    expertise_section = "\n".join([f"- **{area}**" for area in expertise_areas])

    # Generate typical questions section
    questions_section = "\n".join([f'- "{q}"' for q in typical_questions])

    # Build specialization description
    specialization_description = f"""
Je bent de DEFINITIEVE EXPERT voor {agent_domain.lower()} in Gemeente Rijswijk.

🎯 EXCLUSIEVE EXPERTISE (GEEN ANDERE AGENT NODIG):
{expertise_section}

CROSS-INDEX EXPERTISE:
- **CVDR**: [Domain-specific CVDR description]
- **Web**: [Domain-specific Web description]  
- **OEP**: [Domain-specific OEP description]

TYPISCHE VRAGEN DIE IK BEANTWOORD:
{questions_section}

{get_agent_cross_references(cross_references_exclude)}

{get_definitive_answer_principle(agent_domain.lower())}

{get_cross_index_strategy_description(primary_index, "WEB" if primary_index != "WEB" else "CVDR", "OEP")}
"""

    return {
        "specialization_description": specialization_description,
        "metadata_knowledge": get_metadata_knowledge_template(
            agent_domain, specific_metadata
        ),
        "search_strategy": get_search_strategy_template(
            agent_domain, primary_index, search_patterns
        ),
        "tool_examples_header": get_tool_examples_header().format(
            domain=agent_domain.lower()
        ),
        "performance_footer": get_performance_footer(),
    }
