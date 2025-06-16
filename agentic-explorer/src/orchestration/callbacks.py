"""Callback handlers for agent orchestration and streaming."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from semantic_kernel.contents import ChatMessageContent, TextContent
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent

from orchestration.constants import (
    CITATION_END_MARKER,
    CITATION_SOURCE_PREFIX,
    CITATION_START_MARKER,
    COMPLETION_SIGNALS,
    INVALID_DATE_VALUES,
    LOOP_INDICATORS,
    TOOL_DESCRIPTIONS,
    StreamEvents,
    SystemSteps,
)
from skills.committee_mapping_skill.committee_mapping import (
    determine_committee_for_topic_sync,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Record of a tool call and its results."""

    agent: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    timestamp: datetime
    result_ids: Set[str] = field(default_factory=set)

    def __post_init__(self):
        """Extract identifiers from tool results."""
        self.result_ids = self._extract_result_ids()

    def _extract_result_ids(self) -> Set[str]:
        """Extract all identifiers from tool call results."""
        ids = set()

        if isinstance(self.result, list):
            for item in self.result:
                if isinstance(item, dict):
                    # Extract common ID fields
                    for id_field in [
                        "id",
                        "uuid",
                        "nummer",
                        "document_id",
                        "agendapunt_id",
                    ]:
                        if id_field in item and item[id_field]:
                            ids.add(str(item[id_field]))

        elif isinstance(self.result, dict):
            for id_field in ["id", "uuid", "nummer", "document_id", "agendapunt_id"]:
                if id_field in self.result and self.result[id_field]:
                    ids.add(str(self.result[id_field]))

        # Also extract from string representation (for SQL query results)
        elif isinstance(self.result, str):
            ids.update(self._extract_ids_from_string(self.result))

        return ids

    def _extract_ids_from_string(self, result: str) -> Set[str]:
        """Extract IDs from database query string results for citation verification."""
        ids = set()

        # Pattern 1: UUID format (most common in full results)
        uuid_pattern = (
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
        )
        ids.update(re.findall(uuid_pattern, result, re.IGNORECASE))

        # Pattern 2: Document/Case numbers (2025D27695, 2025Z12196, etc.)
        nummer_pattern = r"\b20\d{2}[DZ]\d{4,6}\b"
        ids.update(re.findall(nummer_pattern, result))

        # Pattern 3: Activity numbers (2025A04767, etc.)
        activity_pattern = r"\b20\d{2}A\d{4,6}\b"
        ids.update(re.findall(activity_pattern, result))

        # Pattern 4: Agendapunt IDs or other specific patterns
        # Look for terms that could be matched in citations
        onderwerp_pattern = r'"([^"]*jeugdzorg[^"]*)"'
        onderwerpen = re.findall(onderwerp_pattern, result, re.IGNORECASE)
        for onderwerp in onderwerpen:
            # Use onderwerp as pseudo-ID for matching
            ids.add(f"onderwerp:{onderwerp}")

        logger.debug(
            f"Extracted {len(ids)} IDs from string result: {list(ids)[:3]}..."
        )  # Show first 3
        return ids


