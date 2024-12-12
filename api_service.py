from fastapi import FastAPI, HTTPException, Query
from elasticsearch import Elasticsearch
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Union, Set
import os
from dotenv import load_dotenv
import base64
import json

load_dotenv()

app = FastAPI(title="Elasticsearch Search API")

# Initialize Elasticsearch client
es_client = Elasticsearch(
    [f"{os.getenv('ES_HOST')}:{os.getenv('ES_PORT')}"],
    basic_auth=(os.getenv('ES_USER'), os.getenv('ES_PASSWORD')),
    use_ssl=os.getenv('ES_USE_SSL', 'false').lower() == 'true'
)

class SearchQuery(BaseModel):
    index: str
    query_fields: Dict[str, Any]
    size: Optional[int] = Field(default=10, ge=1, le=100)
    sort_by: Optional[Dict[str, str]] = None
    search_after: Optional[List[Any]] = None  # For cursor-based pagination
    page: Optional[int] = Field(default=1, ge=1)  # For offset pagination
    page_size: Optional[int] = Field(default=10, ge=1, le=100)  # For offset pagination
    fields: Optional[List[str]] = None  # For field selection
    exclude_fields: Optional[List[str]] = None  # For excluding specific fields

class PaginationMeta(BaseModel):
    total_records: int
    page_size: int
    current_page: Optional[int] = None
    total_pages: Optional[int] = None
    has_next: bool
    has_previous: bool
    next_cursor: Optional[str] = None
    selected_fields: Optional[List[str]] = None

class SearchResponse(BaseModel):
    data: List[Dict[str, Any]]
    meta: PaginationMeta

def create_search_after_token(sort_values: List[Any]) -> str:
    """Create a base64 encoded token for cursor pagination"""
    return base64.b64encode(json.dumps(sort_values).encode()).decode()

def decode_search_after_token(token: str) -> List[Any]:
    """Decode a search_after token"""
    try:
        return json.loads(base64.b64decode(token.encode()).decode())
    except:
        raise HTTPException(status_code=400, detail="Invalid pagination token")

def filter_document_fields(doc: Dict[str, Any], fields: Optional[List[str]], exclude_fields: Optional[List[str]]) -> Dict[str, Any]:
    """Filter document fields based on inclusion and exclusion lists"""
    if not fields and not exclude_fields:
        return doc

    if exclude_fields:
        return {k: v for k, v in doc.items() if k not in exclude_fields}

    if fields:
        return {k: doc.get(k) for k in fields if k in doc}

    return doc

