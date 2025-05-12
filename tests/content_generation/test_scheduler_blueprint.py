import pytest
from blueprints.content_generation import scheduler_blueprint, shared
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import pytz
import openai
import json

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

@pytest.fixture
def mock_template():
    """Create a mock template with current time settings."""
    current_time = datetime.now(timezone.utc)
    return {
        'id': 'test-template',
        'metadata': {'isActive': True},
        'templateInfo': {
            'brandId': 'test-brand',
            'contentType': 'post'
        },
        'settings': {
            'promptTemplate': {
                'variables': [
                    {'name': 'topic', 'values': ['tech', 'science']},
                    {'name': 'tone', 'values': ['casual', 'professional']}
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
                'keywords': ['tech'],
                'hashtagStrategy': 'relevant',
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

@pytest.fixture
def mock_timer_request():
    """Create a mock timer request."""
    return MagicMock(past_due=False)

def test_get_default_variable_values(mock_template):
    """Test variable value selection for templates."""
    result = scheduler_blueprint._get_default_variable_values(mock_template)
    assert isinstance(result, dict)
    assert 'topic' in result
    assert result['topic'] in ['tech', 'science']
    assert 'tone' in result
    assert result['tone'] in ['casual', 'professional']

    # Test with empty template
    assert scheduler_blueprint._get_default_variable_values({}) == {}

    # Test with invalid structure
    invalid_template = {'settings': {'promptTemplate': {}}}
    assert scheduler_blueprint._get_default_variable_values(invalid_template) == {}

def test_get_templates_for_current_time(mock_cosmos_client, mock_template):
    client, db, container = mock_cosmos_client
    
    with patch('azure.cosmos.CosmosClient') as mock_cosmos, \
         patch('blueprints.content_generation.shared.load_settings', return_value={
             'COSMOS_DB_NAME': 'test-db',
             'COSMOS_DB_CONTAINER_TEMPLATE': 'templates'
         }):
        
        # Reset and configure CosmosDB mock
        shared._cosmos_client = None
        mock_cosmos.from_connection_string.return_value = client
        
        # Set up container responses
        container.query_items.side_effect = [
            [mock_template],  # Template query
            [{'count': 0}]    # Post count query
        ]
        
        templates = scheduler_blueprint._get_templates_for_current_time()
        assert len(templates) == 1
        assert templates[0]['id'] == 'test-template'

        # Test with inactive template
        inactive_template = mock_template.copy()
        inactive_template['metadata']['isActive'] = False
        container.query_items.side_effect = [
            [inactive_template],
            [{'count': 0}]
        ]
        templates = scheduler_blueprint._get_templates_for_current_time()
        assert len(templates) == 0

def test_generate_scheduled_content(mock_cosmos_client, mock_openai, mock_template, mock_timer_request):
    with patch('azure.cosmos.CosmosClient') as mock_cosmos, \
         patch('blueprints.content_generation.scheduler_blueprint._get_templates_for_current_time') as mock_get_templates, \
         patch('blueprints.content_generation.shared.load_settings', return_value={
             'COSMOS_DB_NAME': 'test-db',
             'COSMOS_DB_CONTAINER_POSTS': 'posts',
             'OPENAI_API_KEY': 'test-key'
         }):
        
        client, _, container = mock_cosmos_client
        mock_cosmos.return_value = mock_cosmos_client[0]
        mock_get_templates.return_value = [mock_template]
        
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
        
        # Test successful content generation
        scheduler_blueprint.generate_scheduled_content(mock_timer_request)
        assert container.create_item.call_count > 0

def test_generate_scheduled_content_error_handling(mock_timer_request, structured_logger):
    with patch('blueprints.content_generation.scheduler_blueprint._get_templates_for_current_time') as mock_get_templates, \
         patch('blueprints.content_generation.shared.generate_content') as mock_generate:
        
        # Test past due timer
        past_due_timer = MagicMock(past_due=True)
        scheduler_blueprint.generate_scheduled_content(past_due_timer)
        warning_entries = [
            json.loads(call[0][0]) 
            for call in structured_logger.logger.warning.call_args_list
        ]
        assert any("Timer trigger is past due" in entry["message"] for entry in warning_entries)
        
        # Test content generation error
        mock_timer_request.past_due = False
        mock_get_templates.return_value = [{'id': 'test-template', 'templateInfo': {'brandId': 'test-brand'}}]
        mock_generate.return_value = (None, 500, "Test error")
        
        scheduler_blueprint.generate_scheduled_content(mock_timer_request)
        error_entries = [
            json.loads(call[0][0]) 
            for call in structured_logger.logger.error.call_args_list
        ]
        assert any("Error generating scheduled content" in entry["message"] for entry in error_entries)

def test_timezone_handling(mock_cosmos_client, mock_template):
    client, _, container = mock_cosmos_client
    current_utc = datetime.now(timezone.utc)
    
    # Test different timezone scenarios
    test_timezones = [
        ('America/New_York', -4),  # EDT
        ('UTC', 0),
        ('Asia/Tokyo', 9)
    ]
    
    for tz_name, offset in test_timezones:
        template = mock_template.copy()
        template['schedule']['timeSlots'][0]['timezone'] = tz_name
        local_time = current_utc.astimezone(pytz.timezone(tz_name))
        template['schedule']['timeSlots'][0].update({
            'hour': local_time.hour,
            'minute': local_time.minute
        })
        
        with patch('azure.cosmos.CosmosClient') as mock_cosmos, \
             patch('blueprints.content_generation.shared.load_settings', return_value={
                 'COSMOS_DB_NAME': 'test-db',
                 'COSMOS_DB_CONTAINER_TEMPLATE': 'templates'
             }):
            
            shared._cosmos_client = None
            mock_cosmos.from_connection_string.return_value = client
            container.query_items.side_effect = [[template], [{'count': 0}]]
            
            templates = scheduler_blueprint._get_templates_for_current_time()
            assert len(templates) == 1
            assert templates[0]['schedule']['timeSlots'][0]['timezone'] == tz_name