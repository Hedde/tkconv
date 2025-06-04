"""Constants for orchestration configuration."""

# Orchestration limits
DEFAULT_MAX_ROUND_COUNT = 3
DEFAULT_MAX_RESET_COUNT = 1
DEFAULT_MAX_STALL_COUNT = 2

# Streaming configuration
STREAMING_MAX_ROUND_COUNT = 4
STREAMING_MAX_RESET_COUNT = 1
STREAMING_MAX_STALL_COUNT = 2

# Tool descriptions for UI feedback
TOOL_DESCRIPTIONS = {
    "search": "zoekt in documentendatabase",
    "list_indices": "haalt beschikbare databases op",
    "get_mappings": "analyseert database structuur",
    "query": "voert database query uit",
    "search_politicians": "zoekt naar politici",
    "read_records": "leest database records",
    "list_tables": "toont database tabellen",
}

# Citation parsing patterns
CITATION_START_MARKER = "USED_SOURCES_START"
CITATION_END_MARKER = "USED_SOURCES_END"
CITATION_SOURCE_PREFIX = "SOURCE:"

# Invalid date values for citation processing
INVALID_DATE_VALUES = {"N/A", "Invalid Date", "", "null", "None"}

# Completion signals for task completion detection
COMPLETION_SIGNALS = [
    "✅ TAAK VOLTOOID",
    "✅ PARLEMENTAIRE DATA COMPLEET",
    "✅ INFORMATIE BESCHIKBAAR",
    "✅ DATABASE GERAADPLEEGD",
    "✅ ANTWOORD GEGEVEN",
]

# Loop detection patterns
LOOP_INDICATORS = [
    "Function failed",
    "Parameter parsing",
    "expected to be parsed to",
    "Error invoking function",
    "laat me het anders proberen",
    "ik zal een andere zoekmethode proberen",
]


# Event names for streaming
class StreamEvents:
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_TOOL_CALL = "agent_tool_call"
    AGENT_TOOL_RESULT = "agent_tool_result"
    THOUGHT = "thought"
    CITATIONS_FOUND = "citations_found"
    LOOP_DETECTED = "loop_detected"
    SYSTEM = "system"
    TOKEN = "token"
    DONE = "done"


# System step names
class SystemSteps:
    RECEIVED = "received"
    INIT_AGENTS = "init_agents"
    INIT_AGENTS_DONE = "init_agents_done"
    START_ORCHESTRATION = "start_orchestration"
    ORCHESTRATION_STARTED = "orchestration_started"
    WAITING_FOR_RESULT = "waiting_for_result"
    RESULT_READY = "result_ready"
    PLANNING = "planning"
    PLANNING_DONE = "planning_done"
    PROGRESS_LEDGER = "progress_ledger"
    PROGRESS_LEDGER_DONE = "progress_ledger_done"
    FINALIZING = "finalizing"
    AGENT_SELECTION = "agent_selection"
    AGENT_SELECTED = "agent_selected"
    EVALUATING_COMPLETION = "evaluating_completion"
    COMPLETION_EVALUATED = "completion_evaluated"
    SELECTING_SPEAKER = "selecting_speaker"
    SPEAKER_SELECTED = "speaker_selected"
