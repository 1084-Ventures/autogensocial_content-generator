import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import pytz
from blueprints.content_generation import shared
import openai

@pytest.fixture(autouse=True)
def clear_cosmos_client():
    """Reset the cached cosmos client between tests."""
    shared._cosmos_client = None
    yield

def test_init_cosmos_client():
    with patch("azure.cosmos.CosmosClient") as mock_cosmos:
        mock_client = MagicMock()
        mock_cosmos.from_connection_string.return_value = mock_client

        client = shared.init_cosmos_client()
        assert client is not None
        mock_cosmos.from_connection_string.assert_called_once()

        # Test caching behavior
        cached_client = shared.init_cosmos_client()
        assert cached_client is client
        assert mock_cosmos.from_connection_string.call_count == 1

def test_get_current_time_in_timezone():
    # Test with valid timezone
    time = shared.get_current_time_in_timezone("UTC")
    assert isinstance(time, datetime)
    assert time.tzinfo is not None
    
    # Test with invalid timezone
    time = shared.get_current_time_in_timezone("INVALID")
    assert isinstance(time, datetime)
    assert time.tzinfo is not None  # Should default to UTC

def test_is_time_matching():
    current_time = datetime.now(timezone.utc)
    slot = {"hour": current_time.hour, "minute": current_time.minute}
    assert shared.is_time_matching(slot, current_time) is True
    
    # Test non-matching time
    slot = {"hour": (current_time.hour + 1) % 24, "minute": current_time.minute}
    assert shared.is_time_matching(slot, current_time) is False

def test_get_todays_post_count(mock_cosmos_client):
    client, db, container = mock_cosmos_client
    container.query_items.return_value = [{"count": 5}]
    
    count = shared.get_todays_post_count(container, "test-brand", "test-template")
    assert count == 5
    assert container.query_items.call_count == 1

def test_generate_content_with_retry(mock_openai):
    prompt_settings = {
        "model": "gpt-4",
        "temperature": 0.7,
        "maxTokens": 1000
    }
    system_prompt = "Test system prompt"
    user_prompt = "Test user prompt"

    with patch("openai.chat.completions.create", mock_openai.chat.completions.create):
        # Test successful generation
        result = shared.generate_content_with_retry(prompt_settings, system_prompt, user_prompt)
        assert isinstance(result, dict)
        assert all(key in result for key in ["mainText", "caption", "hashtags", "callToAction"])

def test_validate_request():
    # Test valid request
    valid_request = {
        "brandId": "test-brand",
        "templateId": "test-template",
        "variableValues": {"topic": "technology"}
    }
    is_valid, error = shared.validate_request(valid_request)
    assert is_valid is True
    assert error is None

    # Test missing required fields
    invalid_request = {
        "brandId": "test-brand"
    }
    is_valid, error = shared.validate_request(invalid_request)
    assert is_valid is False
    assert error is not None

def test_generate_content(mock_cosmos_client, mock_openai):
    # Test successful content generation
    req_body = {
        "brandId": "test-brand",
        "templateId": "test-template",
        "variableValues": {"topic": "technology"}
    }
    
    with patch("azure.cosmos.CosmosClient") as mock_cosmos:
        client, db, container = mock_cosmos_client
        shared._cosmos_client = None  # Reset cached client
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
        
        result, status_code, error = shared.generate_content(req_body)
        assert status_code == 201, f"Expected 201, got {status_code}, error: {error}"
        assert error is None
        assert result == mock_post
        assert posts_container.create_item.call_count == 1