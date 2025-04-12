import logging
import json
from datetime import datetime
import uuid
from typing import Any, Dict, Optional
from functools import wraps
import time
import inspect

class StructuredLogger:
    """Structured logging with correlation IDs and performance metrics."""
    
    def __init__(self):
        self._correlation_id = None
        self.logger = logging.getLogger('autogensocial')
        self._configure_logging()
        
    def _configure_logging(self):
        """Configure basic logging."""
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        
    def _format_log(self, level: str, message: str, **kwargs) -> str:
        """Format log message as JSON with standard fields."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'message': message,
            'correlation_id': self._correlation_id or 'no_correlation_id'
        }
        log_data.update(kwargs)
        return json.dumps(log_data)
        
    def set_correlation_id(self, correlation_id: Optional[str] = None):
        """Set correlation ID for request tracking."""
        self._correlation_id = correlation_id or str(uuid.uuid4())
        
    def clear_correlation_id(self):
        """Clear correlation ID after request completion."""
        self._correlation_id = None
        
    def info(self, message: str, **kwargs):
        """Log info level message."""
        self.logger.info(self._format_log('INFO', message, **kwargs))
        
    def error(self, message: str, **kwargs):
        """Log error level message."""
        self.logger.error(self._format_log('ERROR', message, **kwargs))
        
    def warning(self, message: str, **kwargs):
        """Log warning level message."""
        self.logger.warning(self._format_log('WARNING', message, **kwargs))
        
    def debug(self, message: str, **kwargs):
        """Log debug level message."""
        self.logger.debug(self._format_log('DEBUG', message, **kwargs))

def log_function_call(logger: StructuredLogger):
    """Decorator to log function entry/exit and timing."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            function_name = func.__name__
            module_name = inspect.getmodule(func).__name__
            
            # Log function entry
            logger.debug(
                f"Entering {function_name}",
                function=function_name,
                module=module_name
            )
            
            try:
                result = func(*args, **kwargs)
                execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                
                # Log successful execution
                logger.debug(
                    f"Completed {function_name}",
                    function=function_name,
                    module=module_name,
                    execution_time_ms=execution_time
                )
                return result
                
            except Exception as e:
                execution_time = (time.time() - start_time) * 1000
                # Log error
                logger.error(
                    f"Error in {function_name}: {str(e)}",
                    function=function_name,
                    module=module_name,
                    execution_time_ms=execution_time,
                    error=str(e),
                    error_type=type(e).__name__
                )
                raise
                
        return wrapper
    return decorator

# Global logger instance
structured_logger = StructuredLogger()