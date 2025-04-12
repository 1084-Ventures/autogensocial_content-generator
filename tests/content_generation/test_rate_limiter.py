import pytest
from unittest.mock import patch, MagicMock
from blueprints.rate_limiter import RateLimiter
import redis

@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    with patch('redis.from_url') as mock_redis:
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        yield mock_client

@pytest.fixture
def rate_limiter(mock_redis):
    """Create a RateLimiter instance with mocked Redis."""
    with patch('os.getenv', return_value='redis://dummy'):
        limiter = RateLimiter()
        limiter._initialized = False  # Reset for testing
        limiter.__init__()
        return limiter

def test_rate_limiter_initialization(mock_redis):
    """Test RateLimiter initialization with Redis."""
    with patch('os.getenv', return_value='redis://dummy'):
        limiter = RateLimiter()
        assert limiter._redis is not None
        mock_redis.assert_called_once_with('redis://dummy')

def test_rate_limiter_singleton():
    """Test that RateLimiter is a singleton."""
    limiter1 = RateLimiter()
    limiter2 = RateLimiter()
    assert limiter1 is limiter2

def test_check_rate_limit_first_request(rate_limiter, mock_redis):
    """Test rate limit check for first request."""
    mock_redis.get.return_value = None
    assert rate_limiter.check_rate_limit('user123') is True
    mock_redis.setex.assert_called_once_with('rate_limit:user123', 60, 1)

def test_check_rate_limit_under_limit(rate_limiter, mock_redis):
    """Test rate limit check when under limit."""
    mock_redis.get.return_value = '50'
    assert rate_limiter.check_rate_limit('user123') is True
    mock_redis.incr.assert_called_once_with('rate_limit:user123')

def test_check_rate_limit_exceeded(rate_limiter, mock_redis):
    """Test rate limit check when limit exceeded."""
    mock_redis.get.return_value = '100'
    assert rate_limiter.check_rate_limit('user123') is False
    mock_redis.incr.assert_not_called()

def test_check_rate_limit_redis_error(rate_limiter, mock_redis):
    """Test rate limit check handles Redis errors gracefully."""
    mock_redis.get.side_effect = redis.RedisError()
    assert rate_limiter.check_rate_limit('user123') is True

def test_get_remaining_requests(rate_limiter, mock_redis):
    """Test getting remaining requests."""
    mock_redis.get.return_value = '30'
    assert rate_limiter.get_remaining_requests('user123', 100) == 70

def test_get_remaining_requests_no_usage(rate_limiter, mock_redis):
    """Test getting remaining requests with no current usage."""
    mock_redis.get.return_value = None
    assert rate_limiter.get_remaining_requests('user123', 100) == 100