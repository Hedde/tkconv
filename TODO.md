# tkconv Project - Code Cleanup & Optimization TODO

## 🎯 Context & Problem Solved

**Original Issue**: tkconv application failed with `std::bad_variant_access` errors and missing database tables, preventing web interface from working.

**Root Causes Identified**:
1. **XML Table Schema Bug**: `tkgetxml.cc` line 32 created tables with wrong schema
2. **Skiptoken Strategy Flaw**: High skiptoken (22500000) caused 0 entries for reference entities (Person, Fractie, etc.)
3. **Variant Access Issues**: SQLiteWriter returning mixed types (string vs int64_t) 
4. **Missing Entity Dependencies**: Only 5 of 27 entity categories were being synced

**Current Status**: ✅ **WORKING** - All issues resolved, web interface functional

---

## 🔧 Changes Made (Current State)

### ✅ **Critical Fixes - KEEP THESE**

1. **`docker-compose.minimal.yml`** - New clean setup
2. **`docker/tksync-skiptoken.sh`** - Intelligent adaptive skiptoken logic:
   - 8 phases in dependency order (Base→Seats→Mappings→Core→Actors→PersonData→Processes→Meta)
   - Exponential backoff: 22500000 → -500k → -1M → -2M → -4M → -8M → -16M → from beginning
   - All 27 entity categories included
3. **`tkgetxml.cc` line 32**:
   ```cpp
   // OLD (BROKEN):
   sqlw.query("create table if not exists "+category+" (skiptoken INT)");
   
   // NEW (FIXED):
   sqlw.query("create table if not exists "+category+" (category TEXT, id TEXT, skiptoken INT, enclosure TEXT, updated TEXT, xml TEXT)");
   ```

### 🤔 **Defensive Fixes - REVIEW THESE**

4. **`tkconv.cc` - Safe variant handling**:
   - Added: `#include <variant>`
   - Added: `safe_atoi()` and `safe_atof()` functions (lines 9-21)
   - Added: Variant access error handling (lines 909-927)
   - Added: Safe skiptoken retrieval (lines 93-97)
   - Added: Safe XML content access (lines 108-115)
   - Changed: ~25 `atoi()` calls to `safe_atoi()` throughout entity processing

---

## 📋 TODO Items

### **Priority 1: Secure Essential Fixes** 🔒

**Task**: Commit the absolutely critical changes
```bash
git add docker-compose.minimal.yml docker/tksync-skiptoken.sh tkgetxml.cc
git commit -m "Essential fixes: XML schema bug + intelligent skiptoken sync

- Fix tkgetxml.cc table schema (was missing columns)
- Add adaptive skiptoken logic for all 27 entities 
- Organize entities in dependency order to prevent FK violations
- Add exponential backoff when no data found at current skiptoken"
```

**Rationale**: These fixes are the core innovation and bug fixes. Without them, the system doesn't work.

---

### **Priority 2: Experiment with atoi() Optimization** 🧪

**Hypothesis**: Now that we have complete entity relationships, empty string issues may be resolved, making `safe_atoi()` calls potentially unnecessary.

**Plan**:
1. Create experimental branch:
   ```bash
   git checkout -b experiment-revert-safe-atoi
   ```

2. **Keep Critical Infrastructure**:
   ```cpp
   #include <variant>                    // ✅ KEEP - Required for SQLiteWriter
   safe_atoi() function definition       // ✅ KEEP - Utility function  
   safe_atof() function definition       // ✅ KEEP - Utility function
   Variant access error handling         // ✅ KEEP - Prevents crashes
   Skiptoken variant access (lines 93-97) // ✅ KEEP - Critical for DB read
   XML content variant access (lines 108-115) // ✅ KEEP - Critical for XML parse
   ```

3. **Selectively Revert atoi() Calls**:
   Target these conversions for reversion:
   ```cpp
   // REVERT CANDIDATES (~20 locations):
   safe_atoi(fields["nummer"])     → atoi(fields["nummer"].c_str())
   safe_atoi(fields["gewicht"])    → atoi(fields["gewicht"].c_str()) 
   safe_atoi(fields["volgorde"])   → atoi(fields["volgorde"].c_str())
   safe_atoi(fields["jaar"])       → atoi(fields["jaar"].c_str())
   // etc...
   
   // KEEP AS-IS (critical paths):
   safe_atoi(next.substr(pos+10))  → Keep (skiptoken parsing)
   safe_atoi(get<string>(skiptoken_var)) → Keep (variant access)
   ```

4. **Test Methodology**:
   ```bash
   # Rebuild and test
   docker build -t tkconv:latest .
   docker-compose -f docker-compose.minimal.yml down
   docker volume rm tkconv_data-minimal  # Fresh start
   docker-compose -f docker-compose.minimal.yml up -d
   
   # Monitor logs for variant access errors
   docker logs tkconv-tksync-minimal-1 | grep -i error
   
   # Test web interface
   curl http://localhost:8089/
   curl http://localhost:8089/kamerleden.html
   curl http://localhost:8089/stemmingen.html
   ```

**Success Criteria**: 
- ✅ No variant access errors in logs
- ✅ All entity sync completes successfully  
- ✅ Web interface returns HTML (not 500 errors)
- ✅ Database contains expected record counts

**Rollback Plan**: If experiment fails, `git checkout main && git branch -D experiment-revert-safe-atoi`

---

### **Priority 3: Code Documentation** 📚

**Task**: Document the adaptive skiptoken innovation
```bash
# Add comments to tksync-skiptoken.sh explaining:
# - Why dependency order matters
# - How exponential backoff works  
# - Why different entities need different skiptoken ranges
```

**Task**: Add inline comments to variant access code
```cpp
// Explain why SQLiteWriter returns mixed variant types
// Document when string vs int64_t is expected
```

---

### **Priority 4: Performance Baseline** 📊

**Task**: Measure current performance
```bash
time docker exec tkconv-tksync-minimal-1 /usr/local/bin/tkconv Document
# Baseline: How long does processing take with safe_atoi()?
```

**Task**: Compare with reverted atoi() calls
- Expected improvement: ~10-15% faster (micro-optimization)
- More important: Cleaner, more maintainable code

---

## 🤝 Decision Rationale

### **Why Keep Infrastructure:**
- **Variant access errors are real** - We saw them in production logs
- **Future-proofing** - API changes might introduce new edge cases  
- **Debugging value** - Error logging helps troubleshoot issues
- **Low cost** - Function definitions don't hurt performance

### **Why Experiment with Reverting atoi() Calls:**
- **Complete entity hypothesis** - Full relationships should eliminate empty strings
- **Code simplicity** - Closer to original, more maintainable
- **Performance gain** - Small but measurable improvement
- **KISS principle** - Don't over-engineer solutions

### **Why Staggered Approach:**
- **Risk management** - Secure critical fixes first
- **Scientific method** - Test one hypothesis at a time  
- **Easy rollback** - Experimental branch can be discarded
- **Learning opportunity** - Understand which parts are truly necessary

---

## 🎯 Expected Outcome

**Best Case**: 
- Critical infrastructure maintained for safety
- 80% of safe_atoi() calls reverted to atoi() for performance/clarity
- System remains stable and functional
- Codebase is cleaner and closer to original

**Worst Case**:
- Experiment fails, revert to current working state
- No harm done, lessons learned about which defensive measures are needed

**Timeline**: ~2-3 hours total
- 30 min: Secure essential fixes
- 60 min: Implement and test atoi() reversion
- 30 min: Documentation and cleanup

---

*Created: December 2024*
*Status: Ready for implementation* 