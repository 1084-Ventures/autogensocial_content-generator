import azure.functions as func
from blueprints.generate_content import blueprint as generate_content_blueprint
from blueprints.consolidate_brand_template import blueprint as consolidate_blueprint

app = func.FunctionApp()

# Register blueprints
app.register_blueprint(generate_content_blueprint)
app.register_blueprint(consolidate_blueprint)
