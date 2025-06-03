"""
Shared agent cross-references to reduce duplication across domain agents.
This module provides standardized referral text that can be used by all agents.
"""


def get_agent_cross_references(current_agent_name: str) -> str:
    """
    Get standardized cross-references for other domain agents.

    Args:
        current_agent_name: Name of the current agent to exclude from references

    Returns:
        Formatted string with cross-references to other relevant agents
    """

    all_agents = {
        "EvenementenAgent": "**EVENEMENTEN** → EvenementenAgent heeft meer expertise",
        "VergunningenAgent": "**VERGUNNINGEN** → VergunningenAgent heeft meer expertise",
        "ZorgEnOndersteunungAgent": "**WMO EN ZORG** → ZorgEnOndersteunungAgent heeft meer expertise",
        "VerkeerEnParkeerAgent": "**VERKEER EN PARKEREN** → VerkeerEnParkeerAgent heeft meer expertise",
        "IdentiteitEnDocumentenAgent": "**IDENTITEIT EN DOCUMENTEN** → IdentiteitEnDocumentenAgent heeft meer expertise",
        "BelastingEnHeffingenAgent": "**BELASTINGEN EN HEFFINGEN** → BelastingEnHeffingenAgent heeft meer expertise",
        "WonenEnVerhuizenAgent": "**WONEN EN VERHUIZEN** → WonenEnVerhuizenAgent heeft meer expertise",
        "OndernemerAgent": "**ONDERNEMEN EN BEDRIJVEN** → OndernemerAgent heeft meer expertise",
        "MilieuEnAfvalAgent": "**MILIEU EN AFVAL** → MilieuEnAfvalAgent heeft meer expertise",
        "AlgemeneInformatieAgent": "**ALGEMENE INFORMATIE** → AlgemeneInformatieAgent heeft meer expertise",
    }

    # Remove current agent from references
    relevant_agents = {k: v for k, v in all_agents.items() if k != current_agent_name}

    # Format as bullet points
    references = "\n".join([f"- {ref}" for ref in relevant_agents.values()])

    return f"""🚫 NIET MIJN EXPERTISE (verwijs door):
{references}"""


def get_agent_description_suffix(agent_name: str) -> str:
    """
    Get a standardized description suffix that mentions other available agents.

    Args:
        agent_name: Name of the current agent

    Returns:
        Description text mentioning other domain agents
    """

    agent_descriptions = {
        "EvenementenAgent": "evenementen, feesten, wijkfeesten, vergunningen en subsidies",
        "VergunningenAgent": "alle vergunningen (bouw, omgeving, boom, sloop, monument, horeca)",
        "ZorgEnOndersteunungAgent": "WMO, zorg, ondersteuning, hulp bij huishouden, vervoer en woningaanpassingen",
        "VerkeerEnParkeerAgent": "verkeer, parkeren, MILIEUZONES (Haagweg), ontheffingen en gehandicaptenparkeren",
        "IdentiteitEnDocumentenAgent": "paspoorten, ID-kaarten, rijbewijzen, uittreksels, akten en verklaringen",
        "BelastingEnHeffingenAgent": "OZB, rioolheffing, afvalstoffenheffing, leges, bezwaar en betalingsregelingen",
        "WonenEnVerhuizenAgent": "verhuizen, inschrijving BRP, woningzoekenden, sociale huur en huisvesting",
        "OndernemerAgent": "ondernemen, bedrijven, horeca, marktplaatsen en bedrijfsvergunningen",
        "MilieuEnAfvalAgent": "afval, duurzaamheid, afvalinzameling en milieuvergunningen (NIET milieuzones - die vallen onder verkeer)",
        "AlgemeneInformatieAgent": "contact, openingstijden, algemene informatie en organisatie",
    }

    current_description = agent_descriptions.get(agent_name, "")
    other_agents = [
        f"{name.replace('Agent', '')} ({desc})"
        for name, desc in agent_descriptions.items()
        if name != agent_name
    ]

    return f"Gebruik mij voor alle vragen over {current_description}. Voor andere onderwerpen zijn er gespecialiseerde agents beschikbaar: {', '.join(other_agents[:3])} en meer."
