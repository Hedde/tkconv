"""Utility functions for committee mapping using AI skill."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template.prompt_template_config import PromptTemplateConfig

logger = logging.getLogger(__name__)

# Path to skill files
SKILL_PATH = Path(__file__).parent / "CommitteeMappingFunction"


async def determine_committee_for_topic(onderwerp: str) -> str:
    """
    Determine the most relevant Tweede Kamer committee for a parliamentary topic.

    Args:
        onderwerp: Parliamentary topic or agenda item

    Returns:
        Committee name for URL construction, fallback to 'commissievergaderingen'

    Example:
        >>> committee = await determine_committee_for_topic("Moties over veehouderij")
        >>> print(committee)  # "landbouw_natuur_en_voedselkwaliteit"
    """
    try:
        openai_model = os.getenv("OPENAI_MODEL")
        openai_api_key = os.getenv("OPENAI_API_KEY")

        if not openai_model or not openai_api_key:
            logger.warning("OpenAI credentials missing for committee mapping")
            return "commissievergaderingen"

        kernel = Kernel()
        kernel.add_service(
            OpenAIChatCompletion(ai_model_id=openai_model, api_key=openai_api_key)
        )

        # Load skill configuration
        prompt_file = SKILL_PATH / "skprompt.txt"
        config_file = SKILL_PATH / "config.json"

        if not prompt_file.exists() or not config_file.exists():
            logger.warning("CommitteeMapping skill files not found")
            return "commissievergaderingen"

        prompt_template = prompt_file.read_text(encoding="utf-8")
        config_data = json.loads(config_file.read_text(encoding="utf-8"))

        prompt_config = PromptTemplateConfig(
            template=prompt_template,
            name="CommitteeMappingFunction",
            description=config_data["description"],
            template_format="semantic-kernel",
            input_variables=[
                {
                    "name": "onderwerp",
                    "description": "Het parlementaire onderwerp of agendapunt",
                    "is_required": True,
                }
            ],
            execution_settings=config_data.get("execution_settings", {}),
        )

        committee_mapping_fn = kernel.add_function(
            plugin_name="committee_mapping_skill",
            function_name="CommitteeMappingFunction",
            prompt_template_config=prompt_config,
        )

        mapping_result = await kernel.invoke(
            committee_mapping_fn, KernelArguments(onderwerp=onderwerp)
        )

        if mapping_result and mapping_result.value:
            committee_name = str(mapping_result.value).strip()
            if committee_name:
                logger.info(f"Committee mapped: '{onderwerp}' → '{committee_name}'")
                return committee_name

        logger.warning(f"Committee mapping failed for: {onderwerp}")
        return "commissievergaderingen"

    except Exception as e:
        logger.error(f"Error mapping committee for '{onderwerp}': {e}", exc_info=True)
        return "commissievergaderingen"


# Sync wrapper for backwards compatibility
def determine_committee_for_topic_sync(onderwerp: str) -> str:
    """
    Synchronous wrapper for committee determination with basic fallback mapping.

    Args:
        onderwerp: Parliamentary topic or agenda item

    Returns:
        Committee name for URL construction
    """
    onderwerp_lower = onderwerp.lower()

    # Basic keyword mapping as fallback
    if "veehouderij" in onderwerp_lower or "dieren" in onderwerp_lower:
        return "landbouw_natuur_en_voedselkwaliteit"
    elif "asiel" in onderwerp_lower or "migratie" in onderwerp_lower:
        return "asiel_en_migratie"
    elif "zorg" in onderwerp_lower or "ouderen" in onderwerp_lower:
        return "volksgezondheid_welzijn_en_sport"
    elif "belasting" in onderwerp_lower or "financien" in onderwerp_lower:
        return "financien"
    elif "energie" in onderwerp_lower or "klimaat" in onderwerp_lower:
        return "economische_zaken_en_klimaat"
    elif "woning" in onderwerp_lower or "huisvesting" in onderwerp_lower:
        return "binnenlandse_zaken"
    elif "algemene" in onderwerp_lower and "beschouwingen" in onderwerp_lower:
        return "plenaire_vergaderingen"
    else:
        return "commissievergaderingen"
