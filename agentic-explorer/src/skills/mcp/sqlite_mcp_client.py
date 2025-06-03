import json
import logging
import os
from typing import Annotated, Any, Dict, List

from semantic_kernel.connectors.mcp import MCPStdioPlugin
from semantic_kernel.contents.text_content import TextContent
from semantic_kernel.functions import KernelArguments, kernel_function


class SQLiteMCPClient:
    """Native Semantic-Kernel plugin that wraps a SQLite Municipal Content Platform (MCP) server.

    Exposes database operations for interacting with SQLite databases:
        • db_info        → database information (path, size, table count)
        • list_tables    → list of available tables
        • get_schema     → schema information for a specific table
        • query          → execute raw SQL queries with optional parameters
        • read_records   → read records from a table with conditions
        • create_record  → insert a new record into a table
        • update_records → update records in a table
        • delete_records → delete records from a table

    This client is designed specifically for the Dutch parliamentary database (tkconv)
    containing information about politicians, parties, documents, meetings, and votes.
    """

    def __init__(self, db_path: str = None) -> None:
        # Use environment variable first, then try container path, then relative path
        container_db_path = "/app/db-export/tk.sqlite3"  # Docker container path
        local_db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
            "..", "..", "sqlite-data", "tk.sqlite3"
        )
        
        if db_path:
            self.db_path = db_path
        elif os.getenv("TKCONV_DB_PATH"):
            self.db_path = os.getenv("TKCONV_DB_PATH")
        elif os.path.exists(container_db_path):
            self.db_path = container_db_path
        else:
            self.db_path = local_db_path
            
        self._log = logging.getLogger("mcp.sqlite_client")
        self._tables_cache: List[str] = []
        self._schema_cache: Dict[str, List[Dict]] = {}
        
        # Debug logging for database path resolution
        self._log.info("SQLiteMCPClient initialized with db_path: %s", self.db_path)
        self._log.info("TKCONV_DB_PATH environment variable: %s", os.getenv("TKCONV_DB_PATH"))
        self._log.info("Container path exists: %s", os.path.exists(container_db_path))
        self._log.info("Local path exists: %s", os.path.exists(local_db_path))
        self._log.info("Selected database file exists: %s", os.path.exists(self.db_path) if self.db_path else False)
        if self.db_path and os.path.exists(self.db_path):
            self._log.info("Database file size: %d bytes", os.path.getsize(self.db_path))
        
        # List directory contents for debugging
        if self.db_path:
            db_dir = os.path.dirname(self.db_path)
            if os.path.exists(db_dir):
                self._log.info("Directory contents of %s: %s", db_dir, os.listdir(db_dir))
            else:
                self._log.warning("Database directory does not exist: %s", db_dir)

    async def _call_tool(self, name: str, **kwargs):
        """Launch SQLite MCP server via npx and invoke the specified tool."""
        self._log.info(
            "Starting SQLite MCPStdioPlugin with db_path=%s, tool=%s, args=%s",
            self.db_path,
            name,
            kwargs,
        )

        # Check if database file exists before proceeding
        if not self.db_path or not os.path.exists(self.db_path):
            error_msg = f"Database file not found: {self.db_path}"
            self._log.error(error_msg)
            raise FileNotFoundError(error_msg)

        cmd = f'npx -y mcp-sqlite "{self.db_path}"'
        self._log.info("Command to run SQLite MCP plugin: %s", cmd)

        try:
            async with MCPStdioPlugin(
                name="SQLiteMCP",
                command="sh",
                args=["-c", cmd],
                load_tools=True,
                load_prompts=False,
            ) as mcp_plugin:
                self._log.info("SQLite MCPStdioPlugin started successfully")
                tool = getattr(mcp_plugin, name, None)
                if not tool:
                    raise RuntimeError(f"Tool {name} not found in SQLite MCP plugin")
                self._log.info("Calling SQLite MCP tool %s with args: %s", name, kwargs)
                result = await tool(**kwargs)
                self._log.info("SQLite MCP tool %s completed successfully", name)
                return result
        except Exception as e:
            self._log.error("Error calling SQLite MCP tool %s: %s", name, e, exc_info=True)
            raise

    @kernel_function(
        name="db_info",
        description="Get information about the SQLite database including path, existence, size, and table count",
    )
    async def db_info(
        self,
        arguments: KernelArguments | None = None,
    ) -> Dict[str, Any]:
        """Get database information."""
        try:
            result = await self._call_tool("db_info", random_string="info")
            self._log.info("Database info result: %r", result)
            return result
        except Exception as e:
            self._log.error("db_info failed: %s", e)
            return {"error": str(e), "exists": False}

    @kernel_function(
        name="list_tables",
        description="List all tables in the SQLite database. Useful for discovering what data is available in the Dutch parliamentary database.",
    )
    async def list_tables(
        self,
        reload: Annotated[bool, "Set to true to bypass the client-side cache"] = False,
        arguments: KernelArguments | None = None,
    ) -> List[str]:
        """List all tables in the database."""
        if self._tables_cache and not reload:
            return self._tables_cache

        try:
            result = await self._call_tool("list_tables", random_string="tables")
            self._log.info("List tables result: %r", result)
            
            # Extract table names from the result
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
            self._log.error("list_tables failed: %s", e)
            return []

    @kernel_function(
        name="get_table_schema",
        description="Get the schema information for a specific table including column details. Essential for understanding the structure of parliamentary data tables like Persoon (politicians), Fractie (parties), Document (parliamentary documents), etc.",
    )
    async def get_table_schema(
        self,
        table_name: Annotated[str, "Name of the table to get schema for"],
        reload: Annotated[bool, "Force fetch from server instead of cache"] = False,
        arguments: KernelArguments | None = None,
    ) -> List[Dict[str, Any]]:
        """Get schema information for a specific table."""
        if table_name in self._schema_cache and not reload:
            return self._schema_cache[table_name]

        try:
            result = await self._call_tool("get_table_schema", tableName=table_name)
            self._log.info("Get table schema result for %s: %r", table_name, result)
            
            schema = result if isinstance(result, list) else []
            self._schema_cache[table_name] = schema
            return schema
        except Exception as e:
            self._log.error("get_table_schema failed for %s: %s", table_name, e)
            return []

    @kernel_function(
        name="query",
        description="Execute a raw SQL query against the database. Use this for complex queries involving JOINs, aggregations, or specific filtering. Be careful with the SQL syntax - this is a direct database query.",
    )
    async def query(
        self,
        sql: Annotated[str, "The SQL query to execute"],
        values: Annotated[List[Any] | None, "Optional parameter values for parameterized queries"] = None,
        arguments: KernelArguments | None = None,
    ) -> List[Dict[str, Any]]:
        """Execute a raw SQL query."""
        try:
            kwargs = {"sql": sql}
            
            # Handle values parameter - ensure it's a list or None
            if values is not None:
                # Handle different input formats that might come from function calling
                if isinstance(values, str):
                    # If values is a string, try to parse it as JSON
                    try:
                        import json
                        values = json.loads(values)
                    except (json.JSONDecodeError, ValueError):
                        # If parsing fails, treat as single string value
                        values = [values]
                elif not isinstance(values, list):
                    # Convert other types to list
                    values = [values]
                
                # Convert all values to strings for SQLite parameter binding
                # SQLite expects string parameters even for numeric values
                if values:
                    values = [str(v) if v is not None else None for v in values]
                    kwargs["values"] = values
            
            self._log.info("Executing SQL query: %s with values: %r", sql[:100], kwargs.get("values"))
            
            result = await self._call_tool("query", **kwargs)
            self._log.info("Query result for SQL %s: %d records returned", sql[:50], 
                          len(result) if isinstance(result, list) else 1)
            return result if isinstance(result, list) else [result] if result else []
        except Exception as e:
            self._log.error("query failed for SQL %s: %s", sql[:100], e)
            return []

    @kernel_function(
        name="read_records",
        description="Read records from a table with optional filtering conditions. This is safer than raw SQL for simple data retrieval. Useful for getting politicians from Persoon table, parties from Fractie, documents from Document table, etc.",
    )
    async def read_records(
        self,
        table: Annotated[str, "Name of the table to read from"],
        conditions: Annotated[Dict[str, Any] | None, "Filter conditions as key-value pairs"] = None,
        limit: Annotated[int | None, "Maximum number of records to return"] = None,
        offset: Annotated[int | None, "Number of records to skip"] = None,
        arguments: KernelArguments | None = None,
    ) -> List[Dict[str, Any]]:
        """Read records from a table with optional conditions."""
        try:
            kwargs = {"table": table}
            
            # Handle conditions parameter 
            if conditions is not None and conditions:
                # Ensure conditions is a dictionary
                if isinstance(conditions, str):
                    try:
                        import json
                        conditions = json.loads(conditions)
                    except (json.JSONDecodeError, ValueError):
                        self._log.warning("Could not parse conditions as JSON: %s", conditions)
                        conditions = None
                
                if conditions and isinstance(conditions, dict):
                    kwargs["conditions"] = conditions
            
            # Handle limit and offset
            if limit is not None:
                kwargs["limit"] = int(limit)
            if offset is not None:
                kwargs["offset"] = int(offset)
            
            self._log.info("Reading records from table %s with conditions: %r, limit: %s", table, kwargs.get("conditions"), kwargs.get("limit"))
            
            result = await self._call_tool("read_records", **kwargs)
            self._log.info("Read records result from %s: %d records", table, len(result) if isinstance(result, list) else 0)
            return result if isinstance(result, list) else []
        except Exception as e:
            self._log.error("read_records failed for table %s: %s", table, e)
            return []

    @kernel_function(
        name="create_record",
        description="Insert a new record into a table. Use with caution - this modifies the database. Generally not recommended for the parliamentary database as it contains official government data.",
    )
    async def create_record(
        self,
        table: Annotated[str, "Name of the table to insert into"],
        data: Annotated[Dict[str, Any], "Record data as key-value pairs"],
        arguments: KernelArguments | None = None,
    ) -> Dict[str, Any]:
        """Create a new record in a table."""
        try:
            result = await self._call_tool("create_record", table=table, data=data)
            self._log.info("Create record result in %s: %r", table, result)
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            self._log.error("create_record failed for table %s: %s", table, e)
            return {"success": False, "error": str(e)}

    @kernel_function(
        name="update_records",
        description="Update records in a table based on conditions. Use with extreme caution - this modifies the database. Generally not recommended for the parliamentary database.",
    )
    async def update_records(
        self,
        table: Annotated[str, "Name of the table to update"],
        data: Annotated[Dict[str, Any], "New values as key-value pairs"],
        conditions: Annotated[Dict[str, Any], "Filter conditions to identify records to update"],
        arguments: KernelArguments | None = None,
    ) -> Dict[str, Any]:
        """Update records in a table."""
        try:
            result = await self._call_tool("update_records", table=table, data=data, conditions=conditions)
            self._log.info("Update records result in %s: %r", table, result)
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            self._log.error("update_records failed for table %s: %s", table, e)
            return {"success": False, "error": str(e)}

    @kernel_function(
        name="delete_records",
        description="Delete records from a table based on conditions. Use with extreme caution - this permanently removes data. Generally not recommended for the parliamentary database.",
    )
    async def delete_records(
        self,
        table: Annotated[str, "Name of the table to delete from"],
        conditions: Annotated[Dict[str, Any], "Filter conditions to identify records to delete"],
        arguments: KernelArguments | None = None,
    ) -> Dict[str, Any]:
        """Delete records from a table."""
        try:
            result = await self._call_tool("delete_records", table=table, conditions=conditions)
            self._log.info("Delete records result from %s: %r", table, result)
            return result if isinstance(result, dict) else {"success": True}
        except Exception as e:
            self._log.error("delete_records failed for table %s: %s", table, e)
            return {"success": False, "error": str(e)}

    # Convenience methods for common parliamentary data queries
    @kernel_function(
        name="search_politicians",
        description="Search for politicians (MPs) in the Persoon table by name, party affiliation, or other criteria. Returns detailed information about parliament members.",
    )
    async def search_politicians(
        self,
        search_term: Annotated[str | None, "Search term to look for in names (e.g., 'Ruud Verkuijlen', 'Rudolf')"] = None,
        function: Annotated[str | None, "Filter by function (e.g., 'Tweede Kamerlid', 'Oud Kamerlid')"] = None,
        limit: Annotated[int, "Maximum number of results"] = 10,
        arguments: KernelArguments | None = None,
    ) -> List[Dict[str, Any]]:
        """Search for politicians with flexible criteria."""
        # Convert parameters to proper types
        search_term = str(search_term) if search_term is not None and search_term else None
        function = str(function) if function is not None and function else None
        limit = int(limit) if limit is not None else 10
        
        if search_term:
            # Use SQL for name search
            sql = """
            SELECT * FROM Persoon 
            WHERE (achternaam LIKE ? OR voornamen LIKE ? OR roepnaam LIKE ?)
            """
            params = [f"%{search_term}%"] * 3
            
            if function:
                sql += " AND functie = ?"
                params.append(function)
            
            sql += f" LIMIT {limit}"
            result = await self.query(sql, params)
            
            # DEBUG: Log what search_politicians is returning to the agent
            self._log.info("🔍 DEBUG: search_politicians returning %d records to agent", len(result) if isinstance(result, list) else 0)
            if isinstance(result, list) and len(result) > 0:
                self._log.info("🔍 DEBUG: search_politicians first record: %r", result[0])
            
            return result
        else:
            # Use read_records for simple filtering
            conditions = {}
            if function:
                conditions["functie"] = function
            result = await self.read_records("Persoon", conditions, limit)
            
            # DEBUG: Log what search_politicians is returning to the agent  
            self._log.info("🔍 DEBUG: search_politicians (read_records) returning %d records to agent", len(result) if isinstance(result, list) else 0)
            
            return result

    @kernel_function(
        name="get_political_parties",
        description="Get information about political parties (fracties) including vote counts and seat numbers. Useful for understanding the current political landscape.",
    )
    async def get_political_parties(
        self,
        active_only: Annotated[bool, "Only return currently active parties"] = True,
        arguments: KernelArguments | None = None,
    ) -> List[Dict[str, Any]]:
        """Get political party information."""
        if active_only:
            conditions = {"datumInactief": ""}  # Empty string means still active
            return await self.read_records("Fractie", conditions)
        else:
            return await self.read_records("Fractie")

    @kernel_function(
        name="search_documents",
        description="Search parliamentary documents by title, subject, or date. Useful for finding specific legislation, motions, or parliamentary papers.",
    )
    async def search_documents(
        self,
        search_term: Annotated[str | None, "Search term for title or subject"] = None,
        document_type: Annotated[str | None, "Filter by document type"] = None,
        date_from: Annotated[str | None, "Start date (YYYY-MM-DD format)"] = None,
        date_to: Annotated[str | None, "End date (YYYY-MM-DD format)"] = None,
        limit: Annotated[int, "Maximum number of results"] = 20,
        arguments: KernelArguments | None = None,
    ) -> List[Dict[str, Any]]:
        """Search for parliamentary documents."""
        sql_parts = ["SELECT * FROM Document WHERE 1=1"]
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
        
        sql_parts.append("ORDER BY datum DESC")
        sql_parts.append(f"LIMIT {limit}")
        
        sql = " ".join(sql_parts)
        return await self.query(sql, params)
