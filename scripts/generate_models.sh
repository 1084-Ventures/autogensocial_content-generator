#!/bin/bash
# Generate Python models directly from generated_openapi.yaml

datamodel-codegen \
  --input ../specs/generated_openapi.yaml \
  --input-file-type openapi \
  --output generated_models/models.py \
  --output-model-type pydantic_v2.BaseModel \
  --snake-case-field \
  --use-standard-collections \
  --field-constraints
