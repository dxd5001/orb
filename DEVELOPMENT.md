# Development Guide

This document provides detailed information for developers working on the Obsidian RAG Chatbot project.

## Architecture Overview

The system follows a clean, layered architecture with clear separation of concerns:

```
Frontend (React) 
    |
    v
API Layer (FastAPI)
    |
    v
Generation Layer (LLM interaction)
    |
    v
Retrieval Layer (Vector search)
    |
    v
Indexing Layer (Vector storage)
    |
    v
Embedding Layer (Text vectors)
    |
    v
Ingestion Layer (File reading)
```

## Core Components

### 1. Ingestion Layer (`backend/ingestion/`)

**Purpose**: Read and parse Obsidian vault files

**Key Classes**:
- `BaseIngestor`: Abstract interface for data sources
- `ObsidianIngestor`: Concrete implementation for Obsidian vaults
- `IngestorFactory`: Factory pattern for creating ingestors

**Design Patterns**:
- Abstract Factory for extensibility
- Error resilience (continues processing on individual failures)
- Lazy loading of dependencies

### 2. Embedding Layer (`backend/embedding/`)

**Purpose**: Convert text to vector embeddings

**Key Classes**:
- `EmbeddingBackend`: Abstract interface for embedding providers
- `LocalEmbeddingBackend`: sentence-transformers implementation
- `OpenAIEmbeddingBackend`: OpenAI API implementation
- `EmbeddingBackendFactory`: Factory for creating backends

**Features**:
- Batch processing for efficiency
- Automatic fallback for API failures
- Support for multiple providers

### 3. Indexing Layer (`backend/indexing/`)

**Purpose**: Chunk documents and store in vector database

**Key Classes**:
- `Indexer`: Main indexing orchestrator

**Process**:
1. Split documents into chunks (1000 chars with 200 overlap)
2. Generate embeddings for all chunks
3. Store in ChromaDB with metadata

**Configuration**:
- `CHUNK_SIZE = 1000` characters
- `CHUNK_OVERLAP = 200` characters

### 4. Retrieval Layer (`backend/retrieval/`)

**Purpose**: Search for relevant chunks based on queries

**Key Classes**:
- `Retriever`: Handles similarity search and filtering

**Features**:
- Scope-based filtering (folder and tags)
- Configurable top-k results
- Metadata preservation

### 5. Generation Layer (`backend/generation/`)

**Purpose**: Construct prompts and generate responses

**Key Classes**:
- `Generator`: Orchestrates prompt building and LLM interaction

**Process**:
1. Build prompt from context and history
2. Generate response from LLM
3. Extract and format citations

### 6. LLM Layer (`backend/llm/`)

**Purpose**: Interface with various LLM providers

**Key Classes**:
- `LLMBackend`: Abstract interface
- `LocalLLMBackend`: OpenAI-compatible local APIs
- `OllamaLLMBackend`: Ollama-specific implementation
- `OpenAILLMBackend`: OpenAI API implementation

## Data Models (`backend/models.py`)

### Core Models

**NoteDocument**: Represents a single Obsidian note
```python
@dataclass
class NoteDocument:
    file_path: str
    title: str
    body: str
    tags: List[str]
    frontmatter: Dict[str, Any]
    last_modified: datetime
```

**Chunk**: Represents a chunk of a note
```python
@dataclass
class Chunk:
    chunk_id: str
    text: str
    source_path: str
    title: str
    tags: List[str]
    frontmatter: Dict[str, Any]
    last_modified: datetime
    chunk_index: int
```

**API Models**: Pydantic models for request/response validation

## Configuration Management (`backend/config.py`)

### Features
- Environment variable loading
- Optional OS keyring integration
- Configuration validation
- Vault path validation

### Key Methods
- `get_config(key)`: Get configuration value
- `set_config(key, value)`: Set configuration value
- `get_api_key(service)`: Get API key (with keyring fallback)
- `validate_config()`: Validate required configuration
- `validate_vault_path(path)`: Validate vault directory

## API Design (`backend/routers/`)

### Endpoints

**Chat** (`/api/chat`): Main chat functionality
- Input: `ChatRequest` with query, scope, history
- Output: `ChatResponse` with answer and citations

**Index** (`/api/index`): Vault indexing
- Input: None
- Output: `IndexResponse` with statistics

**Status** (`/api/status`): System status
- Input: None
- Output: `StatusResponse` with system information

**Config** (`/api/config`): Configuration management
- GET: `ConfigGetResponse` with current config
- PUT: `ConfigUpdateRequest` to update configuration

### Dependency Injection
All routers use dependency injection via `get_components()` for:
- Configuration management
- Embedding backend
- LLM backend
- Core processing components

## Testing Strategy

### Test Coverage
- Unit tests for all major components
- Integration tests for API endpoints
- Property-based testing with Hypothesis
- Mock implementations for external dependencies

