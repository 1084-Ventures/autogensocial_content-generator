import azure.functions as func
from blueprints.text_generation.text_generation_blueprint import text_generation_blueprint
from blueprints.orchestrator_blueprint import orchestrator_blueprint
from blueprints.image_generation.image_generation_blueprint import image_generation_blueprint
from blueprints.posting.posting_blueprint import posting_blueprint

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Register blueprints
app.register_blueprint(text_generation_blueprint)
app.register_blueprint(orchestrator_blueprint)
app.register_blueprint(image_generation_blueprint)
app.register_blueprint(posting_blueprint)

