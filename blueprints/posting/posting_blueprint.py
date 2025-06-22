import os
import json
import requests
import azure.functions as func
from azure.cosmos import CosmosClient
from azure.functions import Blueprint
from shared.logger import structured_logger
from generated_models.models import PostingRequest, PostingResponse

posting_blueprint = Blueprint()

# Example HTTP trigger for posting (stub)
@posting_blueprint.route(route="post-content", methods=["POST"])
def post_content(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        posting_request = PostingRequest(**data)
        brand_id = posting_request.brand_id
        image_url = posting_request.image_url
        content = posting_request.content
        post_id = posting_request.post_id

        # Cosmos DB setup
        cosmos_url = os.environ["COSMOS_DB_CONNECTION_STRING"]
        db_name = os.environ["COSMOS_DB_NAME"]
        container_brands = os.environ.get("COSMOS_DB_CONTAINER_BRAND", "brands")
        client = CosmosClient.from_connection_string(cosmos_url)
        db = client.get_database_client(db_name)
        brands_container = db.get_container_client(container_brands)

        # Fetch Instagram access token
        try:
            brand_db = brands_container.read_item(item=brand_id, partition_key=brand_id)
            instagram_account = brand_db.get("socialAccounts", {}).get("instagram", {})
            access_token = instagram_account.get("accessToken")
            instagram_username = instagram_account.get("username")
        except Exception as e:
            structured_logger.error("Brand/Instagram account not found", error=str(e), brand_id=brand_id)
            return func.HttpResponse(json.dumps({"error": "Instagram account not found"}), status_code=404, mimetype="application/json")

        # Prepare Instagram post if access token is available
        instagram_post_result = None
        post_status = "failed"
        instagram_post_id = None
        if access_token and image_url:
            try:
                # Compose the comment with hashtags appended
                comment = ""
                hashtags = []
                if isinstance(content, dict):
                    comment = content.get("comment", "")
                    hashtags = content.get("hashtags", [])
                hashtags_str = " ".join(hashtags) if hashtags else ""
                full_caption = f"{comment} {hashtags_str}".strip()

                # Instagram Graph API: Step 1 - Create Media Object
                create_media_url = f"https://graph.facebook.com/v22.0/{instagram_username}/media"
                payload = {
                    "image_url": image_url,
                    "caption": full_caption,
                    "access_token": access_token
                }
                structured_logger.info(
                    "Instagram media creation request",
                    url=create_media_url,
                    payload=payload
                )
                media_resp = requests.post(create_media_url, data=payload)
                media_json = media_resp.json()
                structured_logger.info(
                    "Instagram media creation response",
                    status_code=media_resp.status_code,
                    response=media_json
                )
                if "id" in media_json:
                    creation_id = media_json["id"]
                    # Step 2 - Publish Media
                    publish_url = f"https://graph.facebook.com/v22.0/{instagram_username}/media_publish"
                    publish_payload = {
                        "creation_id": creation_id,
                        "access_token": access_token
                    }
                    structured_logger.info(
                        "Instagram media publish request",
                        url=publish_url,
                        payload=publish_payload
                    )
                    publish_resp = requests.post(publish_url, data=publish_payload)
                    publish_json = publish_resp.json()
                    structured_logger.info(
                        "Instagram media publish response",
                        status_code=publish_resp.status_code,
                        response=publish_json
                    )
                    instagram_post_result = publish_json
                    if "id" in publish_json:
                        instagram_post_id = publish_json["id"]
                        post_status = "posted"
                    else:
                        post_status = "failed"
                else:
                    structured_logger.error(
                        "Instagram media creation failed",
                        response=media_json,
                        request_url=create_media_url,
                        request_payload=payload
                    )
                    instagram_post_result = media_json
            except Exception as e:
                structured_logger.error(
                    "Instagram posting error",
                    error=str(e),
                    request_url=create_media_url if 'create_media_url' in locals() else None,
                    request_payload=payload if 'payload' in locals() else None
                )
                instagram_post_result = {"error": str(e)}
                post_status = "failed"

        result = {
            "instagramResult": instagram_post_result,
            "instagramPostId": instagram_post_id,
            "postStatus": post_status
        }
        response_model = PostingResponse(status=post_status, post_url=instagram_post_id, error=instagram_post_result.get("error") if isinstance(instagram_post_result, dict) else None)
        return func.HttpResponse(response_model.model_dump_json(), status_code=200, mimetype="application/json")
    except Exception as e:
        structured_logger.error("Posting blueprint error", error=str(e))
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