@app.post("/search", response_model=SearchResponse)
async def search(search_query: SearchQuery):
    try:
        # Validate field selection
        if search_query.fields and search_query.exclude_fields:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both fields and exclude_fields"
            )

        # Construct Elasticsearch query
        must_conditions = []
        for field, value in search_query.query_fields.items():
            if isinstance(value, list):
                must_conditions.append({"terms": {field: value}})
            elif isinstance(value, dict):
                must_conditions.append({"range": {field: value}})
            else:
                must_conditions.append({"match": {field: value}})

        # Base query
        query = {
            "query": {
                "bool": {
                    "must": must_conditions
                }
            }
        }

        # Handle field selection in Elasticsearch query
        if search_query.fields:
            query["_source"] = search_query.fields
        elif search_query.exclude_fields:
            query["_source"] = {
                "excludes": search_query.exclude_fields
            }

        # Handle sorting
        sort_fields = []
        if search_query.sort_by:
            sort_fields = [{field: {"order": order}} 
                         for field, order in search_query.sort_by.items()]
        else:
            sort_fields = [{"_id": "asc"}]
        
        query["sort"] = sort_fields

        # Handle pagination
        if search_query.search_after:
            query["size"] = search_query.size
            query["search_after"] = search_query.search_after
        else:
            query["size"] = search_query.page_size
            query["from"] = (search_query.page - 1) * search_query.page_size

        # Execute search
        response = es_client.search(
            index=search_query.index,
            body=query,
            track_total_hits=True
        )

        hits = response["hits"]["hits"]
        total_records = response["hits"]["total"]["value"]

        # Process hits with field filtering
        filtered_hits = [
            filter_document_fields(
                hit["_source"],
                search_query.fields,
                search_query.exclude_fields
            )
            for hit in hits
        ]

        # Prepare pagination metadata
        if search_query.search_after:
            has_next = len(hits) == search_query.size
            next_cursor = create_search_after_token(hits[-1]["sort"]) if has_next else None
            
            meta = PaginationMeta(
                total_records=total_records,
                page_size=search_query.size,
                has_next=has_next,
                has_previous=bool(search_query.search_after),
                next_cursor=next_cursor,
                selected_fields=search_query.fields
            )
        else:
            total_pages = (total_records + search_query.page_size - 1) // search_query.page_size
            
            meta = PaginationMeta(
                total_records=total_records,
                page_size=search_query.page_size,
                current_page=search_query.page,
                total_pages=total_pages,
                has_next=search_query.page < total_pages,
                has_previous=search_query.page > 1,
                selected_fields=search_query.fields
            )

        return SearchResponse(
            data=filtered_hits,
            meta=meta
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search/{index}/scroll")
async def scroll_search(
    index: str,
    cursor: Optional[str] = None,
    size: int = Query(default=10, ge=1, le=100),
    sort_by: Optional[str] = None,
    fields: Optional[str] = None,
    exclude_fields: Optional[str] = None
):
    """Endpoint for cursor-based pagination with field selection"""
    try:
        # Validate field selection
        if fields and exclude_fields:
            raise HTTPException(
                status_code=400,
                detail="Cannot specify both fields and exclude_fields"
            )

        # Parse fields
        field_list = fields.split(',') if fields else None
        exclude_list = exclude_fields.split(',') if exclude_fields else None

        # Parse sort parameters
        sort_fields = []
        if sort_by:
            for sort_item in sort_by.split(','):
                field, order = sort_item.split(':') if ':' in sort_item else (sort_item, 'asc')
                sort_fields.append({field: {"order": order}})
        else:
            sort_fields = [{"_id": "asc"}]

        # Build query
        query = {
            "query": {"match_all": {}},
            "sort": sort_fields,
            "size": size
        }

        # Handle field selection
        if field_list:
            query["_source"] = field_list
        elif exclude_list:
            query["_source"] = {
                "excludes": exclude_list
            }

        # Add search_after if cursor is provided
        if cursor:
            search_after = decode_search_after_token(cursor)
            query["search_after"] = search_after

        # Execute search
        response = es_client.search(
            index=index,
            body=query,
            track_total_hits=True
        )

        hits = response["hits"]["hits"]
        total_records = response["hits"]["total"]["value"]

        # Process hits with field filtering
        filtered_hits = [
            filter_document_fields(
                hit["_source"],
                field_list,
                exclude_list
            )
            for hit in hits
        ]

        # Prepare pagination metadata
        has_next = len(hits) == size
        next_cursor = create_search_after_token(hits[-1]["sort"]) if has_next else None

        meta = PaginationMeta(
            total_records=total_records,
            page_size=size,
            has_next=has_next,
            has_previous=bool(cursor),
            next_cursor=next_cursor,
            selected_fields=field_list
        )

        return SearchResponse(
            data=filtered_hits,
            meta=meta
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/indices/{index}/fields")
async def get_index_fields(index: str):
    """Get all available fields for an index"""
    try:
        mapping = es_client.indices.get_mapping(index=index)
        properties = mapping[index]["mappings"].get("properties", {})
        return {
            "index": index,
            "fields": list(properties.keys()),
            "field_types": {
                field: properties[field].get("type")
                for field in properties
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/indices")
async def list_indices():
    try:
        indices = es_client.cat.indices(format="json")
        return indices
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    try:
        health = es_client.cluster.health()
        return {"status": "healthy", "cluster_health": health}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
