from datetime import datetime, timedelta
from typing import Dict, Tuple
import threading
import logging

class InMemoryRateLimiter:
    """Simple in-memory rate limiter for local development."""
    def __init__(self):
        self._requests: Dict[str, Tuple[int, datetime]] = {}
        self._lock = threading.Lock()

    def check_rate_limit(self, user_id: str, limit: int = 100, window: int = 60) -> bool:
        """Check if user has exceeded rate limit."""
        with self._lock:
            now = datetime.now()
            if user_id in self._requests:
                count, start_time = self._requests[user_id]
                # Reset if window has expired
                if now - start_time > timedelta(seconds=window):
                    self._requests[user_id] = (1, now)
                    return True
                # Check if under limit
                if count >= limit:
                    return False
                # Increment counter
                self._requests[user_id] = (count + 1, start_time)
                return True
            # First request
            self._requests[user_id] = (1, now)
            return True

    def get_remaining_requests(self, user_id: str, limit: int = 100) -> int:
        """Get remaining requests for user in current window."""
        with self._lock:
            if user_id not in self._requests:
                return limit
            count, _ = self._requests[user_id]
            return max(0, limit - count)

# Global rate limiter instance
rate_limiter = InMemoryRateLimiter()