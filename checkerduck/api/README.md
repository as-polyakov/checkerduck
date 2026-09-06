# Verseo API

FastAPI-based REST API for the SEO Domain Checker application.

## Overview

This module provides REST API endpoints for managing domain analysis sessions. It uses FastAPI for high performance and automatic API documentation.

## Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the API Server

```bash
python api_server.py
```

The API will be available at http://localhost:8000

### API Documentation

Once the server is running, visit:
- **Interactive API Docs (Swagger)**: http://localhost:8000/docs
- **Alternative API Docs (ReDoc)**: http://localhost:8000/redoc

## API Endpoints

### Health Check

**GET /**
- Returns service information and status

**GET /health**
- Health check endpoint

### Analysis Management

#### Start Analysis
**POST /api/startAnalysis**

Create and start a new domain analysis session.

**Request Body:**
```json
{
  "name": "Q1 2025 Domain Batch",
  "domains": [
    {
      "domain": "example.com",
      "price": "$250",
      "notes": "High priority target"
    },
    {
      "domain": "test.com",
      "price": "$150",
      "notes": "Secondary option"
    }
  ]
}
```

**Response:** (201 Created)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Q1 2025 Domain Batch",
  "status": "pending",
  "created_at": "2025-01-15T10:30:00",
  "completed_at": null,
  "total_domains": 2,
  "domains_analyzed": 0
}
```

#### List All Analyses
**GET /api/analyses**

Get a list of all analysis sessions.

**Response:** (200 OK)
```json
{
  "analyses": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Q1 2025 Domain Batch",
      "status": "completed",
      "created_at": "2025-01-15T10:30:00",
      "completed_at": "2025-01-15T10:35:00",
      "total_domains": 2,
      "domains_analyzed": 2
    }
  ]
}
```

#### Get Analysis by ID
**GET /api/analyses/{analysis_id}**

Get details of a specific analysis session.

**Response:** (200 OK)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Q1 2025 Domain Batch",
  "status": "running",
  "created_at": "2025-01-15T10:30:00",
  "completed_at": null,
  "total_domains": 2,
  "domains_analyzed": 1
}
```

#### Delete Analysis
**DELETE /api/analyses/{analysis_id}**

Delete an analysis session.

**Response:** (204 No Content)

## Status Values

Analysis can have the following statuses:
- `pending`: Analysis created, waiting to start
- `running`: Analysis in progress
- `completed`: All domains analyzed
- `failed`: Analysis encountered an error

## Data Models

### DomainInput
```python
{
  "domain": str,      # Required - domain name to analyze
  "price": str,       # Optional - price information
  "notes": str        # Optional - notes about the domain
}
```

### AnalysisResponse
```python
{
  "id": str,                    # Unique analysis ID
  "name": str,                  # Analysis name
  "status": str,                # pending|running|completed|failed
  "created_at": datetime,       # Creation timestamp
  "completed_at": datetime,     # Completion timestamp (nullable)
  "total_domains": int,         # Total domains to analyze
  "domains_analyzed": int       # Number of domains processed
}
```

## Architecture

### Module Structure

```
api/
├── __init__.py           # Package initialization
├── models.py             # Pydantic models for request/response
├── routes.py             # API route definitions
├── server.py             # FastAPI app configuration
└── analysis_service.py   # Business logic for analysis operations
```

### Flow

1. **Frontend** sends POST request to `/api/startAnalysis`
2. **routes.py** validates request and calls `analysis_service.create_analysis()`
3. **analysis_service.py** creates analysis record and starts background processing
4. **Background thread** processes domains and updates status
5. **Frontend** polls `/api/analyses/{id}` to get real-time status updates

## Development

### CORS Configuration

The API is configured to allow requests from:
- http://localhost:3000 (React dev server)
- http://localhost:5173 (Vite dev server)

To add more origins, update `api/server.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://your-domain.com"],
    ...
)
```

### Auto-reload

The dev server has auto-reload enabled. Any changes to Python files will automatically restart the server.

### Testing

Test the API using:

**cURL:**
```bash
curl -X POST http://localhost:8000/api/startAnalysis \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Batch", "domains": [{"domain": "example.com"}]}'
```

**Python requests:**
```python
import requests

response = requests.post(
    'http://localhost:8000/api/startAnalysis',
    json={
        'name': 'Test Batch',
        'domains': [{'domain': 'example.com'}]
    }
)
print(response.json())
```

### Storage

Currently uses in-memory storage (`analyses_store` dict in `analysis_service.py`). 

**TODO**: Migrate to database storage using the existing SQLite database.

## Integration with Main Analysis

The `run_analysis()` function in `analysis_service.py` is a placeholder that simulates domain analysis. To integrate with the actual analysis pipeline:

1. Import functions from `main.py` (e.g., `AhrefsClient`, database operations)
2. Replace the simulation logic with actual API calls to Ahrefs, SimilarWeb, etc.
3. Store results in the database using existing DAO functions
4. Update the analysis status and progress accordingly

## Future Enhancements

- [ ] Persist analyses to database
- [ ] Add authentication/authorization
- [ ] Implement WebSocket for real-time updates (instead of polling)
- [ ] Add endpoints for retrieving domain results
- [ ] Implement pagination for large result sets
- [ ] Add export functionality
- [ ] Implement analysis cancellation
- [ ] Add rate limiting
- [ ] Add request validation and better error handling
- [ ] Add comprehensive logging

