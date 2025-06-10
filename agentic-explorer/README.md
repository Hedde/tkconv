# Tweede Kamer AI - Agentic Explorer

Een geavanceerd AI-agenten systeem voor Nederlandse parlementaire data analyse, gebouwd op Microsoft Semantic Kernel met gespecialiseerde agents.

## 🏗️ Architectuur

### Core Framework
- **Microsoft Semantic Kernel**: AI orchestration en agent management
- **FastAPI**: Moderne async web framework voor API endpoints  
- **SQLite MCP**: Model Context Protocol voor database toegang
- **Docker**: Containerized deployment met intelligente data sync

### Agent Specialization Architecture

```
📊 User Query
    ↓
🎭 Magentic Orchestration
    ↓
🤖 Specialized Agents
    ├── PersonAgent      → Kamerleden & Politieke Partijen
    ├── DocumentAgent    → Parlementaire Documenten & Wetgeving  
    ├── VotingAgent      → Stemmingen & Besluiten
    └── CaseAgent        → Procedures & Activiteiten
    ↓
🗄️ SQLite Database (tk.sqlite3)
    ↓
✅ Structured Response
```

## 🤖 Agent Specializations

### PersonAgent
**Expertise**: Kamerleden, politieke partijen, commissies, nevenfuncties
- **Database Toegang**: `Persoon`, `Fractie`, `Commissie`, `FractieZetel*`, `PersoonNevenfunctie`
- **Capabilities**: Biografische info, zetelverdeling, commissielidmaatschap, transparantie data

### DocumentAgent  
**Expertise**: Parlementaire documenten, wetgeving, officiële TK URLs
- **Database Toegang**: `Document`, `DocumentActor`, `Kamerstukdossier`, `DocumentVersie`
- **Capabilities**: Motie/amendement zoeken, URL generatie, dossier management

### VotingAgent
**Expertise**: Stemmingen, besluiten, parlementaire besluitvorming
- **Database Toegang**: `Stemming`, `Besluit`, `Agendapunt`, `Vergadering`
- **Capabilities**: Stemresultaten, fractie analyse, Voor/Tegen/Onthouding tracking

### CaseAgent
**Expertise**: Parlementaire procedures, activiteiten, toezeggingen
- **Database Toegang**: `Zaak`, `ZaakActor`, `Activiteit`, `Toezegging`, `link`
- **Capabilities**: Procedure tracking, status monitoring, timeline analyse

## 📁 Project Structure

```
agentic-explorer/
├── src/
│   ├── main.py                   # FastAPI application entry point
│   ├── requirements.txt          # Python dependencies
│   ├── agents/                   # Specialized AI agents
│   │   ├── person_agent.py       # PersonAgent implementation
│   │   ├── document_agent.py     # DocumentAgent + TK URL generation
│   │   ├── voting_agent.py       # VotingAgent implementation
│   │   ├── case_agent.py         # CaseAgent implementation
│   │   └── research_agent.py     # ResearchAgent for web search
│   ├── api/
│   │   ├── endpoints.py          # FastAPI route definitions
│   │   └── streaming.py          # Server-Sent Events streaming
│   ├── orchestration/
│   │   ├── agents.py             # Agent factory & initialization
│   │   ├── magentic.py           # Magentic orchestration logic
│   │   ├── callbacks.py          # Citation processing & streaming callbacks
│   │   ├── constants.py          # Completion signals & config
│   │   └── prompts/              # System prompts & templates
│   ├── skills/
│   │   ├── mcp/                  # Model Context Protocol clients
│   │   ├── committee_mapping_skill/ # AI-powered committee detection
│   │   └── query_rewriting_skill/ # Query optimization
│   └── utils/
│       ├── identity.py           # System identity configuration
│       ├── logging.py            # Structured JSON logging setup
│       ├── citations.py          # DRY citation system for all agents
│       ├── embedding_cache_store.py # Semantic search caching
│       └── embedding_generator.py # SentenceTransformer embeddings
├── demo/                         # Frontend demo interface
├── docker/                       # Docker configuration
└── README.md                     # This file
```

## 🔧 Technical Implementation

### Semantic Kernel Integration

