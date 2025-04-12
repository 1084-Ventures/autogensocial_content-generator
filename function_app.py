import azure.functions as func
from blueprints.content_generation import http_blueprint, scheduler_blueprint

app = func.FunctionApp()

# Register blueprints
app.register_blueprint(http_blueprint)
app.register_blueprint(scheduler_blueprint)
