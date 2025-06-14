#!/bin/bash
# Bundle OpenAPI spec and generate Python models

# 1. Bundle OpenAPI spec
swagger-cli bundle ../specs/openapi.yaml --outfile bundled_openapi.yaml --type yaml

# 2. Generate Python models from bundled spec
datamodel-codegen \
  --input bundled_openapi.yaml \
  --input-file-type openapi \
  --output generated_models/models.py \
  --output-model-type pydantic_v2.BaseModel \
  --snake-case-field \
  --use-standard-collections \
  --field-constraints
