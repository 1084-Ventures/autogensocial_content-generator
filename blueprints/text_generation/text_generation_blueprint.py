import os
import openai
import json
import azure.functions as func
from azure.functions import Blueprint
from generated_models.models import GenerateTextContentRequest, GenerateTextContentResponse

text_generation_blueprint = Blueprint()

@text_generation_blueprint.route(route="generate-text-content", methods=["POST"])
def generate_text_content(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        text_content_request = GenerateTextContentRequest(**data)
        content = generate_text_content_logic(text_content_request.template, text_content_request.variable_values or {})
        return func.HttpResponse(json.dumps(content), status_code=200, mimetype="application/json")
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")

def generate_text_content_logic(template: dict, variable_values: dict) -> dict:
    """
    Calls Azure OpenAI to generate content based on the template and variable values.
    Returns a dict with keys: text, comment, hashtags.
    """
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")

    prompt_template = template["settings"]["prompt_template"]
    system_prompt = prompt_template["system_prompt"]
    user_prompt = prompt_template["user_prompt"]
    model = prompt_template["model"]
    temperature = prompt_template.get("temperature", 1)
    max_tokens = prompt_template.get("max_tokens", 512)

    # Render user/system prompt with variable values
    for k, v in variable_values.items():
        user_prompt = user_prompt.replace(f"{{{{{k}}}}}", str(v))
        system_prompt = system_prompt.replace(f"{{{{{k}}}}}", str(v))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Use OpenAI v1+ Azure client
    client = openai.AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens
    )
    content_json = response.choices[0].message.content
    try:
        content = json.loads(content_json)
    except Exception:
        content = {"text": content_json, "comment": "", "hashtags": []}
    return content
