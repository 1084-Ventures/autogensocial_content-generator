import azure.functions as func
from azure.functions.decorators import Blueprint
import os
import json
from azure.cosmos import CosmosClient
from shared.logger import structured_logger
from azure.storage.blob import BlobServiceClient
# If you have an AI model or service, import it here (e.g., OpenAI, Azure Cognitive Services)

media_search_blueprint = Blueprint()

@media_search_blueprint.route(route="media-search", methods=["POST"])
def media_search(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        text_content = data.get("text")
        source = data.get("source", "internal")  # Accept 'source' param, default to 'internal'
        if not text_content:
            return func.HttpResponse(json.dumps({"error": "Missing 'text' in request body."}), status_code=400, mimetype="application/json")

        if source == "online":
            # --- ONLINE IMAGE SEARCH (Bing Image Search API) ---
            # You must set BING_IMAGE_SEARCH_KEY in your environment variables
            subscription_key = os.environ.get("BING_IMAGE_SEARCH_KEY")
            if not subscription_key:
                return func.HttpResponse(json.dumps({"error": "Bing Image Search API key not configured."}), status_code=500, mimetype="application/json")
            search_url = "https://api.bing.microsoft.com/v7.0/images/search"
            headers = {"Ocp-Apim-Subscription-Key": subscription_key}
            params = {"q": text_content, "count": 10}
            import requests
            try:
                resp = requests.get(search_url, headers=headers, params=params)
                if resp.status_code == 200:
                    results = resp.json().get("value", [])
                    if not results:
                        return func.HttpResponse(json.dumps({"error": "No online images found."}), status_code=404, mimetype="application/json")
                    # Optionally, use AI to rank results here
                    best_match = results[0]
                    return func.HttpResponse(json.dumps({"media": best_match, "source": "online"}), status_code=200, mimetype="application/json")
                else:
                    return func.HttpResponse(json.dumps({"error": f"Bing Image Search failed: {resp.text}"}), status_code=resp.status_code, mimetype="application/json")
            except Exception as e:
                structured_logger.error("Online image search error", error=str(e))
                return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")

        if source == "uploaded":
            # --- UPLOADED MEDIA SEARCH (Cosmos DB) ---
            user_id = data.get("userId")
            brand_id = data.get("brandId")
            if not user_id or not brand_id:
                return func.HttpResponse(json.dumps({"error": "Missing 'userId' or 'brandId' in request body."}), status_code=400, mimetype="application/json")
            cosmos_url = os.environ["COSMOS_DB_CONNECTION_STRING"]
            db_name = os.environ["COSMOS_DB_NAME"]
            container_media = os.environ.get("COSMOS_DB_CONTAINER_MEDIA", "media")
            client = CosmosClient.from_connection_string(cosmos_url)
            db = client.get_database_client(db_name)
            media_container = db.get_container_client(container_media)
            # Search for media by userId, brandId, and text_content in fileName, description, or tags
            query = (
                "SELECT * FROM c WHERE c.userId = @userId AND c.brandId = @brandId "
                "AND (CONTAINS(c.metadata.fileName, @text) "
                "OR CONTAINS(c.metadata.description, @text) "
                "OR ARRAY_CONTAINS(c.metadata.tags, {\"name\": @text}, true))"
            )
            items = media_container.query_items(
                query=query,
                parameters=[
                    {"name": "@userId", "value": user_id},
                    {"name": "@brandId", "value": brand_id},
                    {"name": "@text", "value": text_content}
                ],
                enable_cross_partition_query=True
            )
            results = list(items)
            if not results:
                return func.HttpResponse(json.dumps({"error": "No uploaded media found."}), status_code=404, mimetype="application/json")
            best_match = results[0]
            return func.HttpResponse(json.dumps({"media": best_match, "source": "uploaded"}), status_code=200, mimetype="application/json")

        if source == "uploaded_llm":
            # --- UPLOADED MEDIA SEARCH WITH LLM RANKING (Cosmos DB + OpenAI) ---
            user_id = data.get("userId")
            brand_id = data.get("brandId")
            if not user_id or not brand_id:
                return func.HttpResponse(json.dumps({"error": "Missing 'userId' or 'brandId' in request body."}), status_code=400, mimetype="application/json")
            cosmos_url = os.environ["COSMOS_DB_CONNECTION_STRING"]
            db_name = os.environ["COSMOS_DB_NAME"]
            container_media = os.environ.get("COSMOS_DB_CONTAINER_MEDIA", "media")
            client = CosmosClient.from_connection_string(cosmos_url)
            db = client.get_database_client(db_name)
            media_container = db.get_container_client(container_media)
            # Get all media for user/brand
            query = (
                "SELECT c.id, c.metadata.fileName, c.metadata.tags, c.metadata.description FROM c "
                "WHERE c.userId = @userId AND c.brandId = @brandId"
            )
            items = media_container.query_items(
                query=query,
                parameters=[
                    {"name": "@userId", "value": user_id},
                    {"name": "@brandId", "value": brand_id}
                ],
                enable_cross_partition_query=True
            )
            media_list = list(items)
            if not media_list:
                return func.HttpResponse(json.dumps({"error": "No uploaded media found."}), status_code=404, mimetype="application/json")
            # Prepare prompt for LLM
            prompt = f"""Given the following content: \n{text_content}\n\nChoose the best matching media from the list below.\n\n"""
            for idx, media in enumerate(media_list, 1):
                tags = ', '.join([t['name'] for t in media.get('tags', [])]) if media.get('tags') else ''
                prompt += f"{idx}. id: {media.get('id')}, name: {media.get('fileName')}, tags: [{tags}], description: {media.get('description', '')}\n"
            prompt += "\nReturn the id of the best match and a short reason."
            # Call OpenAI (Azure) LLM
            import openai
            openai.api_type = "azure"
            openai.api_base = os.environ["AZURE_OPENAI_ENDPOINT"]
            openai.api_key = os.environ["AZURE_OPENAI_API_KEY"]
            openai.api_version = os.environ["AZURE_OPENAI_API_VERSION"]
            deployment = os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]
            try:
                response = openai.ChatCompletion.create(
                    engine=deployment,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that selects the best matching media for a given content."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=128,
                    temperature=0.2
                )
                answer = response["choices"][0]["message"]["content"]
                return func.HttpResponse(json.dumps({"llm_result": answer, "source": "uploaded_llm"}), status_code=200, mimetype="application/json")
            except Exception as e:
                structured_logger.error("LLM media ranking error", error=str(e))
                return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")

        # --- INTERNAL MEDIA SEARCH (Cosmos DB) ---
        # Cosmos DB setup for media metadata
        cosmos_url = os.environ["COSMOS_DB_CONNECTION_STRING"]
        db_name = os.environ["COSMOS_DB_NAME"]
        container_media = os.environ.get("COSMOS_DB_CONTAINER_MEDIA", "media")
        client = CosmosClient.from_connection_string(cosmos_url)
        db = client.get_database_client(db_name)
        media_container = db.get_container_client(container_media)

        # TODO: Use AI to extract keywords/tags from text_content
        # For now, just use the text as a keyword search
        query = "SELECT * FROM c WHERE CONTAINS(c.tags, @text) OR CONTAINS(c.description, @text)"
        items = media_container.query_items(
            query=query,
            parameters=[{"name": "@text", "value": text_content}],
            enable_cross_partition_query=True
        )
        results = list(items)

        # TODO: Use AI to rank/select the best image from results
        # For now, just pick the first result
        best_match = results[0] if results else None

        if not best_match:
            return func.HttpResponse(json.dumps({"error": "No matching media found."}), status_code=404, mimetype="application/json")

        return func.HttpResponse(json.dumps({"media": best_match, "source": source}), status_code=200, mimetype="application/json")
    except Exception as e:
        structured_logger.error("Media search error", error=str(e))
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
