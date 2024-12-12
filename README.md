# PostgreSQL to Elasticsearch Sync Solution

A comprehensive data synchronization and search solution that bridges PostgreSQL databases with Elasticsearch, providing real-time data migration and advanced search capabilities.

## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Documentation](#api-documentation)
- [Deployment](#deployment)
- [Development](#development)
- [Performance Considerations](#performance-considerations)
- [Security](#security)

## Features

### Data Synchronization
- Real-time PostgreSQL to Elasticsearch sync
- Configurable sync intervals
- Dynamic batch sizing
- Progress tracking
- Rate limiting
- Connection pooling

### Search Capabilities
- Advanced query support
- Field selection/exclusion
- Multiple pagination strategies
  - Cursor-based (efficient for large datasets)
  - Offset-based (traditional page-based)
- Flexible sorting
- Dynamic field filtering

## Architecture

### Components
1. **Sync Service**
   - Monitors PostgreSQL tables
   - Handles data migration
   - Manages sync status

2. **Search API Service**
   - Provides search endpoints
   - Handles pagination
   - Manages field selection

### Technologies
- Python 3.11+
- FastAPI
- Elasticsearch 8.x
- PostgreSQL
- Kubernetes
- Docker

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd postgres-to-elasticsearch
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Configuration

### Environment Variables

#### PostgreSQL Connection
```env
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=your_db
PG_USER=your_user
PG_PASSWORD=your_password
```

#### Elasticsearch Connection
```env
ES_HOST=localhost
ES_PORT=9200
ES_USER=elastic
ES_PASSWORD=your_password
ES_USE_SSL=true
```

### Sync Configuration
```env
SYNC_INTERVAL=60
MIN_BATCH_SIZE=100
MAX_BATCH_SIZE=1000
RATE_LIMIT=5000
POOL_SIZE=5
```

## API Documentation

### Search API

#### 1. POST /search
Advanced search with field selection and pagination.

**Request Body:**
```json
{
  "index": "your_index",
  "query_fields": {
    "field1": "exact_match",
    "field2": ["value1", "value2"],
    "field3": {
      "gte": 100,
      "lte": 200
    }
  },
  "fields": ["field1", "field2"],
  "exclude_fields": null,
  "size": 10,
  "sort_by": {
    "field1": "asc",
    "field2": "desc"
  },
  "page": 1,
  "page_size": 10
}
```

**Response:**
```json
{
  "data": [
    {
      "field1": "value1",
      "field2": "value2"
    }
  ],
  "meta": {
    "total_records": 100,
    "page_size": 10,
    "current_page": 1,
    "total_pages": 10,
    "has_next": true,
    "has_previous": false,
    "selected_fields": ["field1", "field2"]
  }
}
```

#### 2. GET /search/{index}/scroll
Cursor-based pagination for efficient scrolling through large datasets.

**Request:**
```bash
GET /search/your_index/scroll?cursor=base64_token&size=10&fields=field1,field2
```

**Response:**
```json
{
  "data": [...],
  "meta": {
    "total_records": 1000,
    "page_size": 10,
    "has_next": true,
    "has_previous": true,
    "next_cursor": "base64_encoded_token",
    "selected_fields": ["field1", "field2"]
  }
}
```

#### 3. GET /indices/{index}/fields
Get available fields and their types for an index.

**Request:**
```bash
GET /indices/your_index/fields
```

**Response:**
```json
{
  "index": "your_index",
  "fields": ["field1", "field2", "field3"],
  "field_types": {
    "field1": "text",
    "field2": "keyword",
    "field3": "integer"
  }
}
```

#### 4. GET /indices
List all available indices.

**Request:**
```bash
GET /indices
```

#### 5. GET /health
Check system health.

**Request:**
```bash
GET /health
```

### Query Examples

1. **Basic Search:**
```json
{
  "index": "users",
  "query_fields": {
    "status": "active"
  }
}
```

2. **Range Query:**
```json
{
  "index": "orders",
  "query_fields": {
    "amount": {
      "gte": 100,
      "lte": 1000
    },
    "status": "completed"
  }
}
```

3. **Field Selection:**
```json
{
  "index": "users",
  "query_fields": {
    "age": {"gte": 18}
  },
  "fields": ["name", "email", "age"]
}
```

4. **Field Exclusion:**
```json
{
  "index": "users",
  "query_fields": {
    "status": "active"
  },
  "exclude_fields": ["password_hash", "internal_notes"]
}
```

5. **Sorted Search:**
```json
{
  "index": "products",
  "query_fields": {
    "category": "electronics"
  },
  "sort_by": {
    "price": "asc",
    "rating": "desc"
  }
}
```

## Deployment

### Kubernetes Deployment

1. Create namespace:
```bash
kubectl apply -f k8s/namespace.yaml
```

2. Deploy configuration:
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
```

3. Deploy services:
```bash
kubectl apply -f k8s/api-deployment.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/ingress.yaml
```

### Docker Deployment

1. Build image:
```bash
docker build -t pg-es-sync .
```

2. Run containers:
```bash
# Run API Service
docker run -d \
  --name pg-es-api \
  -p 8000:8000 \
  -e SERVICE_TYPE=api \
  pg-es-sync

# Run Sync Service
docker run -d \
  --name pg-es-sync \
  -e SERVICE_TYPE=sync \
  pg-es-sync
```

## Development

### Setting Up Development Environment

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

2. Install dev dependencies:
```bash
pip install -r requirements-dev.txt
```

### Running Tests
```bash
pytest tests/
```

### Code Style
```bash
# Format code
black .

# Check style
flake8
```

## Performance Considerations

1. **Batch Processing**
   - Configurable batch sizes
   - Dynamic adjustment based on system load

2. **Connection Pooling**
   - Reuse database connections
   - Minimize connection overhead

3. **Pagination Strategies**
   - Use cursor-based pagination for large datasets
   - Offset pagination for smaller datasets

4. **Field Selection**
   - Only fetch required fields
   - Reduce network bandwidth

## Security

1. **Authentication**
   - Basic authentication for Elasticsearch
   - Environment-based credentials

2. **Data Protection**
   - SSL/TLS encryption
   - Field-level access control

3. **Rate Limiting**
   - Configurable rate limits
   - Protection against overload

4. **Error Handling**
   - Secure error messages
   - No sensitive data in logs

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
