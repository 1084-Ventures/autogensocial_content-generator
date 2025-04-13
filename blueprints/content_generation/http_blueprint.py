import azure.functions as func
from shared import rate_limiter, structured_logger
from shared.logger import log_function_call
from . import shared
import json
from typing import Dict, Any, Tuple, Optional
from enum import Enum

class ErrorCode(Enum):
    UNAUTHORIZED = ("UNAUTHORIZED", 401)
    RATE_LIMIT_EXCEEDED = ("RATE_LIMIT_EXCEEDED", 429)
    INVALID_INPUT = ("INVALID_INPUT", 400)
    VALIDATION_ERROR = ("VALIDATION_ERROR", 400)
    RESOURCE_NOT_FOUND = ("RESOURCE_NOT_FOUND", 404)
    INTERNAL_ERROR = ("INTERNAL_ERROR", 500)

blueprint = func.Blueprint()

@log_function_call(structured_logger)
def validate_api_key(req: func.HttpRequest) -> Tuple[Optional[str], Optional[str]]:
    """Validate API key from request headers."""
    try:
        # Check headers using dict-style access with get() to handle missing headers
        headers = dict(req.headers)
        api_key = headers.get('x-api-key') or headers.get('x-functions-key')
        if not api_key:
            return None, None
            
        settings = shared.load_settings()
        valid_api_key = settings.get('FUNCTIONS_KEY')
        
        if api_key == valid_api_key:
            return api_key, 'api-user'
    except Exception as e:
        structured_logger.warning(f"Error validating API key: {str(e)}", error=str(e))
    return None, None

def create_error_response(error_code: ErrorCode, message: str = None, details: Dict = None) -> func.HttpResponse:
    """Create a standardized error response."""
    code, status_code = error_code.value
    response_body = {
        "error": {
            "code": code,
            "message": message or error_code.name.replace('_', ' ').title()
        }
    }
    if details:
        response_body["error"]["details"] = details
        
    return func.HttpResponse(
        json.dumps(response_body),
        mimetype="application/json",
        status_code=status_code
    )

@blueprint.route(route="generate-content", methods=["POST"])
@log_function_call(structured_logger)
def generate_content_http(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger for content generation."""
    structured_logger.set_correlation_id()
    structured_logger.info('Content generation HTTP trigger function started')
    
    try:
        # Validate API key
        api_key, user_id = validate_api_key(req)
        if not api_key:
            structured_logger.warning("Unauthorized request attempt")
            return create_error_response(ErrorCode.UNAUTHORIZED, "Valid API key required")

        structured_logger.info("Processing request", user_id=user_id)

        # Check rate limit
        remaining_requests = rate_limiter.get_remaining_requests(user_id)
        if not rate_limiter.check_rate_limit(user_id):
            structured_logger.warning(
                "Rate limit exceeded", 
                user_id=user_id, 
                remaining_requests=remaining_requests
            )
            return create_error_response(
                ErrorCode.RATE_LIMIT_EXCEEDED,
                f"Rate limit exceeded. Remaining requests: {remaining_requests}",
                {"remaining_requests": remaining_requests}
            )

        # Parse request body
        try:
            req_body = req.get_json()
        except ValueError:
            return create_error_response(ErrorCode.INVALID_INPUT, "Invalid JSON in request body")

        # Validate request
        is_valid, error = shared.validate_request(req_body)
        if not is_valid:
            structured_logger.warning("Invalid request", error=error)
            return create_error_response(ErrorCode.VALIDATION_ERROR, error)

        # Generate content
        result, status_code, error = shared.generate_content(req_body)
        if error:
            error_mapping = {
                404: ErrorCode.RESOURCE_NOT_FOUND,
                400: ErrorCode.INVALID_INPUT,
                500: ErrorCode.INTERNAL_ERROR
            }
            error_code = error_mapping.get(status_code, ErrorCode.INTERNAL_ERROR)
            structured_logger.error(
                "Error generating content", 
                error=error, 
                status_code=status_code
            )
            return create_error_response(error_code, error)
                
        structured_logger.info(
            "Content generated successfully",
            template_id=req_body.get('templateId'),
            brand_id=req_body.get('brandId')
        )
        
        response = func.HttpResponse(
            json.dumps(result),
            mimetype="application/json",
            status_code=status_code
        )
        response.headers["X-RateLimit-Remaining"] = str(remaining_requests)
        return response
            
    except Exception as e:
        structured_logger.error(
            "Unexpected error generating content",
            error=str(e),
            error_type=type(e).__name__
        )
        return create_error_response(ErrorCode.INTERNAL_ERROR, "An unexpected error occurred")
            
    finally:
        structured_logger.clear_correlation_id()