@dataclass
class CitationVerifier:
    """Verifies citations against actual tool call results."""

    tool_calls: List[ToolCallRecord] = field(default_factory=list)

    def add_tool_call(self, agent: str, tool_name: str, arguments: Dict, result: Any):
        """Record a tool call result."""
        record = ToolCallRecord(
            agent=agent,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            timestamp=datetime.now(),
        )
        self.tool_calls.append(record)
        logger.debug(
            f"Recorded tool call: {tool_name} -> {len(record.result_ids)} result IDs"
        )

    def verify_citations(
        self, citations: List[Dict[str, str]], agent: str
    ) -> tuple[List[Dict[str, str]], List[str]]:
        """
        Verify citations against tool call results.

        Returns:
            Tuple of (verified_citations, warnings)
        """
        verified_citations = []
        warnings = []

        # Get all result IDs from this agent's tool calls
        agent_result_ids = set()
        for call in self.tool_calls:
            if call.agent == agent:
                agent_result_ids.update(call.result_ids)

        for citation in citations:
            citation_id = self._extract_citation_id(citation)

            if citation_id and citation_id in agent_result_ids:
                # Valid citation - came from tool results
                citation["verified"] = True
                verified_citations.append(citation)
            else:
                # Invalid or unverifiable citation
                if citation_id:
                    warnings.append(
                        f"Citation ID '{citation_id}' not found in tool results"
                    )
                else:
                    warnings.append(f"Citation missing valid ID: {citation}")

                # Mark as unverified but keep with warning
                citation["verified"] = False
                citation["warning"] = "Not verified against tool results"
                verified_citations.append(citation)

        logger.info(
            f"Citation verification for {agent}: {len(verified_citations)} total, "
            f"{sum(1 for c in verified_citations if c.get('verified'))} verified, "
            f"{len(warnings)} warnings"
        )

        return verified_citations, warnings

    def _extract_citation_id(self, citation: Dict[str, str]) -> Optional[str]:
        """Extract primary identifier from citation."""
        for id_field in ["id", "document_id", "agendapunt_id", "uuid"]:
            if id_field in citation and citation[id_field]:
                return str(citation[id_field])
        return None

    def get_verification_stats(self) -> Dict[str, Any]:
        """Get statistics about tool calls and citations."""
        total_calls = len(self.tool_calls)
        total_result_ids = sum(len(call.result_ids) for call in self.tool_calls)

        agents = {}
        for call in self.tool_calls:
            if call.agent not in agents:
                agents[call.agent] = {"tool_calls": 0, "result_ids": 0}
            agents[call.agent]["tool_calls"] += 1
            agents[call.agent]["result_ids"] += len(call.result_ids)

        return {
            "total_tool_calls": total_calls,
            "total_result_ids": total_result_ids,
            "agents": agents,
        }


# Global citation verifier instance
_citation_verifier = CitationVerifier()


def agent_response_callback(message: ChatMessageContent) -> None:
    """Print agent responses for CLI/debug usage."""
    print(f"**{message.name}**\n{message.content}")


def _get_tool_description(tool_name: str) -> str:
    """Get user-friendly description for a tool call."""
    return TOOL_DESCRIPTIONS.get(tool_name, f"gebruikt tool {tool_name}")


def _generate_official_tk_url(nummer: str, soort: str) -> str:
    """Generate official Tweede Kamer URL for document."""
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


def _generate_voting_tk_url(citation_data: Dict[str, str]) -> Optional[str]:
    """
    Generate specialized Tweede Kamer URLs for voting/agenda data.

    Args:
        citation_data: Parsed citation data

    Returns:
        Generated URL or None if not applicable
    """
    cite_type = citation_data.get("type", "")
    cite_id = citation_data.get("id", "")

    # For Agendapunt - try to link to committee/meeting pages
    if cite_type == "Agendapunt":
        onderwerp = citation_data.get("title", "").lower()

        # Check if it's about motions (moties) - try to find document number
        if "moties ingediend" in onderwerp:
            # For motions, try to link to general motions page
            return "https://www.tweedekamer.nl/kamerstukken/moties"

        # Use AI-powered committee mapping
        try:
            committee = determine_committee_for_topic_sync(onderwerp)
            if committee and committee != "commissievergaderingen":
                return f"https://www.tweedekamer.nl/vergaderingen/commissievergaderingen/{committee}"
            else:
                # Fallback to general committee meetings page
                return "https://www.tweedekamer.nl/vergaderingen/commissievergaderingen"
        except Exception as e:
            logger.warning(f"Committee mapping failed for '{onderwerp}': {e}")
            # Fallback to general committee meetings page
            return "https://www.tweedekamer.nl/vergaderingen/commissievergaderingen"

    # For Besluit - link to voting results if we have date
    elif cite_type == "Besluit":
        stemming_datum = citation_data.get("stemming_datum")
        if stemming_datum:
            # Try to construct stemming URL based on date
            return f"https://www.tweedekamer.nl/vergaderingen/plenaire_vergaderingen"
        else:
            return "https://www.tweedekamer.nl/vergaderingen/stemmingen"

    # For known document numbers, use existing document URL generator
    elif cite_type in ["Motie", "Amendement", "Brief regering"] and citation_data.get(
        "document_nummer"
    ):
        return _generate_official_tk_url(citation_data["document_nummer"], cite_type)

    return None


