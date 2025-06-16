#!/bin/sh

echo "Starting INTELLIGENT SKIPTOKEN-BASED sync..."

# Starting skiptoken - May 2025 data 
INITIAL_SKIPTOKEN=20000000
# Higher skiptoken for large datasets like Document to skip older data
DOCUMENT_SKIPTOKEN=22500000
# Lower skiptoken for critical entities (Persoon, Fractie) to get more complete data
CRITICAL_ENTITIES_SKIPTOKEN=15000000

# Document sync configuration - minimal setup for last 7 days only
DOC_SYNC_DAYS=7
DOC_MAX_SIZE_MB=50

# Exponential backoff intervals when 0 entries found
INTERVALS="500000 1000000 2000000 4000000 8000000 16000000"

# All categories in logical dependency order to avoid relation failures
# 1. Base reference data first (Persoon and Fractie are critical for agents)
BASE_ENTITIES="Persoon Fractie Commissie Zaal"
# 2. Seat/position assignments  
SEAT_ENTITIES="FractieZetel CommissieZetel"
# 3. Person-to-position mappings
PERSON_MAPPING_ENTITIES="FractieZetelPersoon CommissieZetelVastPersoon CommissieZetelVervangerPersoon FractieZetelVacature"
# 4. Core parliamentary items
CORE_ENTITIES="Document Kamerstukdossier Zaak Activiteit Agendapunt Besluit Vergadering Verslag"
# 5. Actor relationships (who is involved in what)
ACTOR_ENTITIES="DocumentActor ZaakActor ActiviteitActor"
# 6. Additional person data
PERSON_DATA_ENTITIES="PersoonGeschenk PersoonNevenfunctie PersoonNevenfunctieInkomsten PersoonReis"
# 7. Parliamentary processes
PROCESS_ENTITIES="Stemming Toezegging Reservering"
# 8. Metadata
META_ENTITIES="DocumentVersie CommissieContactinformatie"

# Critical entities that need fresh data for AI agents
CRITICAL_ENTITIES="Persoon Fractie"

ALL_CATEGORIES="$BASE_ENTITIES $SEAT_ENTITIES $PERSON_MAPPING_ENTITIES $CORE_ENTITIES $ACTOR_ENTITIES $PERSON_DATA_ENTITIES $PROCESS_ENTITIES $META_ENTITIES"

# Database corruption protection
DB_BACKUP_CHECK=true

# Function to check and repair database corruption
check_database_integrity() {
  db_file=$1
  echo "Checking integrity of $db_file..."
  
  if [ ! -f "$db_file" ]; then
    echo "Database $db_file does not exist, will be created fresh"
    return 0
  fi
  
  # Check integrity
  integrity_result=$(sqlite3 "$db_file" "PRAGMA integrity_check;" 2>/dev/null | head -1)
  
  if [ "$integrity_result" = "ok" ]; then
    echo "Database $db_file integrity: OK"
    return 0
  else
    echo "WARNING: Database $db_file is corrupted: $integrity_result"
    echo "Moving corrupted database to backup and starting fresh..."
    mv "$db_file" "${db_file}.corrupted.$(date +%s)"
    rm -f "${db_file}-wal" "${db_file}-shm" 2>/dev/null || true
    return 1
  fi
}

# Function to safely close database connections
close_database_connections() {
  db_file=$1
  echo "Ensuring clean database closure for $db_file..."
  
  if [ -f "$db_file" ]; then
    # Force WAL checkpoint and close
    sqlite3 "$db_file" "PRAGMA wal_checkpoint(FULL); PRAGMA optimize;" 2>/dev/null || true
    
    # Wait for file handles to close
    sleep 2
    
    # Remove WAL and SHM files if they exist
    rm -f "${db_file}-wal" "${db_file}-shm" 2>/dev/null || true
  fi
}

# Function to get appropriate skiptoken for category
get_skiptoken() {
  category=$1
  if [ "$category" = "Document" ]; then
    echo $DOCUMENT_SKIPTOKEN
  elif [ "$category" = "Persoon" ] || [ "$category" = "Fractie" ]; then
    echo $CRITICAL_ENTITIES_SKIPTOKEN
  else
    echo $INITIAL_SKIPTOKEN
  fi
}

# Function to check if category is critical (needs refresh on restart)
is_critical_entity() {
  category=$1
  for critical in $CRITICAL_ENTITIES; do
    if [ "$category" = "$critical" ]; then
      return 0
    fi
  done
  return 1
}

