import azure.functions as func
from blueprints.text_generation.text_generation_blueprint import text_generation_blueprint
from blueprints.orchestrator_blueprint import orchestrator_blueprint

app = func.FunctionApp()

# Register blueprints
app.register_blueprint(text_generation_blueprint)
app.register_blueprint(orchestrator_blueprint)

