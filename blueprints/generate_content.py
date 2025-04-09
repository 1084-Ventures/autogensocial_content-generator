import azure.functions as func
from azure.functions import Blueprint, HttpRequest, HttpResponse
import json
import os
from azure.cosmos import CosmosClient
import openai
import logging
import uuid

# Initialize Blueprint
blueprint = Blueprint()

@blueprint.route(route="generate", methods=["POST"])
def generate_content(req: HttpRequest) -> HttpResponse:
    try:
        # Get request body
        req_body = req.get_json()
        brand_id = req_body.get('brandId')
        template_id = req_body.get('templateId')

        if not brand_id or not template_id:
            return func.HttpResponse(
                body=json.dumps({"error": "Please provide both brandId and templateId"}),
                mimetype="application/json",
                status_code=400
            )

        # Initialize Cosmos DB client
        cosmos_client = CosmosClient.from_connection_string(
            os.environ["COSMOS_DB_CONNECTION_STRING"]
        )
        database = cosmos_client.get_database_client(os.environ["COSMOS_DB_NAME"])
        
        # Get brand and template data
        brands_container = database.get_container_client(os.environ["COSMOS_DB_CONTAINER_BRAND"])
        templates_container = database.get_container_client(os.environ["COSMOS_DB_CONTAINER_TEMPLATE"])

        brand = list(brands_container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": brand_id}],
            enable_cross_partition_query=True
        ))[0]

        template = list(templates_container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": template_id}],
            enable_cross_partition_query=True
        ))[0]

        # Initialize OpenAI client
        openai.api_key = os.environ["OPENAI_API_KEY"]

        # Prepare prompt
        prompt = f"""
        Brand Context:
        Name: {brand.get('name')}
        Voice: {brand.get('voice')}
        Industry: {brand.get('industry')}
        
        Template:
        {template.get('content')}
        
        Generate content following the template while maintaining the brand voice and context.
        """

        logging.info(f"Sending prompt to OpenAI: {prompt}")

        # Generate content using OpenAI
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional content creator."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )

        generated_content = response.choices[0].message.content
        logging.info(f"Received response from OpenAI: {generated_content}")
        logging.info(f"OpenAI response metadata: model={response.model}, "
                    f"finish_reason={response.choices[0].finish_reason}, "
                    f"total_tokens={response.usage.total_tokens}")

        # Save generated content to posts container
        posts_container = database.get_container_client(os.environ["COSMOS_DB_CONTAINER_POSTS"])
        new_post = {
            "id": str(uuid.uuid4()),  # Add unique ID
            "brandId": brand_id,
            "templateId": template_id,
            "content": generated_content,
            "status": "draft"
        }
        
        created_post = posts_container.create_item(body=new_post)

        return func.HttpResponse(
            body=json.dumps({"post": created_post}),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"Error generating content: {str(e)}")
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            mimetype="application/json",
            status_code=500
        )