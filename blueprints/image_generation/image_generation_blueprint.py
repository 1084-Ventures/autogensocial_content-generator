import azure.functions as func
from azure.functions import Blueprint
import json
from playwright.sync_api import sync_playwright

image_generation_blueprint = Blueprint()

# Example HTTP trigger for image generation (stub)
@image_generation_blueprint.route(route="generate-image", methods=["POST"])
def generate_image(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        text = data.get("text", "")
        visual_style = data.get("visualStyle", {})
        image_layout = data.get("imageLayout", {})
        width = image_layout.get("width", 800)
        height = image_layout.get("height", 600)
        font_family = visual_style.get("fontFamily", "Arial, sans-serif")
        font_size = visual_style.get("fontSize", "32px")
        text_color = visual_style.get("textColor", "#000000")
        bg_color = visual_style.get("backgroundColor", "#FFFFFF")

        # Build HTML dynamically
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    width: {width}px;
                    height: {height}px;
                    margin: 0;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: {bg_color};
                }}
                .content {{
                    font-family: {font_family};
                    font-size: {font_size};
                    color: {text_color};
                    text-align: center;
                    width: 90%;
                    word-break: break-word;
                }}
            </style>
        </head>
        <body>
            <div class='content'>{text}</div>
        </body>
        </html>
        """

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_content(html_content)
            image_bytes = page.screenshot(type="png", full_page=True)
            browser.close()

        return func.HttpResponse(body=image_bytes, mimetype="image/png", status_code=200)
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