def _parse_citation_line(line: str) -> Optional[Dict[str, str]]:
    """
    Parse a citation line into structured data with enhanced voting support.

    Args:
        line: Citation line starting with SOURCE:

    Returns:
        Parsed citation data or None if parsing fails
    """
    try:
        parts = line[len(CITATION_SOURCE_PREFIX) :].strip()
        cite_data = {}

        # Parse all key="value" pairs
        for match in re.finditer(r'(\w+)="(.*?)"\s*,?', parts):
            key, value = match.groups()

            # Handle invalid date values
            if (
                key in ["publication_date", "stemming_datum"]
                and value in INVALID_DATE_VALUES
            ):
                value = None

            cite_data[key] = value

        # Only accept citations with valid identifiers
        if not (
            cite_data.get("id")
            or cite_data.get("document_id")
            or cite_data.get("agendapunt_id")
        ):
            return None

        cite_type = cite_data.get("type", "")

        # Generate URLs based on citation type
        if cite_type in ["Agendapunt", "Besluit"]:
            # Use specialized voting URL generator
            voting_url = _generate_voting_tk_url(cite_data)
            if voting_url:
                cite_data["uri"] = voting_url

        elif cite_type in ["Motie", "Amendement", "Brief regering"]:
            # Use document URL generator
            nummer = cite_data.get("document_nummer") or cite_data.get("id")
            if nummer and cite_type:
                cite_data["uri"] = _generate_official_tk_url(nummer, cite_type)

        # Add enhanced metadata for voting citations
        if cite_type == "Agendapunt":
            cite_data["category"] = "Parlementaire Agenda"
            cite_data["description"] = (
                f"Agendapunt: {cite_data.get('title', 'Onbekend onderwerp')}"
            )

        elif cite_type == "Besluit":
            cite_data["category"] = "Stemmingsuitslag"
            resultaat = cite_data.get("resultaat", "Onbekend")
            cite_data["description"] = f"Besluit: {resultaat}"

        elif cite_type in ["Motie", "Amendement"]:
            cite_data["category"] = "Parlementair Document"
            cite_data["description"] = (
                f"{cite_type}: {cite_data.get('title', 'Onbekend document')}"
            )

        # Add voting context if available
        if cite_data.get("fractie") and cite_data.get("stem_type"):
            fractie = cite_data.get("fractie")
            stem_type = cite_data.get("stem_type")
            aantal = cite_data.get("aantal_stemmingen", "")

            if aantal:
                cite_data["voting_context"] = f"{fractie}: {aantal}x {stem_type}"
            else:
                cite_data["voting_context"] = f"{fractie}: {stem_type}"

        return cite_data

    except Exception as e:
        logger.error(f"Error parsing citation line '{line}': {e}")

    return None


