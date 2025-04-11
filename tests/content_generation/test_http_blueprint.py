import pytest
from unittest.mock import patch, MagicMock
import json
import azure.functions as func
from blueprints.content_generation import http_blueprint, shared
import openai

def test_create_error_response():
    response = http_blueprint.create_error_response(400, "Test error")
    assert response.status_code == 400
    assert json.loads(response.get_body()) == {"error": "Test error"}
    assert response.mimetype == "application/json"

def test_generate_content_http_invalid_json():
    req = func.HttpRequest(
        method='POST',
        url='/api/generate-content',
        body=b'invalid json'
    )
    
    response = http_blueprint.generate_content_http(req)
    assert response.status_code == 400
    assert json.loads(response.get_body()) == {"error": "Invalid JSON in request body"}

def test_generate_content_http_success(mock_cosmos_client, mock_openai):
    # Create mock request with valid data
    req_body = {
        "brandId": "test-brand",
        "templateId": "test-template",
        "variableValues": {"topic": "technology"}
    }
    req = func.HttpRequest(
        method='POST',
        url='/api/generate-content',
        body=json.dumps(req_body).encode('utf-8')
    )

    with patch("azure.cosmos.CosmosClient") as mock_cosmos:
        client, db, _ = mock_cosmos_client
        mock_cosmos.from_connection_string.return_value = client
        
        # Mock container instances
        brands_container = MagicMock()
        templates_container = MagicMock()
        posts_container = MagicMock()
        
        db.get_container_client.side_effect = [
            brands_container,    # First call for brands
            templates_container, # Second call for templates
            posts_container     # Third call for posts
        ]
        
        # Mock brand query
        brands_container.query_items.return_value = [{
            "id": "test-brand",
            "brandInfo": {
                "name": "Test Brand",
                "description": "Test Description"
            }
        }]
        
        # Mock template query
        templates_container.query_items.return_value = [{
            "id": "test-template",
            "templateInfo": {
                "contentType": "post",
                "brandId": "test-brand"
            },
            "settings": {
                "promptTemplate": {
                    "userPrompt": "Test prompt",
                    "model": "gpt-4",
                    "temperature": 0.7,
                    "maxTokens": 1000
                },
                "contentStrategy": {
                    "targetAudience": "tech enthusiasts",
                    "tone": "professional",
                    "keywords": ["tech"],
                    "hashtagStrategy": "relevant",
                    "callToAction": "Learn more"
                }
            }
        }]
        
        # Mock successful post creation
        mock_post = {
            "id": "test-post",
            "metadata": {
                "createdDate": "2025-04-11T13:00:00Z",
                "updatedDate": "2025-04-11T13:00:00Z",
                "isActive": True
            },
            "content": {
                "mainText": "Generated content text",
                "caption": "Social media caption",
                "hashtags": ["#tech", "#innovation"],
                "callToAction": "Visit our website"
            },
            "status": "draft",
            "contentType": "post",
            "brandId": "test-brand",
            "templateId": "test-template",
            "generatedBy": "api",
            "variableValues": {"topic": "technology"}
        }
        posts_container.create_item.return_value = mock_post
        
        # Reset the cached client
        shared._cosmos_client = None
        
        # Test the function
        response = http_blueprint.generate_content_http(req)
        
        # Verify response
        assert response.status_code == 201
        assert json.loads(response.get_body()) == mock_post
        assert response.mimetype == "application/json"

def test_generate_content_http_error(mock_cosmos_client):
    # Create mock request
    req = func.HttpRequest(
        method='POST',
        url='/api/generate-content',
        body=json.dumps({"brandId": "invalid-brand", "templateId": "test-template"}).encode('utf-8')
    )

    with patch("azure.cosmos.CosmosClient") as mock_cosmos:
        client, db, _ = mock_cosmos_client
        mock_cosmos.from_connection_string.return_value = client
        
        # Mock container instances
        brands_container = MagicMock()
        db.get_container_client.return_value = brands_container
        
        # Mock query to return no results (404 error case)
        brands_container.query_items.return_value = []
        
        # Reset the cached client
        shared._cosmos_client = None
        
        # Test the function
        response = http_blueprint.generate_content_http(req)
        
        # Verify error response
        assert response.status_code == 404
        assert "error" in json.loads(response.get_body())