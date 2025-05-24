import azure.functions as func
from azure.functions.decorators import Blueprint
import os
import json
from azure.cosmos import CosmosClient
from datetime import datetime
from blueprints.text_generation.text_generation_blueprint import generate_text_content
from shared.logger import structured_logger

orchestrator_blueprint = Blueprint()

@orchestrator_blueprint.route(route="generate-content-orchestrator", methods=["POST"])
def generate_content_orchestrator(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        template = data.get("template")
        variable_values = data.get("variableValues", {})
        brand_id = data.get("brandId")
        user_id = req.headers.get("X-API-Key", "anonymous")

        # Generate content using text_generation_blueprint
        content = generate_text_content(template, variable_values)

        # Write to Cosmos DB (posts container)
        cosmos_url = os.environ["COSMOS_DB_CONNECTION_STRING"]
        db_name = os.environ["COSMOS_DB_NAME"]
        container_name = os.environ["COSMOS_DB_CONTAINER_POSTS"]
        client = CosmosClient.from_connection_string(cosmos_url)
        db = client.get_database_client(db_name)
        container = db.get_container_client(container_name)

        post_id = f"post-{datetime.utcnow().isoformat()}"
        post_doc = {
            "id": post_id,
            "brandId": brand_id,
            "templateId": template.get("id"),
            "content": content,
            "createdAt": datetime.utcnow().isoformat(),
            "metadata": {
                "createdDate": datetime.utcnow().isoformat(),
                "updatedDate": datetime.utcnow().isoformat(),
                "isActive": True
            }
        }
        container.create_item(post_doc)
        structured_logger.info("Content written to Cosmos DB", post_id=post_id)
        return func.HttpResponse(json.dumps({"id": post_id, "content": content}), status_code=201, mimetype="application/json")
    except Exception as e:
        structured_logger.error("Orchestrator error", error=str(e))
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