def _extract_citations(
    text_content: str, agent_name: str
) -> tuple[str, List[Dict[str, str]], List[str]]:
    """
    Extract and verify citations from agent response text.

    Args:
        text_content: The agent's response text
        agent_name: Name of the agent for logging

    Returns:
        Tuple of (processed_text, verified_citations, warnings)
    """
    logger.info(f"Processing message from {agent_name} for citations")

    citation_block_match = re.search(
        f"{CITATION_START_MARKER}(.*?){CITATION_END_MARKER}", text_content, re.DOTALL
    )

    if not citation_block_match:
        logger.debug(f"No citation block found in {agent_name} response")
        return text_content, [], []

    # Remove citation block from text
    processed_text = (
        text_content[: citation_block_match.start()].rstrip()
        + text_content[citation_block_match.end() :].lstrip()
    )

    # Parse citations
    citation_lines = citation_block_match.group(1).strip().split("\n")
    parsed_citations = []

    for line in citation_lines:
        if line.startswith(CITATION_SOURCE_PREFIX):
            citation = _parse_citation_line(line)
            if citation:
                parsed_citations.append(citation)

    # Verify citations against tool call results
    verified_citations, warnings = _citation_verifier.verify_citations(
        parsed_citations, agent_name
    )

    logger.info(
        f"Extracted {len(parsed_citations)} citations from {agent_name}, "
        f"{len(verified_citations)} verified, {len(warnings)} warnings"
    )

    return processed_text, verified_citations, warnings


async def _emit_event(queue: asyncio.Queue, event_data: Dict) -> None:
    """Emit an event to the streaming queue."""
    try:
        await queue.put(json.dumps(event_data))
    except Exception as e:
        logger.error(f"Failed to emit event: {e}")


