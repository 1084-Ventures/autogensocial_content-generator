import azure.functions as func
from azure.functions.decorators import Blueprint
import os
import json
from azure.cosmos import CosmosClient
from datetime import datetime
from blueprints.text_generation.text_generation_blueprint import generate_text_content_logic
from shared.logger import structured_logger
import random
import requests
from azure.storage.blob import BlobServiceClient, ContentSettings
import uuid

orchestrator_blueprint = Blueprint()

@orchestrator_blueprint.route(route="generate-content-orchestrator", methods=["POST"])
def generate_content_orchestrator(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        template_id = data.get("templateId")
        variable_values = data.get("variableValues", {})
        brand_id = data.get("brandId")
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

        # Fetch template from Cosmos DB
        try:
            template_db = templates_container.read_item(item=template_id, partition_key=template_id)
        except Exception as e:
            structured_logger.error("Template not found", error=str(e), template_id=template_id)
            return func.HttpResponse(json.dumps({"error": f"Template with id {template_id} not found."}), status_code=404, mimetype="application/json")

        # Extract only the required fields for text generation
        settings = template_db.get("settings", {})
        prompt_template = settings.get("promptTemplate", {})
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

        # Generate image using image_generation endpoint
        visual_style = settings.get("visualStyle", {})
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
        # Add boxText for Pillow-based image generation
        box_text = settings.get("boxText", "")
        # --- Advanced image generation payload ---
        # Add support for textBox and pass all advanced options to image generator
        text_box = settings.get("textBox", {})
        image_payload = {
            "text": image_text,
            "visualStyle": visual_style,
            "image": image,
            "boxText": box_text,
            "textBox": text_box
        }
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
                # Use PUBLIC_BLOB_CONNECTION_STRING for public images
                blob_conn_str = os.environ.get("PUBLIC_BLOB_CONNECTION_STRING")
                blob_service_client = BlobServiceClient.from_connection_string(blob_conn_str)
                container_name = "public-images"
                # Create container if not exists (no public access)
                try:
                    blob_service_client.create_container(container_name)
                except Exception:
                    pass  # Container may already exist
                blob_path = f"{user_id}/{brand_id}/{template_id}/{post_id}.png"
                blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_path)
                blob_client.upload_blob(image_bytes, overwrite=True, content_settings=ContentSettings(content_type="image/png"))
                # Build blob URL
                account_url = blob_service_client.url.rstrip('/')
                container_name_clean = container_name.strip('/')
                blob_path_clean = blob_path.lstrip('/')
                image_url = f"{account_url}/{container_name_clean}/{blob_path_clean}"
            except Exception as e:
                structured_logger.error("Blob upload failed", error=str(e))
                image_url = None

        # Write to Cosmos DB (posts container)
        # Use the same UUID post_id as above
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
        # Call posting_blueprint endpoint to post to Instagram
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

        return func.HttpResponse(json.dumps(response_body), status_code=201, mimetype="application/json")
    except Exception as e:
        structured_logger.error("Orchestrator error", error=str(e))
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
