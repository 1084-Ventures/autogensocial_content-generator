from azure.storage.blob import BlobServiceClient
from urllib.parse import urlparse, unquote
import io

def download_blob_to_bytes(blob_url, conn_str):
    parsed = urlparse(blob_url)
    path_parts = parsed.path.lstrip('/').split('/', 1)
    blob_container = path_parts[0]
    blob = unquote(path_parts[1])
    blob_service_client = BlobServiceClient.from_connection_string(conn_str)
    blob_client = blob_service_client.get_blob_client(container=blob_container, blob=blob)
    font_bytes = io.BytesIO()
    download_stream = blob_client.download_blob()
    font_bytes.write(download_stream.readall())
    font_bytes.seek(0)
    return font_bytes

def upload_bytes_to_blob(blob_bytes, blob_name, container_name, conn_str, content_type="image/png"):
    """
    Uploads bytes to Azure Blob Storage and returns the public URL.
    """
    blob_service_client = BlobServiceClient.from_connection_string(conn_str)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    blob_client.upload_blob(blob_bytes, overwrite=True, content_type=content_type)
    # Build public URL
    account_name = blob_service_client.account_name
    url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
    return url
