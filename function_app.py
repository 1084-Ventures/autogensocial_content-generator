import azure.functions as func
from blueprints.text_generation import scheduler_blueprint, text_generation_blueprint
from blueprints.posting.posting_blueprint import posting_blueprint
from blueprints.scheduling.scheduling_blueprint import scheduling_blueprint
from blueprints.image_generation.image_generation_blueprint import image_generation_blueprint
from blueprints.orchestrator_blueprint import orchestrator_blueprint

app = func.FunctionApp()

# Register blueprints
app.register_blueprint(text_generation_blueprint)
app.register_blueprint(scheduler_blueprint)
app.register_blueprint(posting_blueprint)
app.register_blueprint(scheduling_blueprint)
app.register_blueprint(image_generation_blueprint)
app.register_blueprint(orchestrator_blueprint)