def make_streaming_callback(
    queue: asyncio.Queue,
) -> Callable[[ChatMessageContent], None]:
    """
    Create a streaming callback for agent messages.

    Args:
        queue: Queue for streaming events

    Returns:
        Callback function for processing agent messages
    """

    def streaming_callback(message: ChatMessageContent) -> None:
        """Process agent messages and emit streaming events."""
        try:
            # Extract text content
            text_content = ""
            if message.items and isinstance(message.items[0], TextContent):
                text_content = message.items[0].text
            elif isinstance(message.content, str):
                text_content = message.content

            agent_name = message.name or "Unknown"

            # Emit agent start event
            if text_content and text_content.strip():
                asyncio.create_task(
                    _emit_event(
                        queue,
                        {
                            "event": StreamEvents.AGENT_START,
                            "agent": agent_name,
                            "message": f"{agent_name} begint met antwoorden...",
                        },
                    )
                )

            # Process tool calls
            has_tool_calls = False
            if message.items:
                for item in message.items:
                    if isinstance(item, FunctionCallContent):
                        has_tool_calls = True
                        tool_description = _get_tool_description(item.name)

                        asyncio.create_task(
                            _emit_event(
                                queue,
                                {
                                    "event": StreamEvents.AGENT_TOOL_CALL,
                                    "agent": agent_name,
                                    "tool": tool_description,
                                    "message": f"🔍 {agent_name} {tool_description}...",
                                },
                            )
                        )

                    elif isinstance(item, FunctionResultContent):
                        # Record tool call result for citation verification
                        _citation_verifier.add_tool_call(
                            agent=agent_name,
                            tool_name=item.name,
                            arguments={},  # Arguments not available in result content
                            result=item.result,
                        )

                        tool_description = _get_tool_description(item.name)
                        asyncio.create_task(
                            _emit_event(
                                queue,
                                {
                                    "event": StreamEvents.AGENT_TOOL_RESULT,
                                    "agent": agent_name,
                                    "tool": tool_description,
                                    "message": f"✓ {agent_name} heeft zoekresultaten ontvangen",
                                },
                            )
                        )

            # Process citations for all agents that have content
            processed_text = text_content
            citations = []
            if text_content.strip():
                # Emit citation processing start
                asyncio.create_task(
                    _emit_event(
                        queue,
                        {
                            "event": StreamEvents.SYSTEM,
                            "step": SystemSteps.CITATION_PROCESSING,
                            "message": "Bronvermeldingen opbouwen...",
                        },
                    )
                )

                processed_text, citations, warnings = _extract_citations(
                    text_content, agent_name
                )

                # Check citation compliance
                citation_compliance_warnings = _check_citation_compliance(
                    text_content, agent_name, has_tool_calls
                )

                if citation_compliance_warnings:
                    asyncio.create_task(
                        _emit_event(
                            queue,
                            {
                                "event": StreamEvents.CITATION_WARNINGS,
                                "agent": agent_name,
                                "warnings": citation_compliance_warnings,
                                "message": f"⚠️ Citation compliance issues: {len(citation_compliance_warnings)} warnings",
                            },
                        )
                    )

                if citations:
                    asyncio.create_task(
                        _emit_event(
                            queue,
                            {
                                "event": StreamEvents.CITATIONS_FOUND,
                                "agent": agent_name,
                                "citations": citations,
                                "warnings": warnings,
                            },
                        )
                    )

                    # Emit citation processing completion with verification stats
                    verified_count = sum(
                        1 for c in citations if c.get("verified", True)
                    )
                    total_count = len(citations)

                    if warnings:
                        # Emit citation warnings
                        asyncio.create_task(
                            _emit_event(
                                queue,
                                {
                                    "event": StreamEvents.CITATION_WARNINGS,
                                    "agent": agent_name,
                                    "warnings": warnings,
                                    "message": f"⚠️ {len(warnings)} citation verification warnings",
                                },
                            )
                        )

                    asyncio.create_task(
                        _emit_event(
                            queue,
                            {
                                "event": StreamEvents.SYSTEM,
                                "step": SystemSteps.CITATION_PROCESSING_DONE,
                                "message": f"Bronvermeldingen verwerkt ({verified_count}/{total_count} geverifieerd)",
                            },
                        )
                    )

            # Emit completion event
            if processed_text.strip() and not has_tool_calls:
                # Check for completion signals
                completion_signal = _check_completion_signal(processed_text)
                if completion_signal:
                    asyncio.create_task(
                        _emit_event(
                            queue,
                            {
                                "event": StreamEvents.AGENT_COMPLETE,
                                "agent": agent_name,
                                "completion_signal": completion_signal,
                                "message": f"{agent_name} heeft taak voltooid: {completion_signal}",
                            },
                        )
                    )
                else:
                    asyncio.create_task(
                        _emit_event(
                            queue,
                            {
                                "event": StreamEvents.AGENT_COMPLETE,
                                "agent": agent_name,
                                "message": f"{agent_name} heeft antwoord voltooid",
                            },
                        )
                    )

                # Check for loop indicators
                loop_indicators = _check_loop_indicators(processed_text)
                if loop_indicators:
                    asyncio.create_task(
                        _emit_event(
                            queue,
                            {
                                "event": StreamEvents.LOOP_DETECTED,
                                "agent": agent_name,
                                "indicators": loop_indicators,
                                "message": f"⚠️ Mogelijke loop gedetecteerd bij {agent_name}",
                            },
                        )
                    )

            # Emit thought event
            if processed_text.strip():
                asyncio.create_task(
                    _emit_event(
                        queue,
                        {
                            "event": StreamEvents.THOUGHT,
                            "agent": agent_name,
                            "text": processed_text.strip(),
                        },
                    )
                )

        except Exception as e:
            logger.error(f"Error in streaming callback: {e}", exc_info=True)

    return streaming_callback