# Function to run command with retries
retry_command() {
  max_attempts=3
  attempt=1
  while [ $attempt -le $max_attempts ]; do
    if $@; then
      return 0
    fi
    echo "Command failed, attempt $attempt of $max_attempts. Retrying in 5 seconds..."
    attempt=$((attempt + 1))
    sleep 5
  done
  return 1
}

# Function to perform smart document sync (like tksync.sh but limited)
smart_document_sync() {
  echo "*** SMART_DOCUMENT_SYNC FUNCTION CALLED ***"
  echo "=== Smart Document Sync (last $DOC_SYNC_DAYS days, max ${DOC_MAX_SIZE_MB}MB per file) ==="
  
  # Check database integrity first
  if [ "$DB_BACKUP_CHECK" = "true" ]; then
    check_database_integrity "tk.sqlite3"
    check_database_integrity "xml.sqlite3"
  fi
  
  # Check if we should sync documents  
  doc_count=$(sqlite3 tk.sqlite3 "SELECT COUNT(*) FROM Document WHERE datum >= date('now', '-$DOC_SYNC_DAYS days') AND enclosure != '' AND contentLength > 0 AND contentLength < $((DOC_MAX_SIZE_MB * 1024 * 1024))")
  total_mb=$(sqlite3 tk.sqlite3 "SELECT CAST(ROUND(SUM(contentLength)/1024.0/1024.0) AS INTEGER) FROM Document WHERE datum >= date('now', '-$DOC_SYNC_DAYS days') AND enclosure != '' AND contentLength > 0 AND contentLength < $((DOC_MAX_SIZE_MB * 1024 * 1024))")
  
  echo "Found $doc_count documents totaling ~${total_mb}MB to potentially sync"
  
  if [ "$doc_count" -gt 0 ]; then
    if [ "$total_mb" -lt 8000 ]; then
      echo "Total size acceptable - starting custom limited document pull..."
      
            # Use tkpull but with custom filtering for recent documents only
      echo "Starting filtered document download (last $DOC_SYNC_DAYS days, max ${DOC_MAX_SIZE_MB}MB per file)..."
      mkdir -p /app/docs
      
      # Create backup and filter documents in-place
      echo "Creating filtered document list for tkpull..."
      
      # Close any open database connections
      close_database_connections "tk.sqlite3"
      
      # Create backup
      cp tk.sqlite3 tk.sqlite3.backup
      
      # Filter documents in the actual database
      echo "Filtering to last $DOC_SYNC_DAYS days, max ${DOC_MAX_SIZE_MB}MB per file..."
      sqlite3 tk.sqlite3 "
        DROP TABLE IF EXISTS Document_backup;
        CREATE TABLE Document_backup AS SELECT * FROM Document;
        DELETE FROM Document 
        WHERE datum < date('now', '-$DOC_SYNC_DAYS days') 
        OR enclosure = '' 
        OR contentLength <= 0 
        OR contentLength >= $((DOC_MAX_SIZE_MB * 1024 * 1024));
      "
      
      filtered_count=$(sqlite3 tk.sqlite3 "SELECT COUNT(*) FROM Document;")
      echo "Filtered to $filtered_count documents for download..."
      
      # Run tkpull on filtered database
      echo "Running tkpull on filtered dataset..."
      tkpull
      
      # Restore original Document table
      echo "Restoring original document metadata..."
      sqlite3 tk.sqlite3 "
        DROP TABLE Document;
        ALTER TABLE Document_backup RENAME TO Document;
      "
      
      echo "Creating search index for recent documents..."
      
      # Clean close any existing index database
      close_database_connections "tkindex-minimal.sqlite3"
      
      # Create new index with corruption protection
      if retry_command tkindex --days=$DOC_SYNC_DAYS --tkindex tkindex-minimal.sqlite3; then
        # Verify index integrity
        if [ "$DB_BACKUP_CHECK" = "true" ]; then
          check_database_integrity "tkindex-minimal.sqlite3"
        fi
        echo "Document sync completed successfully"
      else
        echo "ERROR: Failed to create search index"
      fi
    else
      echo "Total size too large (${total_mb}MB > 8000MB) - limiting to priority documents only..."
      
      # Since we're already at 7 days, just limit to smaller important documents
      priority_count=$(sqlite3 tk.sqlite3 "
        SELECT COUNT(*) FROM Document 
        WHERE datum >= date('now', '-$DOC_SYNC_DAYS days') 
        AND enclosure != '' 
        AND contentLength > 0 
        AND contentLength < 5242880
        AND (
          soort LIKE '%brief%' OR 
          soort LIKE '%motie%' OR 
          soort LIKE '%amendement%' OR
          soort LIKE '%wetsvoorstel%'
        )")
      
      priority_size=$(sqlite3 tk.sqlite3 "
        SELECT CAST(ROUND(SUM(contentLength)/1024.0/1024.0) AS INTEGER) FROM Document 
        WHERE datum >= date('now', '-$DOC_SYNC_DAYS days') 
        AND enclosure != '' 
        AND contentLength > 0 
        AND contentLength < 5242880
        AND (
          soort LIKE '%brief%' OR 
          soort LIKE '%motie%' OR 
          soort LIKE '%amendement%' OR
          soort LIKE '%wetsvoorstel%'
        )")
      
      echo "Priority documents (last $DOC_SYNC_DAYS days, important types, <5MB): $priority_count docs, ~${priority_size}MB"
      
      if [ "$priority_count" -gt 0 ] && [ "$priority_size" -lt 3000 ]; then
        echo "Starting selective document pull (priority documents only)..."
        
        # Use tkpull with priority document filtering
        echo "Starting priority document download (last $DOC_SYNC_DAYS days, important types <5MB)..."
        mkdir -p /app/docs
        
        # Create backup and filter priority documents in-place
        echo "Creating priority document filter for tkpull..."
        
        # Close any open database connections
        close_database_connections "tk.sqlite3"
        
        # Create backup
        cp tk.sqlite3 tk.sqlite3.backup
        
        # Filter to priority documents in the actual database
        echo "Filtering to priority documents (last $DOC_SYNC_DAYS days, important types <5MB)..."
        sqlite3 tk.sqlite3 "
          DROP TABLE IF EXISTS Document_backup;
          CREATE TABLE Document_backup AS SELECT * FROM Document;
          DELETE FROM Document 
          WHERE datum < date('now', '-$DOC_SYNC_DAYS days') 
          OR enclosure = '' 
          OR contentLength <= 0 
          OR contentLength >= 5242880
          OR (
            soort NOT LIKE '%brief%' AND 
            soort NOT LIKE '%motie%' AND 
            soort NOT LIKE '%amendement%' AND
            soort NOT LIKE '%wetsvoorstel%'
          );
        "
        
        priority_filtered_count=$(sqlite3 tk.sqlite3 "SELECT COUNT(*) FROM Document;")
        echo "Filtered to $priority_filtered_count priority documents for download..."
        
        # Run tkpull on priority documents
        echo "Running tkpull on priority documents..."
        tkpull
        
        # Restore original Document table
        echo "Restoring original document metadata..."
        sqlite3 tk.sqlite3 "
          DROP TABLE Document;
          ALTER TABLE Document_backup RENAME TO Document;
        "
        
        echo "Creating search index for priority documents..."
        
        # Clean close any existing index database
        close_database_connections "tkindex-minimal.sqlite3"
        
        # Create new index with corruption protection
        if retry_command tkindex --days=$DOC_SYNC_DAYS --tkindex tkindex-minimal.sqlite3; then
          # Verify index integrity
          if [ "$DB_BACKUP_CHECK" = "true" ]; then
            check_database_integrity "tkindex-minimal.sqlite3"
          fi
          echo "Selective document sync completed successfully"
        else
          echo "ERROR: Failed to create search index for priority documents"
        fi
      else
        echo "Even priority documents too large (${priority_size}MB) - metadata-only mode"
      fi
    fi
  else
    echo "No documents found to sync"
  fi
}

# Smart fetch function - finds optimal skiptoken for each category
smart_fetch_category() {
  category=$1
  start_skiptoken=$2
  force_refresh=${3:-false}
  
  if [ "$force_refresh" = "true" ]; then
    echo "=== FORCE REFRESH: $category starting from skiptoken $start_skiptoken ==="
  else
    echo "=== Smart fetching $category starting from skiptoken $start_skiptoken ==="
  fi
  
  current_skiptoken=$start_skiptoken
  
  for interval in $INTERVALS; do
    echo "Trying $category at skiptoken $current_skiptoken..."
    
    # Clear existing data for this category if force refresh or critical entity
    if [ "$force_refresh" = "true" ] || is_critical_entity "$category"; then
      echo "Clearing existing $category data for fresh sync..."
      sqlite3 xml.sqlite3 "DELETE FROM $category;" 2>/dev/null || true
    fi
    
    # Set the skiptoken manually in the database  
    sqlite3 xml.sqlite3 "CREATE TABLE IF NOT EXISTS $category (skiptoken INT);" 2>/dev/null || true
    sqlite3 xml.sqlite3 "INSERT INTO $category (skiptoken) VALUES ($current_skiptoken);"
    
    # Try to fetch data with retry on timeout
    max_retries=3
    retry_count=0
    success=false
    
    while [ $retry_count -lt $max_retries ] && [ "$success" = "false" ]; do
      if [ $retry_count -gt 0 ]; then
        echo "Retry $retry_count for $category (timeout occurred)..."
        sleep 10  # Wait 10 seconds before retry
      fi
      
      # Add small delay between requests to respect rate limiting
      sleep 2
      
      result=$(tkgetxml $category 2>&1)
      echo "$result"
      
      # Check for timeout specifically
      if echo "$result" | grep -q "Connection timed out"; then
        echo "Connection timeout for $category, will retry..."
        retry_count=$((retry_count + 1))
      else
        success=true
      fi
    done
    
    if [ "$success" = "false" ]; then
      echo "Max retries reached for $category, trying lower skiptoken..."
      # Move back by current interval only after max retries
      current_skiptoken=$((current_skiptoken - interval))
      
      if [ $current_skiptoken -lt 0 ]; then
        echo "Reached negative skiptoken for $category, fetching from beginning..."
        sqlite3 xml.sqlite3 "DELETE FROM $category;" 2>/dev/null || true
        tkgetxml $category
        return 0
      fi
      continue
    fi
    
    # Check if we got any data (only lower skiptoken on 0 results, not timeouts)
    entries=$(echo "$result" | grep "Done - saw" | grep -o '[0-9]* new entries' | head -1 | grep -o '[0-9]*')
    
    if [ "$entries" -gt 0 ] 2>/dev/null; then
      echo "SUCCESS: Found $entries entries for $category at skiptoken $current_skiptoken"
      return 0
    else
      echo "No data found for $category at skiptoken $current_skiptoken (0 results - lowering skiptoken)"
      # Move back by current interval only when we get 0 results
      current_skiptoken=$((current_skiptoken - interval))
      
      if [ $current_skiptoken -lt 0 ]; then
        echo "Reached negative skiptoken for $category, fetching from beginning..."
        sqlite3 xml.sqlite3 "DELETE FROM $category;" 2>/dev/null || true
        tkgetxml $category
        return 0
      fi
    fi
  done
  
  echo "Tried all intervals for $category, fetching from beginning..."
  sqlite3 xml.sqlite3 "DELETE FROM $category;" 2>/dev/null || true
  tkgetxml $category
  return 0
}

# Check if this is first run
if [ ! -f "/app/tk.sqlite3" ]; then
  echo "=== FIRST RUN: Intelligent entity collection ==="
  
  echo "Copying templates and binaries..."
  cp -r /workdir/html /app/html
  cp -r /workdir/partials /app/partials  
  cp -r /workdir/build /app/build
  cp /workdir/tk.xslt /app/tk.xslt
  cp /workdir/tk-div.xslt /app/tk-div.xslt
  
  echo "=== Phase 1: Base Reference Data (Critical entities with lower skiptoken) ==="
  for category in $BASE_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    if is_critical_entity "$category"; then
      echo "*** CRITICAL ENTITY: $category using lower skiptoken $skiptoken ***"
    fi
    smart_fetch_category $category $skiptoken true
  done
  
  echo "=== Phase 2: Seat/Position Assignments ==="
  for category in $SEAT_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    smart_fetch_category $category $skiptoken
  done
  
  echo "=== Phase 3: Person-to-Position Mappings ==="
  for category in $PERSON_MAPPING_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    smart_fetch_category $category $skiptoken
  done
  
  echo "=== Phase 4: Core Parliamentary Items ==="
  for category in $CORE_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    smart_fetch_category $category $skiptoken
  done
  
  echo "=== Phase 5: Actor Relationships ==="
  for category in $ACTOR_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    smart_fetch_category $category $skiptoken
  done
  
  echo "=== Phase 6: Additional Person Data ==="
  for category in $PERSON_DATA_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    smart_fetch_category $category $skiptoken
  done
  
  echo "=== Phase 7: Parliamentary Processes ==="
  for category in $PROCESS_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    smart_fetch_category $category $skiptoken
  done
  
  echo "=== Phase 8: Metadata ==="
  for category in $META_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    smart_fetch_category $category $skiptoken
  done
  
  echo "=== Converting all data to database ==="
  retry_command tkconv $ALL_CATEGORIES
  
  echo "Creating basic indexes..."
  sqlite3 tk.sqlite3 < /workdir/maak-indexen || true
  
  echo "Creating search index (last $DOC_SYNC_DAYS days)..."
  close_database_connections "tkindex-small.sqlite3"
  if retry_command tkindex --days=$DOC_SYNC_DAYS --tkindex tkindex-small.sqlite3; then
    if [ "$DB_BACKUP_CHECK" = "true" ]; then
      check_database_integrity "tkindex-small.sqlite3"
    fi
  else
    echo "ERROR: Failed to create initial search index"
  fi
  
  # NEW: Smart document sync for minimal setup
  smart_document_sync
  
  echo "=== INTELLIGENT FIRST RUN COMPLETE ==="
  echo "All entities collected with optimal skiptoken ranges!"
  touch "/app/.first_run_done"
  
else
  echo "=== RESTART DETECTED: Refreshing critical entities for AI agents ==="
  
  # Force refresh critical entities (Persoon, Fractie) on every restart
  echo "*** Forcing fresh sync of critical entities: $CRITICAL_ENTITIES ***"
  for category in $CRITICAL_ENTITIES; do
    skiptoken=$(get_skiptoken $category)
    echo "*** Refreshing $category with lower skiptoken $skiptoken for complete agent data ***"
    smart_fetch_category $category $skiptoken true
  done
  
  echo "=== MAINTENANCE: Incremental update for other entities ==="
  
  # Normal incremental updates for non-critical categories
  non_critical_categories=""
  for category in $ALL_CATEGORIES; do
    if ! is_critical_entity "$category"; then
      non_critical_categories="$non_critical_categories $category"
    fi
  done
  
  retry_command tkgetxml $non_critical_categories
  retry_command tkconv $ALL_CATEGORIES
  
  close_database_connections "tkindex-small.sqlite3"
  if retry_command tkindex --days=$DOC_SYNC_DAYS --tkindex tkindex-small.sqlite3; then
    if [ "$DB_BACKUP_CHECK" = "true" ]; then
      check_database_integrity "tkindex-small.sqlite3"
    fi
  else
    echo "ERROR: Failed to create restart search index"
  fi
  
  # NEW: Always run document sync on restart to ensure filtered downloads
  echo "*** FORCING DOCUMENT SYNC ON RESTART ***"
  smart_document_sync
  
  echo "=== Restart maintenance complete ==="
fi

# Normal sleep schedule
if [ -f "/app/.first_run_done" ]; then
  echo "Intelligent sync complete. Sleeping 15 minutes between updates..."
  sleep 900  # 15 minutes
fi

# Maintenance loop  
while true
do
  echo "=== INCREMENTAL UPDATE ==="
  
  # Periodically refresh critical entities (every 3rd cycle)
  if [ $(($(date +%s) / 3600 % 3)) -eq 0 ]; then
    echo "*** Periodic refresh of critical entities ***"
    for category in $CRITICAL_ENTITIES; do
      skiptoken=$(get_skiptoken $category)
      smart_fetch_category $category $skiptoken true
    done
  fi
  
  retry_command tkgetxml $ALL_CATEGORIES
  retry_command tkconv $ALL_CATEGORIES
  
  close_database_connections "tkindex-small.sqlite3"
  if retry_command tkindex --days=$DOC_SYNC_DAYS --tkindex tkindex-small.sqlite3; then
    if [ "$DB_BACKUP_CHECK" = "true" ]; then
      check_database_integrity "tkindex-small.sqlite3"
    fi
  else
    echo "ERROR: Failed to create maintenance search index"
  fi
  
  # NEW: Run document sync in maintenance loop (less frequent)
  if [ $(($(date +%s) / 3600 % 6)) -eq 0 ]; then
    echo "*** Periodic document sync (every 6th hour) ***"
    smart_document_sync
  fi
  
  echo "=== Update complete. Sleeping 1 hour... ==="
  sleep 3600  # 1 hour
done 