```python
# Agent Creation Pattern
async def create_specialized_agent() -> ChatCompletionAgent:
    sqlite_client = SQLiteMCPClient()
    fc_behavior = FunctionChoiceBehavior.Auto(
        filters={"included_plugins": ["SQLiteMCPClient"]}, 
        max_auto_invoke_attempts=1
    )
    settings = OpenAIChatPromptExecutionSettings(function_choice_behavior=fc_behavior)
    
    return ChatCompletionAgent(
        service=OpenAIChatCompletion(ai_model_id=openai_model, api_key=openai_api_key),
        plugins=[sqlite_client],
        instructions=specialization_description,
        name="AgentName",
        arguments=KernelArguments(settings=settings, current_date=datetime.now().strftime("%Y-%m-%d"))
    )
```

### Database Architecture
- **32 Specialized Tables**: Complete coverage of TK Open Data API
- **Smart Data Sync**: Intelligent skiptoken-based synchronization
- **Critical Entity Prioritization**: Lower skiptokens for Persoon/Fractie data
- **Relationship Integrity**: Proper foreign key handling across entities

### Completion Detection System

```python
COMPLETION_SIGNALS = [
    "✅ PERSONEN DATA COMPLEET",      # PersonAgent
    "✅ DOCUMENTEN DATA COMPLEET",    # DocumentAgent  
    "✅ STEMMINGS DATA COMPLEET",     # VotingAgent
    "✅ ZAAK DATA COMPLEET",          # CaseAgent
    "✅ DATABASE GERAADPLEEGD",       # Fallback
    "✅ ANTWOORD GEGEVEN"             # General
]
```

### Cross-Agent Communication
Agents kunnen naar elkaar verwijzen voor gespecialiseerde expertise:
- **PersonAgent** → DocumentAgent voor documenten van een Kamerlid
- **DocumentAgent** → VotingAgent voor stemmingen over een motie
- **VotingAgent** → CaseAgent voor procedures rondom besluit

## 🚀 Getting Started

### Prerequisites
- Docker & Docker Compose
- OpenAI API Key
- 4GB+ RAM (voor database operations)

### Quick Start

#### 1. Repository Setup
```bash
git clone <repository>
cd tkconv
```

#### 2. Environment Configuration
Maak een `.env` file aan in de `agentic-explorer/` directory met je OpenAI credentials:

```env
# Verplichte configuratie
OPENAI_API_KEY=sk-...                    # Je OpenAI API key
OPENAI_MODEL=gpt-4o                      # Aanbevolen model

# Optionele configuratie
API_PORT=8091                            # FastAPI server port
CRITICAL_ENTITIES_SKIPTOKEN=15000000     # Persoon/Fractie priority sync
DOCUMENT_SKIPTOKEN=22500000              # Document filtering
INITIAL_SKIPTOKEN=20000000               # Standard entities
```

#### 3. Start met Minimal Dataset
Voor snelle development met beperkte dataset:
```bash
# Start minimal setup met watch mode voor live reloading
docker-compose -f docker-compose.minimal.yml up --build --watch
```

#### 4. Toegang tot Services
- **API**: http://localhost:8091
- **Agentic UI**: Open `agentic-explorer/demo/index.html` in browser
- **Health Check**: http://localhost:8091/health

### ⚠️ Frontend Configuration

De demo UI heeft momenteel een hardcoded backend URL in `agentic-explorer/demo/app.js`:
```javascript
const API_BASE_URL = 'http://localhost:8091';
```

Bij andere poorten of deployment wijzig deze URL dienovereenkomstig.

### Full Dataset
Voor productie met complete TK dataset:
```bash
docker-compose up --build
```

## 🔄 Data Synchronization

### Intelligent Sync Strategy
- **Phase 1**: Critical entities (Persoon, Fractie) met lagere skiptoken
- **Phase 2**: Seat assignments (FractieZetel, CommissieZetel)  
- **Phase 3**: Person mappings (FractieZetelPersoon, etc.)
- **Phase 4**: Parliamentary items (Document, Zaak, Activiteit)
- **Phase 5**: Relationships (DocumentActor, ZaakActor)
- **Phase 6**: Transparency (PersoonNevenfunctie, PersoonGeschenk)
- **Phase 7**: Processes (Stemming, Toezegging)
- **Phase 8**: Metadata (DocumentVersie, CommissieContactinformatie)

### Performance Optimizations
- **Exponential Backoff**: 500K → 16M skiptoken intervals bij 0 entries
- **Parallel Fetching**: Concurrent API calls waar mogelijk
- **Memory Management**: Efficient SQLite operations
- **Critical Entity Refresh**: Periodic updates elke 3 uur

## 📊 API Endpoints