async def tool_call_debug_handler(message: ChatMessageContent) -> None:
    """
    Debug handler for detailed tool call logging.

    This handler logs all function calls and results during agent execution
    for debugging and monitoring purposes.
    """
    agent_name = message.name or "Unknown"

    try:
        if message.items:
            for item in message.items:
                if isinstance(item, FunctionCallContent):
                    logger.info(
                        f"TOOL CALL [{agent_name}]: {item.name} with args: {item.arguments}"
                    )
                    print(
                        f"TOOL CALL [{agent_name}]: {item.name} with args: {item.arguments}"
                    )

                elif isinstance(item, FunctionResultContent):
                    # Truncate long results for readability
                    result_str = str(item.result)
                    if len(result_str) > 500:
                        result_str = result_str[:250] + "..." + result_str[-250:]

                    logger.info(
                        f"TOOL RESULT [{agent_name}]: {item.name} returned: {result_str}"
                    )
                    print(
                        f"TOOL RESULT [{agent_name}]: {item.name} returned length {len(str(item.result))}"
                    )

        # Log content-only messages
        elif message.content:
            role = message.role or "UNKNOWN"
            content_preview = str(message.content)[:100]
            logger.info(f"MESSAGE [{agent_name}/{role}]: {content_preview}...")
            print(f"MESSAGE [{agent_name}/{role}]: {content_preview}...")

    except Exception as e:
        logger.error(f"Error in tool call debug handler: {e}", exc_info=True)


def _check_completion_signal(text: str) -> Optional[str]:
    """Check if text contains a completion signal."""
    for signal in COMPLETION_SIGNALS:
        if signal in text:
            return signal
    return None


def _check_citation_compliance(
    text: str, agent_name: str, has_tool_calls: bool
) -> List[str]:
    """
    Check if agent response complies with citation requirements.

    Returns list of compliance warnings.
    """
    warnings = []

    # Check for citation block
    has_citation_block = CITATION_START_MARKER in text and CITATION_END_MARKER in text

    # Check for completion signals that indicate citations should be present
    has_completion_signals = any(signal in text for signal in COMPLETION_SIGNALS)

    if not has_citation_block:
        if has_tool_calls:
            warnings.append(
                f"{agent_name}: VERPLICHTE CITATIONS ONTBREKEN - Agent heeft database queries uitgevoerd maar geen bronvermelding toegevoegd!"
            )
        elif has_completion_signals:
            warnings.append(
                f"{agent_name}: VERPLICHTE CITATIONS ONTBREKEN - Agent gebruikt completion signals maar heeft geen bronvermelding!"
            )
        elif len(text.strip()) > 100:  # Substantial response
            warnings.append(
                f"{agent_name}: BRONVERMELDING VERWACHT - Uitgebreid antwoord zonder citations!"
            )

    # Check citation quality if block exists
    if has_citation_block:
        citation_content = re.search(
            f"{CITATION_START_MARKER}(.*?){CITATION_END_MARKER}", text, re.DOTALL
        )
        if citation_content:
            citations_text = citation_content.group(1).strip()
            citation_lines = [
                line
                for line in citations_text.split("\n")
                if line.startswith(CITATION_SOURCE_PREFIX)
            ]

            if len(citation_lines) == 0:
                warnings.append(
                    f"{agent_name}: LEGE CITATIONS BLOCK - Citations block aanwezig maar geen SOURCE entries!"
                )
            elif has_tool_calls and len(citation_lines) < 1:
                warnings.append(
                    f"{agent_name}: MINIMALE CITATIONS - Verwacht meer bronvermeldingen bij database queries!"
                )

    return warnings


def _check_loop_indicators(text: str) -> List[str]:
    """
    Check if text contains loop indicators.

    Args:
        text: Text to check for loop patterns

    Returns:
        List of found loop indicators
    """
    found_indicators = []
    text_lower = text.lower()

    for indicator in LOOP_INDICATORS:
        if indicator.lower() in text_lower:
            found_indicators.append(indicator)

    return found_indicators


def get_citation_verification_stats() -> Dict[str, Any]:
    """
    Get citation verification statistics.

    Returns:
        Dictionary with verification statistics
    """
    return _citation_verifier.get_verification_stats()


def reset_citation_verifier():
    """Reset the citation verifier for a new conversation."""
    global _citation_verifier
    _citation_verifier = CitationVerifier()
    logger.info("Citation verifier reset for new conversation")
