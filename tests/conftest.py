import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import openai
import json
import pytz
import os
from openai.types.completion import Completion, Choice
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from shared.logger import structured_logger, StructuredLogger
import redis

@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables and configure OpenAI."""
    monkeypatch.setenv("COSMOS_DB_CONNECTION_STRING", "mock_connection_string")
    monkeypatch.setenv("COSMOS_DB_NAME", "mock_db")
    monkeypatch.setenv("COSMOS_DB_CONTAINER_BRAND", "brands")
    monkeypatch.setenv("COSMOS_DB_CONTAINER_TEMPLATE", "templates")
    monkeypatch.setenv("COSMOS_DB_CONTAINER_POSTS", "posts")
    monkeypatch.setenv("OPENAI_API_KEY", "mock_api_key")
    monkeypatch.setenv("REDIS_CONNECTION_STRING", "redis://localhost:6379")
    monkeypatch.setenv("KEY_VAULT_URL", "https://mock-keyvault.vault.azure.net/")
    
    # Configure OpenAI client
    openai.api_key = "mock_api_key"

@pytest.fixture
def mock_cosmos_client():
    """Create a mock Cosmos DB client with proper database and container structure."""
    # Create mock container with all required methods
    mock_container = MagicMock()
    mock_container.query_items.return_value = []
    mock_container.create_item.return_value = {}
    
    # Create mock database that returns the same container for any name
    mock_db = MagicMock()
    mock_db.get_container_client.return_value = mock_container
    
    # Create mock client that returns the same database for any name
    mock_client = MagicMock()
    mock_client.get_database_client.return_value = mock_db
    mock_client.from_connection_string = MagicMock(return_value=mock_client)
    
    return mock_client, mock_db, mock_container

@pytest.fixture
def sample_template():
    return {
        "id": "template-123",
        "metadata": {
            "createdDate": "2025-04-11T13:00:00Z",
            "updatedDate": "2025-04-11T13:00:00Z",
            "isActive": True
        },
        "templateInfo": {
            "name": "Test Template",
            "brandId": "brand-123",
            "contentType": "post"
        },
        "settings": {
            "promptTemplate": {
                "systemPrompt": "You are a content creator",
                "userPrompt": "Create content about {topic}",
                "model": "gpt-4",
                "temperature": 0.7,
                "maxTokens": 1000,
                "variables": [
                    {
                        "name": "topic",
                        "values": ["technology"]
                    }
                ]
            },
            "contentStrategy": {
                "targetAudience": "tech enthusiasts",
                "tone": "professional",
                "keywords": ["tech", "innovation"],
                "hashtagStrategy": "relevant industry hashtags",
                "callToAction": "Learn more on our website"
            }
        }
    }

@pytest.fixture
def sample_brand():
    return {
        "id": "brand-123",
        "metadata": {
            "createdDate": "2025-04-11T13:00:00Z",
            "updatedDate": "2025-04-11T13:00:00Z",
            "isActive": True
        },
        "brandInfo": {
            "name": "Test Brand",
            "description": "A test brand",
            "userId": "user-123"
        }
    }

@pytest.fixture
def mock_openai():
    """Create a mock OpenAI client that returns a properly formatted chat completion."""
    mock_openai = MagicMock()
    mock_message = ChatCompletionMessage(
        role="assistant",
        content=json.dumps({
            "mainText": "Generated content text",
            "caption": "Social media caption",
            "hashtags": ["#tech", "#innovation"],
            "callToAction": "Visit our website"
        }),
        function_call=None,
        tool_calls=None
    )
    mock_choice = Choice(
        finish_reason="stop",
        index=0,
        message=mock_message,
        logprobs=None
    )
    mock_completion = ChatCompletion(
        id="mock-completion",
        choices=[mock_choice],
        created=int(datetime.now(timezone.utc).timestamp()),
        model="gpt-4",
        object="chat.completion",
        usage={"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100}
    )
    mock_openai.chat.completions.create.return_value = mock_completion
    return mock_openai

@pytest.fixture
def fixed_utc_now():
    """Fixture to fix datetime.now() to April 11, 2025 at 13:00 UTC"""
    fixed_dt = datetime(2025, 4, 11, 13, 0, tzinfo=timezone.utc)
    
    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                tz = timezone.utc
            return fixed_dt.astimezone(tz)

    with patch('datetime.datetime', MockDatetime):
        yield fixed_dt

@pytest.fixture
def structured_logger():
    """Create a StructuredLogger instance with mocked logging."""
    logger = StructuredLogger()
    logger.logger = MagicMock()
    return logger

@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    with patch('redis.from_url') as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_key_vault():
    """Create a mock Key Vault client."""
    with patch('azure.keyvault.secrets.SecretClient') as mock_kv:
        mock_client = MagicMock()
        mock_kv.return_value = mock_client
        yield mock_client