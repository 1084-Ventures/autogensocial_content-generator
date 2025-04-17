import json
import os
from azure.cosmos import CosmosClient, exceptions as cosmos_exceptions
import openai
import logging
import uuid
from datetime import datetime, timezone
import pytz
from typing import Dict, Any, Tuple, List, Optional
from shared import structured_logger  # Add import for structured_logger

VALID_CONTENT_TYPES = ['post', 'reel', 'carousel', 'story']

_cosmos_client: Optional[CosmosClient] = None

def _normalize_content_type(content_type: str) -> str:
    """Normalize content type to lowercase."""
    return content_type.lower() if content_type else ''

# Load settings from local.settings.json
def load_settings():
    with open('local.settings.json') as f:
        settings = json.load(f)
        return settings.get('Values', {})

# Get settings once at module level
settings = load_settings()

def get_current_time_in_timezone(tz_str: str) -> datetime:
    """Get current time in specified timezone."""
    try:
        tz = pytz.timezone(tz_str) if tz_str else timezone.utc
        utc_now = datetime.now(timezone.utc)
        return utc_now.astimezone(tz)
    except pytz.exceptions.UnknownTimeZoneError:
        logging.error(f"Unknown timezone: {tz_str}, falling back to UTC")
        return datetime.now(timezone.utc)

def is_time_matching(template_slot: Dict[str, Any], current_time: datetime) -> bool:
    """Check if current time matches the template's time slot."""
    return (template_slot['hour'] == current_time.hour and 
            template_slot['minute'] == current_time.minute)

def get_todays_post_count(posts_container, brand_id: str, template_id: str) -> int:
    """Get count of posts generated today for a template."""
    today = datetime.now(timezone.utc).date()
    
    query = """
    SELECT COUNT(1) as count
    FROM c
    WHERE c.brandId = @brandId
    AND c.templateId = @templateId
    AND STARTSWITH(c.metadata.createdDate, @today)
    """
    
    parameters = [
        {"name": "@brandId", "value": brand_id},
        {"name": "@templateId", "value": template_id},
        {"name": "@today", "value": today.isoformat()}
    ]
    
    result = list(posts_container.query_items(
        query=query,
        parameters=parameters,
        enable_cross_partition_query=True
    ))
    return result[0]['count'] if result else 0

