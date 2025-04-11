import pytest
from blueprints.content_generation import scheduler_blueprint, shared
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import pytz
import openai

class MockDatetime(datetime):
    """Mock datetime for testing."""
    _mock_now = None

    @classmethod
    def set_now(cls, dt):
        cls._mock_now = dt

    @classmethod
    def now(cls, tz=None):
        if not cls._mock_now:
            return datetime.now(tz)
        if tz is None:
            return cls._mock_now
        return cls._mock_now.astimezone(tz)

def test_get_default_variable_values():
    # Test with valid variables
    template = {
        'settings': {
            'promptTemplate': {
                'variables': [
                    {'name': 'topic', 'values': ['tech', 'science']},
                    {'name': 'tone', 'values': ['casual', 'professional']}
                ]
            }
        }
    }
    result = scheduler_blueprint._get_default_variable_values(template)
    assert isinstance(result, dict)
    assert 'topic' in result
    assert result['topic'] in ['tech', 'science']
    assert 'tone' in result
    assert result['tone'] in ['casual', 'professional']

    # Test with empty variables
    template = {
        'settings': {
            'promptTemplate': {
                'variables': []
            }
        }
    }
    result = scheduler_blueprint._get_default_variable_values(template)
    assert isinstance(result, dict)
    assert len(result) == 0

    # Test with missing structures
    template = {}
    result = scheduler_blueprint._get_default_variable_values(template)
    assert isinstance(result, dict)
    assert len(result) == 0

def test_get_templates_for_current_time(mock_cosmos_client):
    client, db, container = mock_cosmos_client
    
    # Set up our test time (we'll adjust the template to match current time)
    current_time = datetime.now(timezone.utc)
    current_day = current_time.strftime('%A').lower()
    current_hour = current_time.hour
    current_minute = current_time.minute

    # Create a mock template that matches current time
    mock_template = {
        'id': 'test-template',
        'metadata': {'isActive': True},
        'templateInfo': {
            'brandId': 'test-brand',
            'contentType': 'post'
        },
        'schedule': {
            'daysOfWeek': [current_day],  # Use current day
            'timeSlots': [
                {
                    'hour': current_hour,    # Use current hour
                    'minute': current_minute, # Use current minute
                    'timezone': 'UTC'
                }
            ],
            'maxPostsPerDay': 5
        }
    }

    # Set up the mocks
    with patch('azure.cosmos.CosmosClient') as mock_cosmos:
        # Reset and configure CosmosDB mock
        shared._cosmos_client = None
        mock_cosmos.from_connection_string.return_value = client
        
        # Set up container responses
        container.query_items.side_effect = [
            [mock_template],  # First call returns template
            [{'count': 0}]    # Second call returns post count
        ]
        
        # Execute the function
        templates = scheduler_blueprint._get_templates_for_current_time()
        
        # Verify results
        assert isinstance(templates, list)
        assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"
        assert templates[0]['id'] == 'test-template'
        assert container.query_items.call_count > 0

def test_generate_scheduled_content(mock_cosmos_client, mock_openai):
    client, db, container = mock_cosmos_client
    current_time = datetime.now(timezone.utc)
    
    # Create mock template with proper structure
    mock_template = {
        'id': 'test-template',
        'metadata': {'isActive': True},
        'templateInfo': {
            'brandId': 'test-brand',
            'contentType': 'post'
        },
        'settings': {
            'promptTemplate': {
                'variables': [
                    {'name': 'topic', 'values': ['tech']}
                ],
                'userPrompt': 'Generate content about {topic}',
                'model': 'gpt-4',
                'systemPrompt': 'You are a content creator',
                'temperature': 0.7,
                'maxTokens': 1000
            },
            'contentStrategy': {
                'targetAudience': 'tech enthusiasts',
                'tone': 'professional',
                'keywords': ['tech', 'innovation'],
                'hashtagStrategy': 'relevant industry hashtags',
                'callToAction': 'Learn more'
            }
        },
        'schedule': {
            'daysOfWeek': [current_time.strftime('%A').lower()],
            'timeSlots': [
                {
                    'hour': current_time.hour,
                    'minute': current_time.minute,
                    'timezone': 'UTC'
                }
            ],
            'maxPostsPerDay': 5
        }
    }

    with patch("azure.cosmos.CosmosClient") as mock_cosmos, \
         patch("openai.chat.completions.create", mock_openai.chat.completions.create):
        mock_cosmos.return_value = mock_cosmos_client[0]
        
        # Mock container query responses
        container.query_items.side_effect = [
            [mock_template],  # First call returns templates
            [{'count': 0}],  # Second call returns post count
            [{
                'id': 'test-brand',
                'brandInfo': {
                    'name': 'Test Brand',
                    'description': 'A test brand'
                }
            }]  # Third call returns brand
        ]
        
        # Mock successful post creation
        mock_post = {
            'id': 'test-post',
            'content': {
                'mainText': 'Generated content',
                'caption': 'Test caption',
                'hashtags': ['#test'],
                'callToAction': 'Test CTA'
            }
        }
        container.create_item.return_value = mock_post
        
        # Create a mock timer request
        timer = MagicMock()
        timer.past_due = False
        timer.schedule_status.last = current_time.isoformat()
        
        # Test function execution
        scheduler_blueprint.generate_scheduled_content(timer)
        
        # Verify calls were made
        assert container.query_items.call_count > 0
        assert container.create_item.call_count > 0