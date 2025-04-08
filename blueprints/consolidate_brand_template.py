import azure.functions as func
import json
from azure.cosmos import CosmosClient
import os
from datetime import datetime
import uuid
import logging

blueprint = func.Blueprint()

@blueprint.route(route="consolidate", methods=["POST"])
def consolidate_post(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        req_body = req.get_json()
        brand_id = req_body.get('brandId')
        template_id = req_body.get('templateId')

        if not brand_id or not template_id:
            return func.HttpResponse(
                "Please provide both brandId and templateId in the request body",
                status_code=400
            )

        # Initialize Cosmos DB client
        client = CosmosClient.from_connection_string(os.environ["COSMOS_DB_CONNECTION_STRING"])
        database = client.get_database_client(os.environ["COSMOS_DB_NAME"])
        
        # Get containers
        brands_container = database.get_container_client(os.environ["COSMOS_DB_CONTAINER_BRAND"])
        templates_container = database.get_container_client(os.environ["COSMOS_DB_CONTAINER_TEMPLATE"])
        posts_container = database.get_container_client(os.environ["COSMOS_DB_CONTAINER_POSTS"])

        # Fetch brand and template documents
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

        # Create new post document
        new_post = {
            "id": str(uuid.uuid4()),
            "metadata": {
                "createdDate": datetime.utcnow().isoformat() + "Z",
                "updatedDate": datetime.utcnow().isoformat() + "Z",
                "isActive": True,
                "brandId": brand_id,
                "templateId": template_id
            },
            "brandInfo": brand["brandInfo"],
            "socialAccounts": brand["socialAccounts"],
            "templateInfo": template["templateInfo"],
            "schedule": template["schedule"],
            "settings": template["settings"],
            "status": "PENDING",
            "content": None
        }

        # Create the post in Cosmos DB
        created_post = posts_container.create_item(body=new_post)

        return func.HttpResponse(
            json.dumps(created_post),
            mimetype="application/json",
            status_code=201
        )

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return func.HttpResponse(
            f"An error occurred: {str(e)}",
            status_code=500
        )
