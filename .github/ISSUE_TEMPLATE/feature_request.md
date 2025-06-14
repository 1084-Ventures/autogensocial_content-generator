# .gitHub/ISSUE_TEMPLATE/feature_request.md
---
name: "Feature request"
description: "Suggest an idea for this project"
title: "[FEATURE] "
labels: [enhancement]
assignees: []
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to suggest a feature!
  - type: input
    id: feature-description
    attributes:
      label: Feature description
      description: What do you want to see added?
      placeholder: Describe the feature you want
    validations:
      required: true
  - type: textarea
    id: use-case
    attributes:
      label: Use case
      description: Why is this feature important? What problem does it solve?
      placeholder: Describe the use case
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
      description: Did you consider any alternatives?
      placeholder: List any alternatives
    validations:
      required: false
