import azure.functions as func
from blueprints.content_generation import http_blueprint

app = func.FunctionApp()

# Register blueprints
app.register_blueprint(http_blueprint)

