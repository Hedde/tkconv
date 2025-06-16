"""Constants for orchestration configuration."""

# Orchestration limits
DEFAULT_MAX_ROUND_COUNT = 8  # Increased for complex multi-agent queries
DEFAULT_MAX_RESET_COUNT = 1
DEFAULT_MAX_STALL_COUNT = 3  # Slightly more tolerance

# Streaming configuration
STREAMING_MAX_ROUND_COUNT = 10  # More rounds for complex questions
STREAMING_MAX_RESET_COUNT = 1
STREAMING_MAX_STALL_COUNT = 3  # More stall tolerance

# Tool descriptions for UI feedback - only for tools actually used by agents
TOOL_DESCRIPTIONS = {
    "mcp_MCP_SQLite_Server_db_info": "controleert database",
    "mcp_MCP_SQLite_Server_list_tables": "bekijkt tabellen",
    "mcp_MCP_SQLite_Server_get_table_schema": "controleert structuur",
    "mcp_MCP_SQLite_Server_query": "zoekt in parlementaire data",
    "mcp_MCP_SQLite_Server_read_records": "haalt records op",
    "mcp_MCP_SQLite_Server_create_record": "voegt data toe",
    "mcp_MCP_SQLite_Server_update_records": "werkt data bij",
    "mcp_MCP_SQLite_Server_delete_records": "verwijdert data",
    "mcp_MCP_SQLite_Server_search_politicians": "zoekt politici",
    "mcp_MCP_SQLite_Server_get_political_parties": "haalt partijen op",
    "mcp_MCP_SQLite_Server_search_documents": "zoekt documenten",
    "mcp_MCP_SQLite_Server_search_full_text": "doorzoekt volledige document inhoud",
    "mcp_MCP_SQLite_Server_get_document_content": "haalt specifieke document content op",
}

# Database information for agents
DATABASE_INFO = {
    "metadata_db": {
        "name": "tk.sqlite3",
        "description": "Hoofddatabase met alle metadata",
        "tables": [
            "Document",
            "Persoon",
            "Fractie",
            "Zaak",
            "Activiteit",
            "Stemming",
            "Agendapunt",
        ],
        "usage": "Gebruik voor overzichten, metadata, en structurele queries",
    },
    "fulltext_db": {
        "name": "tkindex-minimal.sqlite3",
        "description": "Full-text search database met volledige documentinhoud",
        "tables": ["docsearch"],
        "usage": "Gebruik alleen voor citaten, specifieke tekstpassages, of volledige inhoud",
        "note": "⚠️ Context window bewust! Beperk queries tot 5-8 resultaten max",
    },
}

# Citation parsing patterns
CITATION_START_MARKER = "USED_SOURCES_START"
CITATION_END_MARKER = "USED_SOURCES_END"
CITATION_SOURCE_PREFIX = "SOURCE:"

# Invalid date values for citation processing
INVALID_DATE_VALUES = {"N/A", "Invalid Date", "", "null", "None"}

# Completion signals that agents should use
COMPLETION_SIGNALS = [
    "✅ DATABASE GERAADPLEEGD",
    "✅ BRONNEN VERMELD",  # Added this as first priority
    "✅ CITATIONS TOEGEVOEGD",  # Added this as mandatory
    "✅ DOCUMENTEN DATA COMPLEET",
    "✅ PERSONEN DATA COMPLEET",
    "✅ STEMMINGS DATA GEZOCHT",
    "✅ ZAAK DATA COMPLEET",
    "✅ ANTWOORD GEGEVEN",
    "✅ DOCUMENT ANTWOORD GEGEVEN",
    "✅ STEMMING ANTWOORD GEGEVEN",
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
    CITATION_WARNINGS = "citation_warnings"
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
    CITATION_PROCESSING = "citation_processing"
    CITATION_PROCESSING_DONE = "citation_processing_done"
