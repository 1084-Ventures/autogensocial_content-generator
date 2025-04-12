import pytest
from unittest.mock import patch, MagicMock
import json
import logging
from blueprints.content_generation.logger import StructuredLogger, log_function_call

@pytest.fixture
def structured_logger():
    """Create a StructuredLogger instance with mocked logging."""
    logger = StructuredLogger()
    logger.logger = MagicMock()
    return logger

def test_correlation_id_management(structured_logger):
    """Test correlation ID setting and clearing."""
    assert structured_logger._correlation_id is None
    
    # Test setting custom correlation ID
    structured_logger.set_correlation_id("test-id")
    assert structured_logger._correlation_id == "test-id"
    
    # Test auto-generated correlation ID
    structured_logger.set_correlation_id()
    assert structured_logger._correlation_id is not None
    assert isinstance(structured_logger._correlation_id, str)
    
    # Test clearing correlation ID
    structured_logger.clear_correlation_id()
    assert structured_logger._correlation_id is None

def test_log_formatting(structured_logger):
    """Test log message formatting."""
    structured_logger.set_correlation_id("test-id")
    
    # Test basic log message
    structured_logger.info("Test message")
    log_call = structured_logger.logger.info.call_args[0][0]
    log_data = json.loads(log_call)
    
    assert log_data["level"] == "INFO"
    assert log_data["message"] == "Test message"
    assert log_data["correlation_id"] == "test-id"
    assert "timestamp" in log_data

    # Test log message with additional fields
    structured_logger.error("Error message", error_code=500, detail="Test error")
    log_call = structured_logger.logger.error.call_args[0][0]
    log_data = json.loads(log_call)
    
    assert log_data["level"] == "ERROR"
    assert log_data["message"] == "Error message"
    assert log_data["error_code"] == 500
    assert log_data["detail"] == "Test error"

@log_function_call(StructuredLogger())
def sample_function(arg1, arg2):
    """Sample function for testing the log_function_call decorator."""
    return arg1 + arg2

@log_function_call(StructuredLogger())
def failing_function():
    """Sample function that raises an exception."""
    raise ValueError("Test error")

def test_log_function_call_decorator(structured_logger):
    """Test the log_function_call decorator."""
    with patch('blueprints.content_generation.logger.structured_logger', structured_logger):
        # Test successful function call
        result = sample_function(1, 2)
        assert result == 3
        
        debug_calls = [
            call[0][0] for call in structured_logger.logger.debug.call_args_list
        ]
        log_entries = [json.loads(call) for call in debug_calls]
        
        assert any("Entering sample_function" in entry["message"] for entry in log_entries)
        assert any("Completed sample_function" in entry["message"] for entry in log_entries)
        assert any("execution_time_ms" in entry for entry in log_entries)
        
        # Test function call with exception
        with pytest.raises(ValueError):
            failing_function()
            
        error_calls = [
            call[0][0] for call in structured_logger.logger.error.call_args_list
        ]
        error_entries = [json.loads(call) for call in error_calls]
        
        assert any("Error in failing_function" in entry["message"] for entry in error_entries)
        assert any(entry["error_type"] == "ValueError" for entry in error_entries)
        assert any("execution_time_ms" in entry for entry in error_entries)