### Test Structure
```
backend/tests/
|-- test_config.py          # Configuration management
|-- test_models.py          # Data models
|-- test_ingestion_base.py  # Ingestion layer
|-- test_obsidian_ingestor.py # Obsidian-specific ingestion
|-- test_embedding.py       # Embedding layer
|-- test_indexer.py         # Indexing layer
|-- test_retriever.py       # Retrieval layer
|-- test_generator.py       # Generation layer
|-- test_llm.py            # LLM layer
|-- test_main.py           # Main application
```

### Property-Based Testing
Key properties tested:
- Chunk size constraints (Property 6)
- Metadata propagation (Property 7)
- Retrieval result count limits (Property 9)
- Citation generation completeness (Property 10)
- Conversation history limits (Property 11)
- Scope filter accuracy (Property 12)

## Development Workflow

### 1. Adding New Features

1. **Define Data Models**: Add to `backend/models.py`
2. **Implement Core Logic**: Add to appropriate layer
3. **Add Tests**: Create comprehensive test coverage
4. **Add API Endpoint**: If needed, add to `backend/routers/`
5. **Update Documentation**: Update README and development docs

### 2. Adding New LLM/Embedding Providers

1. **Implement Backend Class**: Inherit from appropriate abstract base
2. **Register in Factory**: Add to factory methods
3. **Add Tests**: Comprehensive testing including error cases
4. **Update Configuration**: Add config options and validation

### 3. Adding New Ingestion Sources

1. **Implement Ingestor Class**: Inherit from `BaseIngestor`
2. **Register in Factory**: Add to `IngestorFactory`
3. **Add Tests**: Test with various file formats
4. **Update Documentation**: Document supported formats

## Error Handling Strategy

### Principles
1. **Graceful Degradation**: Continue processing when possible
2. **Clear Error Messages**: Provide actionable error information
3. **Logging**: Comprehensive logging at appropriate levels
4. **Validation**: Input validation at all boundaries

### Error Types
- `ValueError`: Invalid input/configuration
- `ConnectionError`: Network/API connectivity issues
- `RuntimeError`: Processing failures
- `HTTPException`: API-level errors (with proper status codes)

## Performance Considerations

### Embedding Generation
- Batch processing for multiple texts
- Model caching for repeated use
- Truncation of overly long inputs

### Vector Storage
- Efficient chunking strategy
- Metadata optimization
- Index optimization for ChromaDB

### API Performance
- Async processing where possible
- Connection pooling for external APIs
- Response streaming for long operations

## Security Considerations

### Data Privacy
- Local mode: No data leaves the system
- Cloud mode: Clear warnings about external API usage
- API key management: Secure storage options

### Input Validation
- All user inputs validated
- Path traversal prevention
- SQL injection prevention (though using ChromaDB)

### Network Security
- Default localhost binding
- CORS configuration for production
- Rate limiting considerations

## Extensibility Points

### 1. New Data Sources
Implement `BaseIngestor` and register in `IngestorFactory`

### 2. New Embedding Models
Implement `EmbeddingBackend` and register in `EmbeddingBackendFactory`

### 3. New LLM Providers
Implement `LLMBackend` and register in `LLMBackendFactory`

### 4. Custom Processing
- Custom chunking strategies
- Custom prompt templates
- Custom citation extraction

## Debugging

### Logging Levels
- `DEBUG`: Detailed execution information
- `INFO`: General operational information
- `WARNING`: Recoverable issues
- `ERROR`: Serious problems

### Debug Tools
- `test_query()` method in Retriever for debugging searches
- `test_generation()` method in Generator for debugging responses
- Comprehensive error messages with context

### Common Issues
1. **Collection not found**: Need to run indexing first
2. **Model loading failures**: Check model names and availability
3. **Memory issues**: Reduce batch sizes or model complexity
4. **Connection errors**: Verify API endpoints and credentials

## Deployment

### Local Development
```bash
cd backend
python main.py
```

### Production Considerations
- Use WSGI server (Gunicorn/Uvicorn)
- Environment-based configuration
- Log aggregation
- Monitoring and health checks
- SSL/TLS termination

### Docker Support
(Docker configuration can be added for containerized deployment)

## Contributing Guidelines

### Code Style
- Follow PEP 8 for Python code
- Use type hints throughout
- Comprehensive docstrings
- Clear variable and function names

### Testing Requirements
- All new features must include tests
- Maintain >90% test coverage
- Include property-based tests where applicable
- Test error conditions and edge cases

### Pull Request Process
1. Create feature branch
2. Add tests for new functionality
3. Ensure all tests pass
4. Update documentation
5. Submit pull request with clear description

## Future Enhancements

### Planned Features
- Real-time indexing with file watchers
- Advanced search filters (date ranges, file types)
- Multiple vault support
- User authentication and multi-tenancy
- Advanced citation formatting
- Export functionality

### Technical Improvements
- Streaming responses for long generations
- Caching layer for frequently accessed content
- More sophisticated chunking strategies
- Advanced RAG techniques (re-ranking, fusion)
- Performance monitoring and metrics
