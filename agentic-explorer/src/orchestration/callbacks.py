import asyncio
import json
import logging
import re
from typing import Awaitable, Callable

from semantic_kernel.contents import ChatMessageContent, TextContent
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent

logger = logging.getLogger("mcp_debug")

# Print-based callback for CLI/debug


def agent_response_callback(message: ChatMessageContent) -> None:
    """Observer function to print the messages from the agents."""
    print(f"**{message.name}**\n{message.content}")


# Streaming callback for FastAPI SSE endpoints


def make_streaming_callback(queue: asyncio.Queue):
    """Returns a callback that processes agent messages.
    It puts 'thought' events into the queue.
    If citations are found in ArchivistAgent messages, it strips them from the text
    and puts a separate 'citations_found' event onto the queue.
    Enhanced to provide more detailed agent interaction information.
    """

    def streaming_callback(message: ChatMessageContent):
        text_content = ""
        if message.items and isinstance(message.items[0], TextContent):
            text_content = message.items[0].text
        elif isinstance(message.content, str):
            text_content = message.content

        # Enhanced agent interaction tracking
        agent_name = message.name or "Unknown"

        # Check if this is the start of an agent response
        if text_content and len(text_content.strip()) > 0:
            # Send agent start event
            agent_start_payload = {
                "event": "agent_start",
                "agent": agent_name,
                "message": f"{agent_name} begint met antwoorden...",
            }
            asyncio.create_task(queue.put(json.dumps(agent_start_payload)))

        # Check for function/tool calls in the message
        has_tool_calls = False
        for item in message.items or []:
            if isinstance(item, FunctionCallContent):
                has_tool_calls = True
                # Create a more descriptive tool call message
                tool_description = ""
                if item.name == "search":
                    tool_description = "zoekt in documentendatabase"
                elif item.name == "list_indices":
                    tool_description = "haalt beschikbare databases op"
                elif item.name == "get_mappings":
                    tool_description = "analyseert database structuur"
                else:
                    tool_description = f"gebruikt tool {item.name}"

                tool_payload = {
                    "event": "agent_tool_call",
                    "agent": agent_name,
                    "tool": item.name,
                    "message": f"🔍 {agent_name} {tool_description}...",
                }
                asyncio.create_task(queue.put(json.dumps(tool_payload)))
            elif isinstance(item, FunctionResultContent):
                tool_result_payload = {
                    "event": "agent_tool_result",
                    "agent": agent_name,
                    "tool": item.name,
                    "message": f"✓ {agent_name} heeft zoekresultaten ontvangen",
                }
                asyncio.create_task(queue.put(json.dumps(tool_result_payload)))

        processed_text = text_content
        parsed_citations = []

        if message.name and (
            "ArchivistAgent" in message.name
            or "ResearchAgent" in message.name
            or "Agent" in message.name
        ):
            logger.info(
                f"CALLBACKS: Received message from {message.name}. Raw text_content trying to parse for citations: <<<\n{text_content}\n>>>"
            )
            citation_block_match = re.search(
                r"USED_SOURCES_START(.*?)USED_SOURCES_END", text_content, re.DOTALL
            )
            logger.info(
                f"CALLBACKS: citation_block_match result: {citation_block_match}"
            )
            if citation_block_match:
                # Remove the citation block from the text that will be part of the "thought" event
                processed_text = (
                    text_content[: citation_block_match.start()].rstrip()
                    + text_content[citation_block_match.end() :].lstrip()
                )

                citation_lines = citation_block_match.group(1).strip().split("\n")
                for line in citation_lines:
                    if line.startswith("SOURCE:"):
                        try:
                            parts = line[len("SOURCE:") :].strip()
                            cite_data = {}
                            for match in re.finditer(r'(\w+)="(.*?)"\s*,?', parts):
                                key, value = match.groups()
                                # Handle publication_date - avoid "N/A" or "Invalid Date"
                                if key == "publication_date" and value in [
                                    "N/A",
                                    "Invalid Date",
                                    "",
                                    "null",
                                    "None",
                                ]:
                                    value = None
                                cite_data[key] = value
                            # Accept citations with either 'id' or 'document_id' field
                            if cite_data.get("id") or cite_data.get("document_id"):
                                parsed_citations.append(cite_data)
                        except Exception as e:
                            logger.error(f"Error parsing citation line '{line}': {e}")
            logger.info(f"CALLBACKS: parsed_citations: {parsed_citations}")

            # If citations were parsed, put a special event on the queue for them
            if parsed_citations:
                citation_payload = {
                    "event": "citations_found",  # Custom event type
                    "agent": message.name,  # Keep agent name for context if needed
                    "citations": parsed_citations,
                }
                logger.info(f"CITATIONS PAYLOAD: {json.dumps(citation_payload)}")
                # Log citation properties to better understand their structure
                if parsed_citations:
                    logger.info(
                        f"CITATION PROPERTIES: {list(parsed_citations[0].keys())}"
                    )
                asyncio.create_task(queue.put(json.dumps(citation_payload)))

        # Send agent completion event if this appears to be a final response
        if processed_text.strip() and not has_tool_calls:
            agent_complete_payload = {
                "event": "agent_complete",
                "agent": agent_name,
                "message": f"{agent_name} heeft antwoord voltooid",
            }
            asyncio.create_task(queue.put(json.dumps(agent_complete_payload)))

        # Always send the (potentially modified) thought/text content
        if processed_text.strip():  # Only send if there's actual content
            thought_payload = {
                "event": "thought",
                "agent": message.name,
                "text": processed_text.strip(),
            }
            logger.info(f"THOUGHT PAYLOAD: {json.dumps(thought_payload)}")
            asyncio.create_task(queue.put(json.dumps(thought_payload)))

    return streaming_callback


async def tool_call_debug_handler(message: ChatMessageContent) -> None:
    """Detailed handler for intermediate messages to debug function/tool calls.

    This callback is passed to agent.invoke's on_intermediate_message parameter
    to capture and log all function calls and results during agent execution.
    """
    agent_name = message.name or "Unknown"

    # Check if this message has any function calls or results
    for item in message.items or []:
        if isinstance(item, FunctionCallContent):
            logger.info(
                f"TOOL CALL [{agent_name}]: {item.name} with args: {item.arguments}"
            )
            print(f"TOOL CALL [{agent_name}]: {item.name} with args: {item.arguments}")

        elif isinstance(item, FunctionResultContent):
            # Truncate long results to keep logs readable
            result_str = str(item.result)
            if len(result_str) > 500:
                result_str = result_str[:250] + "..." + result_str[-250:]

            logger.info(
                f"TOOL RESULT [{agent_name}]: {item.name} returned: {result_str}"
            )
            print(
                f"TOOL RESULT [{agent_name}]: {item.name} returned length {len(str(item.result))}"
            )

    # If there are no function items but there's content, log that too
    if not message.items and message.content:
        role = message.role or "UNKNOWN"
        logger.info(f"MESSAGE [{agent_name}/{role}]: {message.content[:100]}...")
        print(f"MESSAGE [{agent_name}/{role}]: {message.content[:100]}...")
