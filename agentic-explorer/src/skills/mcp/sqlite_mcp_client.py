import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Tuple

from semantic_kernel.connectors.mcp import MCPStdioPlugin
from semantic_kernel.contents.text_content import TextContent
from semantic_kernel.functions import KernelArguments, kernel_function

# Constants
DEFAULT_SEARCH_LIMIT = 10
DEFAULT_DOCUMENT_SEARCH_LIMIT = 20
MAX_CANDIDATE_COUNT = 50
TRUNCATE_RESULT_LENGTH = 500
TRUNCATE_PREVIEW_LENGTH = 250

# Database path constants
CONTAINER_DB_PATH = "/app/db-export/tk.sqlite3"
LOCAL_DB_RELATIVE_PATH = Path("..", "..", "data", "tk.sqlite3")

# Logging constants
LOG_PREFIX_DEBUG = "🔍 DEBUG:"
LOG_PREFIX_INFO = "SQLite MCP:"

# SQL query templates
POLITICIAN_SEARCH_SQL = """
SELECT * FROM Persoon 
WHERE (achternaam LIKE ? OR voornamen LIKE ? OR roepnaam LIKE ?)
"""

DOCUMENT_SEARCH_BASE_SQL = "SELECT * FROM Document WHERE 1=1"


class SQLiteMCPClient:
    """
    Native Semantic-Kernel plugin for SQLite Municipal Content Platform (MCP) server.

    Provides comprehensive database operations for the Dutch parliamentary database (tkconv)
    containing information about politicians, parties, documents, meetings, and votes.

    Available operations:
        • Database info and schema discovery
        • Raw SQL queries with parameter binding
        • CRUD operations (read, create, update, delete)
        • Specialized parliamentary data searches
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize SQLite MCP client with database path resolution.

        Args:
            db_path: Optional explicit database path
        """
        self.db_path = self._resolve_database_path(db_path)
        self._log = logging.getLogger("mcp.sqlite_client")
        self._tables_cache: List[str] = []
        self._schema_cache: Dict[str, List[Dict]] = {}

        self._log_initialization_status()

    def _resolve_database_path(self, explicit_path: Optional[str]) -> str:
        """
        Resolve database path using priority order: explicit > env > container > local.

        Args:
            explicit_path: Explicitly provided database path

        Returns:
            Resolved database path
        """
        if explicit_path:
            return explicit_path

        env_path = os.getenv("TKCONV_DB_PATH")
        if env_path:
            return env_path

        if Path(CONTAINER_DB_PATH).exists():
            return CONTAINER_DB_PATH

        # Construct local path relative to this file
        local_path = (
            Path(__file__).parent.parent.parent / LOCAL_DB_RELATIVE_PATH
        ).resolve()
        return str(local_path)

    def _log_initialization_status(self) -> None:
        """Log detailed initialization status for debugging."""
        self._log.info(f"{LOG_PREFIX_INFO} Initialized with db_path: {self.db_path}")
        self._log.info(
            f"{LOG_PREFIX_INFO} TKCONV_DB_PATH: {os.getenv('TKCONV_DB_PATH')}"
        )
        self._log.info(
            f"{LOG_PREFIX_INFO} Container path exists: {Path(CONTAINER_DB_PATH).exists()}"
        )

        db_path_obj = Path(self.db_path)
        self._log.info(
            f"{LOG_PREFIX_INFO} Selected file exists: {db_path_obj.exists()}"
        )

        if db_path_obj.exists():
            try:
                file_size = db_path_obj.stat().st_size
                self._log.info(f"{LOG_PREFIX_INFO} Database size: {file_size} bytes")
            except OSError as e:
                self._log.warning(f"{LOG_PREFIX_INFO} Could not get file size: {e}")

        # Log directory contents for debugging
        if db_path_obj.parent.exists():
            try:
                dir_contents = list(db_path_obj.parent.iterdir())
                self._log.info(
                    f"{LOG_PREFIX_INFO} Directory contents: {[p.name for p in dir_contents]}"
                )
            except OSError as e:
                self._log.warning(f"{LOG_PREFIX_INFO} Could not list directory: {e}")

    async def _call_tool(self, name: str, **kwargs) -> Any:
        """
        Launch SQLite MCP server and invoke specified tool.

        Args:
            name: Tool name to invoke
            **kwargs: Tool arguments

        Returns:
            Tool execution result

        Raises:
            FileNotFoundError: If database file doesn't exist
            RuntimeError: If tool execution fails
        """
        self._log.info(f"{LOG_PREFIX_INFO} Invoking tool {name} with args: {kwargs}")

        if not Path(self.db_path).exists():
            error_msg = f"Database file not found: {self.db_path}"
            self._log.error(error_msg)
            raise FileNotFoundError(error_msg)

        cmd = f'npx -y mcp-sqlite "{self.db_path}"'
        self._log.debug(f"{LOG_PREFIX_INFO} Command: {cmd}")

        try:
            async with MCPStdioPlugin(
                name="SQLiteMCP",
                command="sh",
                args=["-c", cmd],
                load_tools=True,
                load_prompts=False,
            ) as mcp_plugin:
                tool = getattr(mcp_plugin, name, None)
                if not tool:
                    raise RuntimeError(f"Tool {name} not found in SQLite MCP plugin")

                result = await tool(**kwargs)
                self._log.info(f"{LOG_PREFIX_INFO} Tool {name} completed successfully")
                return result

        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Tool {name} failed: {e}", exc_info=True)
            raise

    def _convert_parameter_values(
        self, values: Optional[List[Any]]
    ) -> Optional[List[str]]:
        """
        Convert parameter values to strings for SQLite binding.

        Args:
            values: Raw parameter values

        Returns:
            String-converted parameters or None
        """
        if not values:
            return None

        # Handle string input (JSON parsing)
        if isinstance(values, str):
            try:
                values = json.loads(values)
            except (json.JSONDecodeError, ValueError):
                values = [values]
        elif not isinstance(values, list):
            values = [values]

        # Convert to strings for SQLite
        return [str(v) if v is not None else None for v in values]

    def _parse_conditions_parameter(self, conditions: Any) -> Optional[Dict[str, Any]]:
        """
        Parse and validate conditions parameter.

        Args:
            conditions: Raw conditions input

        Returns:
            Parsed conditions dictionary or None
        """
        if not conditions:
            return None

        if isinstance(conditions, str):
            try:
                return json.loads(conditions)
            except (json.JSONDecodeError, ValueError):
                self._log.warning(f"Could not parse conditions as JSON: {conditions}")
                return None

        return conditions if isinstance(conditions, dict) else None

    def _build_search_sql(
        self,
        search_term: Optional[str],
        document_type: Optional[str],
        date_from: Optional[str],
        date_to: Optional[str],
        limit: int,
    ) -> Tuple[str, List[str]]:
        """
        Build SQL query for document search.

        Args:
            search_term: Text to search for
            document_type: Document type filter
            date_from: Start date filter
            date_to: End date filter
            limit: Result limit

        Returns:
            Tuple of (SQL query, parameters)
        """
        sql_parts = [DOCUMENT_SEARCH_BASE_SQL]
        params = []

        if search_term:
            sql_parts.append("AND (titel LIKE ? OR onderwerp LIKE ?)")
            params.extend([f"%{search_term}%", f"%{search_term}%"])

        if document_type:
            sql_parts.append("AND soort = ?")
            params.append(document_type)

        if date_from:
            sql_parts.append("AND datum >= ?")
            params.append(date_from)

        if date_to:
            sql_parts.append("AND datum <= ?")
            params.append(date_to)

        sql_parts.extend(["ORDER BY datum DESC", f"LIMIT {limit}"])
        return " ".join(sql_parts), params

    def _log_search_results(self, operation: str, result: Any, table: str = "") -> None:
        """
        Log search operation results with debug information.

        Args:
            operation: Operation name for logging
            result: Operation result
            table: Optional table name
        """
        result_count = len(result) if isinstance(result, list) else 0
        self._log.info(
            f"{LOG_PREFIX_DEBUG} {operation} returning {result_count} records"
            + (f" from {table}" if table else "")
        )
        if isinstance(result, list) and result:
            self._log.info(f"{LOG_PREFIX_DEBUG} First record sample: {result[0]}")

    @kernel_function(
        name="db_info",
        description="Get comprehensive database information including path, existence, size, and table count",
    )
    async def db_info(
        self, arguments: Optional[KernelArguments] = None
    ) -> Dict[str, Any]:
        """Get database information and health status."""
        try:
            result = await self._call_tool("db_info", random_string="info")
            self._log.info(f"{LOG_PREFIX_INFO} Database info retrieved successfully")
            return result
        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Database info failed: {e}")
            return {"error": str(e), "exists": False}

    @kernel_function(
        name="list_tables",
        description="List all tables in the Dutch parliamentary database for data discovery",
    )
    async def list_tables(
        self,
        reload: Annotated[bool, "Force refresh from server instead of cache"] = False,
        arguments: Optional[KernelArguments] = None,
    ) -> List[str]:
        """List all available database tables."""
        if self._tables_cache and not reload:
            return self._tables_cache

        try:
            result = await self._call_tool("list_tables", random_string="tables")
            self._log.info(f"{LOG_PREFIX_INFO} Retrieved table list")

            # Extract table names from result
            tables = []
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and "name" in item:
                        tables.append(item["name"])
                    elif isinstance(item, str):
                        tables.append(item)

            self._tables_cache = tables
            return tables

        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} List tables failed: {e}")
            return []

    @kernel_function(
        name="get_table_schema",
        description="Get detailed schema for parliamentary tables (Persoon, Fractie, Document, etc.)",
    )
    async def get_table_schema(
        self,
        table_name: Annotated[str, "Table name to inspect"],
        reload: Annotated[bool, "Force refresh from server"] = False,
        arguments: Optional[KernelArguments] = None,
    ) -> List[Dict[str, Any]]:
        """Get table schema information."""
        if table_name in self._schema_cache and not reload:
            return self._schema_cache[table_name]

        try:
            result = await self._call_tool("get_table_schema", tableName=table_name)
            self._log.info(f"{LOG_PREFIX_INFO} Schema retrieved for {table_name}")

            schema = result if isinstance(result, list) else []
            self._schema_cache[table_name] = schema
            return schema

        except Exception as e:
            self._log.error(
                f"{LOG_PREFIX_INFO} Schema retrieval failed for {table_name}: {e}"
            )
            return []

    @kernel_function(
        name="query",
        description="Execute raw SQL queries with parameter binding for complex parliamentary data analysis",
    )
    async def query(
        self,
        sql: Annotated[str, "SQL query to execute"],
        values: Annotated[str, "Parameter values as JSON array string"] = "",
        arguments: Optional[KernelArguments] = None,
    ) -> List[Dict[str, Any]]:
        """Execute parameterized SQL query."""
        try:
            kwargs = {"sql": sql}

            # Parse values if provided
            parameter_values = None
            if values and values.strip():
                try:
                    parameter_values = (
                        json.loads(values) if isinstance(values, str) else values
                    )
                except (json.JSONDecodeError, ValueError):
                    parameter_values = [values] if values else None

            converted_values = self._convert_parameter_values(parameter_values)

            if converted_values:
                kwargs["values"] = converted_values

            self._log.info(
                f"{LOG_PREFIX_INFO} Executing SQL: {sql[:100]}..."
                + (
                    f" with {len(converted_values)} parameters"
                    if converted_values
                    else ""
                )
            )

            result = await self._call_tool("query", **kwargs)
            result_list = (
                result if isinstance(result, list) else [result] if result else []
            )

            self._log.info(
                f"{LOG_PREFIX_INFO} Query returned {len(result_list)} records"
            )
            return result_list

        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Query failed: {e}")
            return []

    @kernel_function(
        name="read_records",
        description="Safe record retrieval from parliamentary tables with filtering and pagination",
    )
    async def read_records(
        self,
        table: Annotated[str, "Table name to query"],
        conditions: Annotated[str, "Filter conditions as JSON string"] = "",
        limit: Annotated[int, "Maximum records to return"] = 0,
        offset: Annotated[int, "Records to skip"] = 0,
        arguments: Optional[KernelArguments] = None,
    ) -> List[Dict[str, Any]]:
        """Read records with optional filtering and pagination."""
        try:
            kwargs = {"table": table}

            # Parse conditions if provided
            if conditions and conditions.strip():
                parsed_conditions = self._parse_conditions_parameter(conditions)
                if parsed_conditions:
                    kwargs["conditions"] = parsed_conditions

            if limit > 0:
                kwargs["limit"] = limit
            if offset > 0:
                kwargs["offset"] = offset

            self._log.info(
                f"{LOG_PREFIX_INFO} Reading from {table}"
                + (f" with conditions" if conditions else "")
                + (f", limit={limit}" if limit > 0 else "")
            )

            result = await self._call_tool("read_records", **kwargs)
            result_list = result if isinstance(result, list) else []

            self._log.info(
                f"{LOG_PREFIX_INFO} Read {len(result_list)} records from {table}"
            )
            return result_list

        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Read records failed for {table}: {e}")
            return []

    @kernel_function(
        name="create_record",
        description="Insert new records (use with caution on official parliamentary data)",
    )
    async def create_record(
        self,
        table: Annotated[str, "Target table name"],
        data: Annotated[str, "Record data as JSON string"],
        arguments: Optional[KernelArguments] = None,
    ) -> Dict[str, Any]:
        """Create new record in specified table."""
        try:
            # Parse JSON data
            try:
                record_data = json.loads(data) if isinstance(data, str) else data
            except (json.JSONDecodeError, ValueError):
                self._log.error(
                    f"{LOG_PREFIX_INFO} Invalid JSON data for create_record: {data}"
                )
                return {"success": False, "error": "Invalid JSON data format"}

            result = await self._call_tool(
                "create_record", table=table, data=record_data
            )
            self._log.info(f"{LOG_PREFIX_INFO} Record created in {table}")
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Create record failed for {table}: {e}")
            return {"success": False, "error": str(e)}

    @kernel_function(
        name="update_records",
        description="Update existing records (use with extreme caution on parliamentary data)",
    )
    async def update_records(
        self,
        table: Annotated[str, "Target table name"],
        data: Annotated[str, "New values as JSON string"],
        conditions: Annotated[str, "Update conditions as JSON string"],
        arguments: Optional[KernelArguments] = None,
    ) -> Dict[str, Any]:
        """Update records matching conditions."""
        try:
            # Parse JSON data and conditions
            try:
                update_data = json.loads(data) if isinstance(data, str) else data
                update_conditions = (
                    json.loads(conditions)
                    if isinstance(conditions, str)
                    else conditions
                )
            except (json.JSONDecodeError, ValueError):
                self._log.error(
                    f"{LOG_PREFIX_INFO} Invalid JSON for update_records: data={data}, conditions={conditions}"
                )
                return {"success": False, "error": "Invalid JSON format"}

            result = await self._call_tool(
                "update_records",
                table=table,
                data=update_data,
                conditions=update_conditions,
            )
            self._log.info(f"{LOG_PREFIX_INFO} Records updated in {table}")
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Update records failed for {table}: {e}")
            return {"success": False, "error": str(e)}

    @kernel_function(
        name="delete_records",
        description="Delete records (use with extreme caution - permanent data removal)",
    )
    async def delete_records(
        self,
        table: Annotated[str, "Target table name"],
        conditions: Annotated[str, "Deletion conditions as JSON string"],
        arguments: Optional[KernelArguments] = None,
    ) -> Dict[str, Any]:
        """Delete records matching conditions."""
        try:
            # Parse JSON conditions
            try:
                delete_conditions = (
                    json.loads(conditions)
                    if isinstance(conditions, str)
                    else conditions
                )
            except (json.JSONDecodeError, ValueError):
                self._log.error(
                    f"{LOG_PREFIX_INFO} Invalid JSON conditions for delete_records: {conditions}"
                )
                return {"success": False, "error": "Invalid JSON conditions format"}

            result = await self._call_tool(
                "delete_records", table=table, conditions=delete_conditions
            )
            self._log.info(f"{LOG_PREFIX_INFO} Records deleted from {table}")
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Delete records failed for {table}: {e}")
            return {"success": False, "error": str(e)}

    @kernel_function(
        name="search_politicians",
        description="Advanced politician search in Persoon table with name and function filtering",
    )
    async def search_politicians(
        self,
        search_term: Annotated[str, "Name search term"] = "",
        function: Annotated[str, "Function filter (e.g., 'Tweede Kamerlid')"] = "",
        limit: Annotated[int, "Maximum results"] = DEFAULT_SEARCH_LIMIT,
        arguments: Optional[KernelArguments] = None,
    ) -> List[Dict[str, Any]]:
        """Search for politicians with flexible criteria."""
        # Sanitize and validate inputs
        search_term = search_term.strip() if search_term else None
        function = function.strip() if function else None
        limit = int(limit) if limit else DEFAULT_SEARCH_LIMIT

        try:
            if search_term:
                # Build parameterized name search query
                sql = POLITICIAN_SEARCH_SQL
                params = [f"%{search_term}%"] * 3

                if function:
                    sql += " AND functie = ?"
                    params.append(function)

                sql += f" LIMIT {limit}"
                # Convert params list to JSON string for query function
                result = await self.query(sql, json.dumps(params))
            else:
                # Simple function-based filtering
                conditions_dict = {"functie": function} if function else {}
                conditions_json = json.dumps(conditions_dict) if conditions_dict else ""
                result = await self.read_records("Persoon", conditions_json, limit)

            self._log_search_results("search_politicians", result, "Persoon")
            return result

        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Politician search failed: {e}")
            return []

    @kernel_function(
        name="get_political_parties",
        description="Retrieve political party information with activity status filtering",
    )
    async def get_political_parties(
        self,
        active_only: Annotated[bool, "Only active parties"] = True,
        arguments: Optional[KernelArguments] = None,
    ) -> List[Dict[str, Any]]:
        """Get political party information."""
        try:
            if active_only:
                conditions = {"datumInactief": ""}  # Empty means still active
                result = await self.read_records("Fractie", conditions)
            else:
                result = await self.read_records("Fractie")

            self._log.info(
                f"{LOG_PREFIX_INFO} Retrieved {len(result)} political parties"
                + (" (active only)" if active_only else " (all)")
            )
            return result

        except Exception as e:
            self._log.error(
                f"{LOG_PREFIX_INFO} Political parties retrieval failed: {e}"
            )
            return []

    @kernel_function(
        name="search_documents",
        description="Advanced parliamentary document search with full-text and temporal filtering",
    )
    async def search_documents(
        self,
        search_term: Annotated[str, "Title/subject search term"] = "",
        document_type: Annotated[str, "Document type filter"] = "",
        date_from: Annotated[str, "Start date (YYYY-MM-DD)"] = "",
        date_to: Annotated[str, "End date (YYYY-MM-DD)"] = "",
        limit: Annotated[int, "Maximum results"] = DEFAULT_DOCUMENT_SEARCH_LIMIT,
        arguments: Optional[KernelArguments] = None,
    ) -> List[Dict[str, Any]]:
        """Search parliamentary documents with multiple criteria."""
        try:
            # Convert empty strings to None for proper query building
            search_term = search_term.strip() if search_term else None
            document_type = document_type.strip() if document_type else None
            date_from = date_from.strip() if date_from else None
            date_to = date_to.strip() if date_to else None

            sql, params = self._build_search_sql(
                search_term, document_type, date_from, date_to, int(limit)
            )

            # Convert params list to JSON string for query function
            result = await self.query(sql, json.dumps(params) if params else "")
            self._log_search_results("search_documents", result, "Document")
            return result

        except Exception as e:
            self._log.error(f"{LOG_PREFIX_INFO} Document search failed: {e}")
            return []