def generate_content_with_retry(prompt_settings: Dict[str, Any], system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Generate content using OpenAI with retry logic."""
    try:
        # Set OpenAI key from settings
        openai.api_key = settings.get('OPENAI_API_KEY')
        
        # Ensure max_tokens is sufficient for carousel content
        max_tokens = prompt_settings.get('maxTokens', 1000)
        if 'carousel' in user_prompt.lower():
            max_tokens = max(1500, max_tokens)  # Use at least 1500 tokens for carousel content
        
        structured_logger.info(
            "Sending request to OpenAI",
            model=prompt_settings.get('model', "gpt-4o"),
            max_tokens=max_tokens,
            temperature=prompt_settings.get('temperature', 0.7),
            system_prompt_length=len(system_prompt),
            user_prompt_length=len(user_prompt)
        )
        
        response = openai.chat.completions.create(
            model=prompt_settings.get('model', "gpt-4o"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=prompt_settings.get('temperature', 0.7),
            response_format={ "type": "json_object" }
        )

        content = response.choices[0].message.content
        structured_logger.info(
            "Received response from OpenAI",
            response_length=len(content) if content else 0,
            raw_response=content
        )

        # Try to parse the JSON response
        try:
            parsed_content = json.loads(content) if isinstance(content, str) else content
            structured_logger.info(
                "Successfully parsed OpenAI response as JSON",
                content_keys=list(parsed_content.keys()) if parsed_content else None
            )
            return parsed_content
        except json.JSONDecodeError as e:
            structured_logger.error(
                "Failed to parse OpenAI response as JSON",
                error=str(e),
                error_location=f"line {e.lineno}, column {e.colno}",
                raw_response=content,
                doc=content[max(0, e.pos-50):e.pos+50] if content and e.pos else None
            )
            raise

    except openai.APIError as e:
        structured_logger.error(
            "OpenAI API error",
            error=str(e),
            error_type=type(e).__name__
        )
        raise
    except Exception as e:
        structured_logger.error(
            "Unexpected error in content generation",
            error=str(e),
            error_type=type(e).__name__
        )
        raise

def validate_request(req_body: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate the request body against the API schema."""
    if not req_body.get('brandId'):
        return False, "brandId is required"
    if not req_body.get('templateId'):
        return False, "templateId is required"
    if not isinstance(req_body.get('variableValues', {}), dict):
        return False, "variableValues must be an object"
    return True, None

def init_cosmos_client() -> CosmosClient:
    """Initialize and return a Cosmos DB client."""
    global _cosmos_client
    if (_cosmos_client is None):
        try:
            conn_str = settings.get('COSMOS_DB_CONNECTION_STRING')
            if not conn_str:
                raise ValueError("COSMOS_DB_CONNECTION_STRING not found in settings")
                
            _cosmos_client = CosmosClient.from_connection_string(conn_str)
            
            # Verify connection by accessing the database
            db_name = settings.get('COSMOS_DB_NAME')
            _cosmos_client.get_database_client(db_name).read()
            
            structured_logger.info("Successfully connected to Cosmos DB")
        except Exception as e:
            structured_logger.error(f"Failed to initialize Cosmos DB client: {str(e)}")
            raise
    return _cosmos_client

def generate_content(req_body: Dict[str, Any], is_timer: bool = False) -> Tuple[Any, int, str]:
    """Core content generation logic used by both HTTP and timer triggers."""
    try:
        brand_id = req_body['brandId']
        template_id = req_body['templateId']
        variable_values = req_body.get('variableValues', {})

        # Initialize Cosmos DB client using settings
        cosmos_client = init_cosmos_client()
        database = cosmos_client.get_database_client(settings.get('COSMOS_DB_NAME'))
        
        # Get container clients using settings
        brands_container = database.get_container_client(settings.get('COSMOS_DB_CONTAINER_BRAND'))
        templates_container = database.get_container_client(settings.get('COSMOS_DB_CONTAINER_TEMPLATE'))
        posts_container = database.get_container_client(settings.get('COSMOS_DB_CONTAINER_POSTS'))

        try:
            # Get brand details
            brands = list(brands_container.query_items(
                query="SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": brand_id}],
                enable_cross_partition_query=True
            ))
            if not brands:
                return None, 404, f"Brand with ID {brand_id} not found"
            brand = brands[0]

            # Get template details
            templates = list(templates_container.query_items(
                query="SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": template_id}],
                enable_cross_partition_query=True
            ))
            if not templates:
                return None, 404, f"Template with ID {template_id} not found"
            template = templates[0]

            # Validate required fields
            if not all(key in template for key in ['templateInfo', 'settings']):
                return None, 500, "Template is missing required fields"

            template_info = template['templateInfo']
            template_settings = template['settings']

            # Validate required template settings
            if not all(key in template_settings for key in ['promptTemplate', 'visualStyle', 'contentStrategy']):
                return None, 400, "Template settings must include promptTemplate, visualStyle, and contentStrategy"

            # Validate prompt template settings
            prompt_settings = template_settings['promptTemplate']
            if not all(key in prompt_settings for key in ['systemPrompt', 'userPrompt']):
                return None, 400, "Template promptTemplate must include systemPrompt and userPrompt"

            system_prompt = prompt_settings['systemPrompt']
            user_prompt = prompt_settings['userPrompt']

            if not system_prompt.strip() or not user_prompt.strip():
                return None, 400, "System prompt and user prompt cannot be empty"

            # Process variables in the prompts
            if 'variables' in prompt_settings:
                if not isinstance(prompt_settings['variables'], list):
                    return None, 400, "Template variables must be an array"
                
                for variable in prompt_settings['variables']:
                    if not isinstance(variable, dict):
                        structured_logger.warning(
                            "Invalid variable format in template",
                            template_id=template_id,
                            variable=variable
                        )
                        continue
                    
                    var_name = variable.get('name')
                    if not var_name:
                        continue

                    # Check if variable is required in either prompt
                    var_placeholder = f"{{{var_name}}}"
                    is_in_system = var_placeholder in system_prompt
                    is_in_user = var_placeholder in user_prompt

                    if (is_in_system or is_in_user) and var_name not in variable_values:
                        return None, 400, f"Missing required variable: {var_name}"
                    
                    if var_name in variable_values:
                        var_value = str(variable_values[var_name])
                        system_prompt = system_prompt.replace(var_placeholder, var_value)
                        user_prompt = user_prompt.replace(var_placeholder, var_value)

            # Prepare the complete system prompt with brand and content strategy context
            brand_info = brand.get('brandInfo', {})
            content_strategy = template_settings.get('contentStrategy', {})
            
            complete_system_prompt = f"""
            You are a professional content creator generating content in JSON format.
            
            Brand Context:
            - Name: {brand_info.get('name', '')}
            - Description: {brand_info.get('description', '')}
            
            Content Strategy:
            - Target Audience: {content_strategy.get('targetAudience', '')}
            - Tone: {content_strategy.get('tone', '')}
            - Keywords: {', '.join(content_strategy.get('keywords', []))}
            - Hashtag Strategy: {content_strategy.get('hashtagStrategy', '')}
            - Call to Action: {content_strategy.get('callToAction', '')}

            {system_prompt}

            Respond with a JSON object containing the generated content. Include:
            - mainText: The primary content text
            - caption: A social media caption
            - hashtags: Array of relevant hashtags
            - callToAction: The call to action text
            """

            # Generate content using OpenAI with validated settings
            try:
                model = prompt_settings.get('model', "gpt-4")
                max_tokens = prompt_settings.get('maxTokens', 1000)
                temperature = prompt_settings.get('temperature', 0.7)
                
                logging.info(
                    "Generating content with settings",
                    extra={
                        "model": model,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "template_id": template_id
                    }
                )

                generated_content = generate_content_with_retry(
                    {
                        "model": model,
                        "maxTokens": max_tokens,
                        "temperature": temperature
                    },
                    complete_system_prompt,
                    user_prompt
                )
            except openai.APIError as e:
                logging.error(f"OpenAI API error: {str(e)}", extra={"template_id": template_id})
                return None, 500, "Error generating content with AI model"

            # Create metadata following the spec
            current_time = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            metadata = {
                "createdDate": current_time,
                "updatedDate": current_time,
                "isActive": True
            }

            # Save generated content to posts container
            new_post = {
                "id": str(uuid.uuid4()),
                "metadata": metadata,
                "brandId": brand_id,
                "templateId": template_id,
                "content": generated_content,
                "status": "draft",
                "contentType": _normalize_content_type(template_info.get('contentType')),
                "variableValues": variable_values,
                "generatedBy": "timer" if is_timer else "api"
            }
            
            try:
                created_post = posts_container.create_item(body=new_post)
                return created_post, 201, None
            except cosmos_exceptions.CosmosHttpResponseError as e:
                logging.error(f"Cosmos DB error: {str(e)}", extra={"template_id": template_id})
                return None, 500, "Error saving generated content"

        except IndexError:
            return None, 404, f"Resource not found"

    except Exception as e:
        logging.error(f"Error generating content: {str(e)}")
        return None, 500, "An unexpected error occurred"