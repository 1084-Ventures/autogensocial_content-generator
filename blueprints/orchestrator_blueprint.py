import azure.functions as func
from azure.functions.decorators import Blueprint
import os
import json
from azure.cosmos import CosmosClient
from datetime import datetime
from blueprints.azure_openai_content_generation.azure_openai_content_generation_blueprint import generate_text_content_logic
from shared.logger import structured_logger
import random
import requests
from azure.storage.blob import BlobServiceClient, ContentSettings
import uuid
from generated_models.models import OrchestratorRequest, OrchestratorResponse

orchestrator_blueprint = Blueprint()

@orchestrator_blueprint.route(route="generate-content-orchestrator", methods=["POST"])
def generate_content_orchestrator(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        orchestrator_request = OrchestratorRequest(**data)
        template_id = orchestrator_request.template_id
        variable_values = orchestrator_request.variable_values or {}
        brand_id = orchestrator_request.brand_id
        user_id = req.headers.get("X-API-Key", "anonymous")

        # Cosmos DB setup
        cosmos_url = os.environ["COSMOS_DB_CONNECTION_STRING"]
        db_name = os.environ["COSMOS_DB_NAME"]
        container_templates = os.environ.get("COSMOS_DB_CONTAINER_TEMPLATES", "templates")
        container_posts = os.environ["COSMOS_DB_CONTAINER_POSTS"]
        client = CosmosClient.from_connection_string(cosmos_url)
        db = client.get_database_client(db_name)
        templates_container = db.get_container_client(container_templates)
        posts_container = db.get_container_client(container_posts)

        # Debug: List all template IDs for this brandId (partition key)
        try:
            query = "SELECT c.id, c.templateInfo.brandId FROM c WHERE c.templateInfo.brandId = @brandId"
            items = list(templates_container.query_items(
                query=query,
                parameters=[{"name": "@brandId", "value": brand_id}],
                enable_cross_partition_query=True
            ))
            template_ids = [item["id"] for item in items]
            structured_logger.info("Templates found for brandId", brand_id=brand_id, template_ids=template_ids)
        except Exception as debug_e:
            structured_logger.error("Debug query failed", error=str(debug_e), brand_id=brand_id)

        # Fetch template from Cosmos DB (partition key is templateInfo.brandId)
        try:
            template_db = templates_container.read_item(item=template_id, partition_key=brand_id)
        except Exception as e:
            structured_logger.error("Template not found", error=str(e), template_id=template_id)
            return func.HttpResponse(json.dumps({"error": f"Template with id {template_id} not found."}), status_code=404, mimetype="application/json")

        # Extract only the required fields for text generation
        settings = template_db.get("settings", {})
        prompt_template = settings.get("prompt_template", {})
        variable_values_random = {}
        # Randomly select one value for each variable, if variables exist
        variables = prompt_template.pop("variables", None)
        if variables:
            for var in variables:
                name = var.get("name")
                values = var.get("values", [])
                if name and values:
                    variable_values_random[name] = random.choice(values)
        template = {
            "settings": settings
        }
        # Use the randomly selected variable values if present
        content = generate_text_content_logic(template, variable_values_random or variable_values)

        # --- Media Search Integration for Images ---
        visual_style = settings.get("visualStyle", {})
        content_type = template_db.get("templateInfo", {}).get("contentType", "text")
        image_url_for_generation = None
        if content_type == "image":
            # Try to get a relevant image from media_search
            try:
                api_base_url = os.environ.get("API_BASE_URL", "http://localhost:7071/api")
                media_search_url = f"{api_base_url}/media-search"
                # Use the text content as the search query
                search_query = content["text"] if isinstance(content, dict) and "text" in content else str(content)
                resp = requests.post(media_search_url, json={"query": search_query, "brandId": brand_id})
                if resp.status_code == 200:
                    media_result = resp.json()
                    # Assume media_result["url"] is the best image URL
                    image_url_for_generation = media_result.get("url")
            except Exception as e:
                structured_logger.error("Media search failed", error=str(e))

        # --- Image Generation ---
        # If visualStyle has a 'themes' array, pick a random theme
        if (
            isinstance(visual_style, dict)
            and "themes" in visual_style
            and isinstance(visual_style["themes"], list)
            and visual_style["themes"]
        ):
            visual_style = random.choice(visual_style["themes"])
        image = settings.get("image", {})
        api_base_url = os.environ.get("API_BASE_URL", "http://localhost:7071/api")
        image_gen_url = f"{api_base_url}/generate-image"
        # Only pass the 'text' field to the image generator, handling both 'text' and 'Text' keys
        image_text = None
        if isinstance(content, dict):
            if "text" in content:
                image_text = content["text"]
            elif "Text" in content:
                image_text = content["Text"]
            else:
                image_text = str(content)
        else:
            image_text = str(content)
        box_text = settings.get("boxText", "")
        text_box = settings.get("textBox", {})
        image_payload = {
            "text": image_text,
            "visualStyle": visual_style,
            "image": image,
            "boxText": box_text,
            "textBox": text_box
        }
        # If we have a media_search image, add it to the payload
        if image_url_for_generation:
            image_payload["mediaUrl"] = image_url_for_generation
        image_bytes = None
        post_id = str(uuid.uuid4())  # Ensure post_id is always set
        try:
            resp = requests.post(image_gen_url, json=image_payload)
            if resp.status_code == 200:
                image_bytes = resp.content
            else:
                structured_logger.error("Image generation failed", status_code=resp.status_code, response=resp.text)
        except Exception as e:
            structured_logger.error("Image generation request error", error=str(e))

        # Upload image to Azure Blob Storage if generated
        image_url = None
        if image_bytes:
            try:
                blob_conn_str = os.environ.get("PUBLIC_BLOB_CONNECTION_STRING")
                blob_service_client = BlobServiceClient.from_connection_string(blob_conn_str)
                container_name = "public-images"
                try:
                    blob_service_client.create_container(container_name)
                except Exception:
                    pass  # Container may already exist
                blob_path = f"{user_id}/{brand_id}/{template_id}/{post_id}.png"
                blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
                blob_client.upload_blob(image_bytes, overwrite=True, content_settings=ContentSettings(content_type="image/png"))
                account_url = blob_service_client.url.rstrip('/')
                container_name_clean = container_name.strip('/')
                blob_path_clean = blob_path.lstrip('/')
                image_url = f"{account_url}/{container_name_clean}/{blob_path_clean}"
            except Exception as e:
                structured_logger.error("Blob upload failed", error=str(e))
                image_url = None

        # Write to Cosmos DB (posts container)
        post_doc = {
            "id": post_id,
            "brandId": brand_id,
            "templateId": template_id,
            "content": content,
            "createdAt": datetime.utcnow().isoformat(),
            "metadata": {
                "createdDate": datetime.utcnow().isoformat(),
                "updatedDate": datetime.utcnow().isoformat(),
                "isActive": True
            },
            "imageUrl": image_url
        }
        posts_container.create_item(post_doc)
        structured_logger.info("Content written to Cosmos DB", post_id=post_id)

        # --- Instagram Posting Logic moved to posting_blueprint ---
        instagram_post_result = None
        instagram_post_id = None
        post_status = None
        try:
            posting_url = f"{api_base_url}/post-content"
            post_payload = {
                "brandId": brand_id,
                "imageUrl": image_url,
                "content": content,
                "postId": post_id
            }
            resp = requests.post(posting_url, json=post_payload)
            if resp.status_code == 200:
                post_result = resp.json()
                instagram_post_result = post_result.get("instagramResult")
                instagram_post_id = post_result.get("instagramPostId")
                post_status = post_result.get("postStatus")
            else:
                structured_logger.error(
                    "Posting blueprint failed",
                    status_code=resp.status_code,
                    response=resp.text,
                    request_url=posting_url,
                    request_payload=post_payload
                )
        except Exception as e:
            structured_logger.error(
                "Posting blueprint request error",
                error=str(e),
                request_url=posting_url if 'posting_url' in locals() else None,
                request_payload=post_payload if 'post_payload' in locals() else None
            )

        # Update post item in posts container with Instagram post id and status
        try:
            if instagram_post_id or post_status:
                post_doc_update = posts_container.read_item(item=post_id, partition_key=post_id)
                post_doc_update["instagramPostId"] = instagram_post_id
                post_doc_update["postStatus"] = post_status
                posts_container.replace_item(item=post_id, body=post_doc_update)
        except Exception as e:
            structured_logger.error("Failed to update post with Instagram info", error=str(e))

        # Add Instagram post result to response
        response_body = {"id": post_id, "content": content, "imageUrl": image_url}
        if instagram_post_result:
            response_body["instagramResult"] = instagram_post_result
        if instagram_post_id:
            response_body["instagramPostId"] = instagram_post_id
        if post_status:
            response_body["postStatus"] = post_status
        if image_url_for_generation:
            response_body["mediaSearchImageUrl"] = image_url_for_generation

        # Use OrchestratorResponse for serialization
        response_model = OrchestratorResponse(status="success", result=response_body)
        return func.HttpResponse(response_model.model_dump_json(), status_code=201, mimetype="application/json")
    except Exception as e:
        structured_logger.error("Orchestrator error", error=str(e))
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
