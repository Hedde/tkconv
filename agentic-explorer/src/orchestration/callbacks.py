"""Callback handlers for agent orchestration and streaming."""

import asyncio
import json
import logging
import re
from typing import Awaitable, Callable, Dict, List, Optional

from orchestration.constants import (
    CITATION_END_MARKER,
    CITATION_SOURCE_PREFIX,
    CITATION_START_MARKER,
    COMPLETION_SIGNALS,
    INVALID_DATE_VALUES,
    LOOP_INDICATORS,
    TOOL_DESCRIPTIONS,
    StreamEvents,
)
from semantic_kernel.contents import ChatMessageContent, TextContent
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent

logger = logging.getLogger(__name__)


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


def _parse_citation_line(line: str) -> Optional[Dict[str, str]]:
    """
    Parse a citation line into structured data.

    Args:
        line: Citation line starting with SOURCE:

    Returns:
        Parsed citation data or None if parsing fails
    """
    try:
        parts = line[len(CITATION_SOURCE_PREFIX) :].strip()
        cite_data = {}

        for match in re.finditer(r'(\w+)="(.*?)"\s*,?', parts):
            key, value = match.groups()

            # Handle invalid date values
            if key == "publication_date" and value in INVALID_DATE_VALUES:
                value = None

            cite_data[key] = value

        # Only accept citations with valid identifiers
        if cite_data.get("id") or cite_data.get("document_id"):
            # Generate TK URL if we have nummer and type
            nummer = cite_data.get("document_nummer") or cite_data.get("id")
            soort = cite_data.get("type", "")

            if nummer:
                cite_data["uri"] = _generate_official_tk_url(nummer, soort)

            return cite_data

    except Exception as e:
        logger.error(f"Error parsing citation line '{line}': {e}")

    return None


def _extract_citations(
    text_content: str, agent_name: str
) -> tuple[str, List[Dict[str, str]]]:
    """
    Extract citations from agent response text.

    Args:
        text_content: The agent's response text
        agent_name: Name of the agent for logging

    Returns:
        Tuple of (processed_text, parsed_citations)
    """
    logger.info(f"Processing message from {agent_name} for citations")

    citation_block_match = re.search(
        f"{CITATION_START_MARKER}(.*?){CITATION_END_MARKER}", text_content, re.DOTALL
    )

    if not citation_block_match:
        logger.debug(f"No citation block found in {agent_name} response")
        return text_content, []

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

    logger.info(f"Extracted {len(parsed_citations)} citations from {agent_name}")
    return processed_text, parsed_citations


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
                                    "tool": item.name,
                                    "message": f"🔍 {agent_name} {tool_description}...",
                                },
                            )
                        )

                    elif isinstance(item, FunctionResultContent):
                        asyncio.create_task(
                            _emit_event(
                                queue,
                                {
                                    "event": StreamEvents.AGENT_TOOL_RESULT,
                                    "agent": agent_name,
                                    "tool": item.name,
                                    "message": f"✓ {agent_name} heeft zoekresultaten ontvangen",
                                },
                            )
                        )

            # Process citations for relevant agents
            processed_text = text_content
            if message.name and (
                "Agent" in message.name or "ResearchAgent" in message.name
            ):
                processed_text, citations = _extract_citations(text_content, agent_name)

                if citations:
                    asyncio.create_task(
                        _emit_event(
                            queue,
                            {
                                "event": StreamEvents.CITATIONS_FOUND,
                                "agent": agent_name,
                                "citations": citations,
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
    """
    Check if text contains any completion signal.

    Args:
        text: Text to check for completion signals

    Returns:
        Found completion signal or None
    """
    for signal in COMPLETION_SIGNALS:
        if signal in text:
            return signal
    return None


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
