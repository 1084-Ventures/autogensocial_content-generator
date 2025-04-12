import pytest
from unittest.mock import patch, MagicMock
import json
import azure.functions as func
from blueprints.content_generation import http_blueprint, shared
from blueprints.content_generation.http_blueprint import ErrorCode

@pytest.fixture
def mock_request():
    """Create a base mock request with default values."""
    def _create_request(body=None, headers=None):
        req = MagicMock(spec=func.HttpRequest)
        req.get_json.return_value = body or {}
        req.headers = headers or {"X-API-Key": "test-key"}
        return req
    return _create_request

@pytest.fixture
def mock_settings():
    """Mock settings with test values."""
    return {
        'API_KEY': 'test-key',
        'COSMOS_DB_NAME': 'test-db',
        'COSMOS_DB_CONTAINER_BRAND': 'brands',
        'COSMOS_DB_CONTAINER_TEMPLATE': 'templates',
        'COSMOS_DB_CONTAINER_POSTS': 'posts'
    }

def verify_error_response(response, error_code: ErrorCode, message: str = None):
    """Helper to verify error response structure."""
    assert response.status_code == error_code.value[1]
    body = json.loads(response.get_body())
    assert "error" in body
    assert body["error"]["code"] == error_code.value[0]
    if message:
        assert body["error"]["message"] == message

def test_validate_api_key(mock_request, mock_settings):
    with patch('blueprints.content_generation.shared.load_settings', return_value=mock_settings):
        # Valid key
        req = mock_request(headers={"X-API-Key": "test-key"})
        api_key, user_id = http_blueprint.validate_api_key(req)
        assert api_key == "test-key"
        assert user_id == "api-user"

        # Invalid key
        req = mock_request(headers={"X-API-Key": "wrong-key"})
        api_key, user_id = http_blueprint.validate_api_key(req)
        assert api_key is None
        assert user_id is None

def test_generate_content_http_unauthorized(mock_request):
    req = mock_request(headers={})  # No API key
    response = http_blueprint.generate_content_http(req)
    verify_error_response(response, ErrorCode.UNAUTHORIZED, "Valid API key required")

def test_generate_content_http_rate_limit_exceeded(mock_request, mock_settings):
    with patch('blueprints.content_generation.shared.load_settings', return_value=mock_settings), \
         patch('shared.rate_limiter.rate_limiter.check_rate_limit', return_value=False), \
         patch('shared.rate_limiter.rate_limiter.get_remaining_requests', return_value=0):
        
        req = mock_request()
        response = http_blueprint.generate_content_http(req)
        verify_error_response(response, ErrorCode.RATE_LIMIT_EXCEEDED)
        assert "remaining_requests" in json.loads(response.get_body())["error"]["details"]

def test_generate_content_http_invalid_json(mock_request, mock_settings):
    with patch('blueprints.content_generation.shared.load_settings', return_value=mock_settings):
        req = mock_request()
        req.get_json.side_effect = ValueError()
        response = http_blueprint.generate_content_http(req)
        verify_error_response(response, ErrorCode.INVALID_INPUT, "Invalid JSON in request body")

def test_generate_content_http_success(mock_request, mock_cosmos_client, mock_openai, mock_settings):
    req_body = {
        "brandId": "test-brand",
        "templateId": "test-template",
        "variableValues": {"topic": "technology"}
    }
    
    with patch("azure.cosmos.CosmosClient") as mock_cosmos, \
         patch('blueprints.content_generation.shared.load_settings', return_value=mock_settings):
        
        client, db, container = mock_cosmos_client
        mock_cosmos.from_connection_string.return_value = client
        
        # Mock successful content generation
        mock_post = {
            "id": "test-post",
            "content": {
                "mainText": "Generated content",
                "caption": "Test caption",
                "hashtags": ["#test"],
                "callToAction": "Test CTA"
            }
        }
        container.create_item.return_value = mock_post
        
        # Reset cached client
        shared._cosmos_client = None
        
        # Test function with valid request
        req = mock_request(body=req_body)
        response = http_blueprint.generate_content_http(req)
        
        assert response.status_code == 201
        assert json.loads(response.get_body()) == mock_post
        assert "X-RateLimit-Remaining" in response.headers

def test_generate_content_http_error_handling(mock_request, mock_settings):
    req_body = {"brandId": "test-brand", "templateId": "test-template"}
    
    with patch('blueprints.content_generation.shared.load_settings', return_value=mock_settings), \
         patch('blueprints.content_generation.shared.generate_content') as mock_generate:
        
        # Test different error scenarios
        error_scenarios = [
            (404, ErrorCode.RESOURCE_NOT_FOUND, "Resource not found"),
            (400, ErrorCode.INVALID_INPUT, "Invalid input"),
            (500, ErrorCode.INTERNAL_ERROR, "Server error")
        ]
        
        for status_code, error_code, error_msg in error_scenarios:
            mock_generate.return_value = (None, status_code, error_msg)
            req = mock_request(body=req_body)
            response = http_blueprint.generate_content_http(req)
            verify_error_response(response, error_code, error_msg)