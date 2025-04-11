import azure.functions as func
from . import shared
import json
import logging
from typing import Dict, Any

blueprint = func.Blueprint()

def create_error_response(status_code: int, error_message: str) -> func.HttpResponse:
    """Create an error response with the given status code and message."""
    return func.HttpResponse(
        json.dumps({"error": error_message}),
        mimetype="application/json",
        status_code=status_code
    )

@blueprint.route(route="generate-content", methods=["POST"])
def generate_content_http(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger for content generation."""
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()
    except ValueError:
        return create_error_response(400, "Invalid JSON in request body")

    is_valid, error = shared.validate_request(req_body)
    if not is_valid:
        return create_error_response(400, error)

    try:
        result, status_code, error = shared.generate_content(req_body)
        if error:
            return create_error_response(status_code, error)
            
        return func.HttpResponse(
            json.dumps(result),
            mimetype="application/json",
            status_code=status_code
        )
    except Exception as e:
        logging.error(f"Error generating content: {str(e)}")
        return create_error_response(500, "Internal server error")