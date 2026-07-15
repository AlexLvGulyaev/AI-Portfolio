# AI Portfolio Backend

Backend for AI Portfolio AI Assistant.

## Architecture

Based on proven patterns from:
- **Review Flow**: FastAPI structure, AI Provider management, Operational logging
- **Assistant Flow**: Conversation Memory Service, Chat Sessions
- **PEcf09**: ChromaDB for RAG, Response caching

## Key Components

### 1. Web Framework
- **FastAPI** (from Review Flow, PEcf11)
- Async support, type hints via Pydantic
- CORS middleware for frontend integration

### 2. Memory
- **PostgreSQL** + Conversation Memory Service (from Assistant Flow)
- Required fields: session_id, user_id (from PEcf09, Assistant Flow)
- BudgetPolicy for context management

### 3. Provider Abstraction
- **AI Provider Settings** + Factory (from Review Flow)
- Runtime provider switching
- Fallback mechanism
- OpenAI (primary), GigaChat (fallback)

### 4. RAG Engine
- **ChromaDB** (from PEcf09, Assistant Flow)
- Persistent vector storage
- OpenAI text-embedding-3-small

### 5. Cache
- **In-memory + file** (from PEcf09)
- SHA-256 hash for cache keys
- Persistent between restarts

### 6. Logging
- **Structured logging + PostgreSQL** (from PEcf09, Assistant Flow, Review Flow)
- Required fields: session_id, user_id, event_type, model_name, latency_ms, status

### 7. Fallback
- **Fallback chain** (from Review Flow)
- Active provider → Fallback provider → Static response
- Graceful degradation

### 8. Rate Limiting
- **In-memory rate limiting** (created for AI Portfolio)
- 10 requests per minute per session

## Database Schema

### Tables

1. **ai_provider_settings** (from Review Flow)
   - Runtime AI provider configuration
   - Active/fallback management

2. **chat_sessions** (from Assistant Flow)
   - Session tracking
   - Required: user_id (visitor_id)

3. **chat_messages** (from Assistant Flow, PEcf09)
   - Conversation history
   - Required: session_id, user_id, role, content

4. **operational_logs** (from PEcf09, Assistant Flow, Review Flow)
   - Logging AI interactions
   - Required: event_type, session_id, user_id, model_name, latency_ms, status

## Project Structure

```
backend/
├── app/
│   ├── api/              # API endpoints
│   ├── core/             # Configuration, database
│   ├── models/           # SQLAlchemy models
│   ├── repositories/     # Database repositories
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   │   ├── cache/        # Response caching
│   │   ├── memory/       # Conversation memory
│   │   ├── providers/    # AI providers
│   │   └── rag/          # RAG engine
│   └── main.py           # FastAPI application
├── migrations/           # Database migrations
├── tests/                # Tests
├── requirements.txt      # Dependencies
└── .env.example          # Environment template
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Required:
- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: OpenAI API key
- `GIGACHAT_AUTH_KEY`: GigaChat API key (optional)

### 3. Run Migrations

```bash
alembic upgrade head
```

### 4. Start Server

```bash
uvicorn app.main:app --reload
```

## API Endpoints

### Public Endpoints

- `GET /`: Root endpoint
- `GET /health`: Health check

### Admin Endpoints (TODO)

- `GET /admin/providers`: List AI providers
- `POST /admin/providers/{provider_key}/activate`: Activate provider
- `POST /admin/providers/{provider_key}/set-fallback`: Set fallback provider
- `POST /admin/providers/{provider_key}/test`: Test provider
- `POST /admin/knowledge/reload`: Reload knowledge base

### Chat Endpoint (TODO)

- `POST /chat`: Chat with AI assistant

## Development

### Run Tests

```bash
pytest
```

### Code Style

Follow PEP 8 and use type hints.

## License

AI Automation Portfolio Lab