### Core Endpoints
- `POST /magentic/ask` - Synchronous parliamentary data query
- `POST /magentic/ask/stream` - Real-time streaming response with SSE
- `GET /health` - System health check

### Streaming Events
```javascript
// Event types in SSE stream
{
  "event": "system",          // Status updates  
  "event": "agent_start",     // Agent begins work
  "event": "agent_tool_call", // Tool execution start
  "event": "agent_tool_result", // Tool execution complete
  "event": "thought",         // Chain of thought
  "event": "citations_found", // Source citations discovered
  "event": "agent_complete",  // Agent finished
  "event": "loop_detected"    // Anti-loop protection triggered
}
```

## 🎯 Advanced Features

### Citation System & URL Generation

**Automatische Citation Processing**: Het systeem extraheert bronvermeldingen uit agent responses en genereert automatisch werkende links naar officiele TK pagina's.

#### Citation Format
Agents gebruiken gestandaardiseerd citation format:
```
USED_SOURCES_START
SOURCE: id="2025D25729", title="Document titel", publication_date="2025-06-03", type="Brief regering", document_nummer="2025D25729"
USED_SOURCES_END
```

#### Automatische URL Generation
```python
def _generate_official_tk_url(nummer: str, soort: str) -> str:
    """Generate official TK URLs in callbacks.py for citations."""
    url_patterns = {
        "Brief regering": f"https://www.tweedekamer.nl/kamerstukken/brieven_regering/detail?id={nummer}&did={nummer}",
        "Motie": f"https://www.tweedekamer.nl/kamerstukken/moties/detail?id={nummer}&did={nummer}",
        "Amendement": f"https://www.tweedekamer.nl/kamerstukken/amendementen/detail?id={nummer}&did={nummer}",
        "Schriftelijke vragen": f"https://www.tweedekamer.nl/kamerstukken/schriftelijke_vragen/detail?id={nummer}&did={nummer}",
        # ... andere document types
    }
    return url_patterns.get(soort, url_patterns["default"])
```

#### Frontend Integration
```javascript
// Citations automatisch verwerkt met werkende links
{
  "event": "citations_found",
  "citations": [
    {
      "id": "2025D25729",
      "title": "F-35 voortgangsrapportage", 
      "uri": "https://www.tweedekamer.nl/kamerstukken/brieven_regering/detail?id=2025D25729&did=2025D25729",
      "publication_date": "2025-06-04"
    }
  ]
}
```

### Chain of Thought Visualization  
Real-time weergave van agent reasoning process in frontend.

### Anti-Loop Protection
- Maximum 2 tool calls per agent response
- Automatic fallback na tool failures  
- Completion signal enforcement

## 🧪 Development

### Code Standards
- **Type Hints**: Comprehensive typing voor alle functies
- **Async/Await**: Consistent asynchronous patterns
- **Error Handling**: Graceful degradation en logging
- **Clean Architecture**: Separation of concerns

### Adding New Agents
1. Implementeer agent in `src/agents/new_agent.py`
2. Voeg toe aan `orchestration/agents.py`
3. Update completion signals in `constants.py`  
4. Test agent behavior en cross-references

## 🏛️ Parliamentary Data Coverage

### Data Completeness (2025)
- **Personen**: 1,000+ current/former MPs
- **Fracties**: 15+ political parties with seat distribution
- **Documenten**: 10,000+ parliamentary documents
- **Stemmingen**: Comprehensive voting records where available
- **Activiteiten**: Committee meetings, debates, hearings

### Real-world Use Cases
- "Wie is de minister van Klimaat?" → PersonAgent
- "Wat zijn de recente moties over energiebeleid?" → DocumentAgent  
- "Hoe heeft de PVV gestemd over klimaatwet?" → VotingAgent
- "Wat is de status van de stikstofwet procedure?" → CaseAgent

## 📈 Performance Metrics

### Response Times
- **Simple Queries**: <2 seconds
- **Complex Multi-table Joins**: <5 seconds
- **Streaming Latency**: <100ms per token

### Database Performance
- **SQLite Size**: ~500MB with full dataset
- **Query Optimization**: Indexed foreign keys
- **Memory Usage**: <1GB RAM during operation

## 🤝 Contributing

Zie [CONTRIBUTING.md](CONTRIBUTING.md) voor development guidelines, coding standards, en pull request procedures.

## 📄 License

Deze software is gelicenseerd onder [LICENSE](../LICENSE) voorwaarden.

---
**Tweede Kamer AI** - Geavanceerde parlementaire data analyse met AI-agents
