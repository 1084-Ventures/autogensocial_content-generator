# .gitHub/ISSUE_TEMPLATE/bug_report.md
---
name: "Bug report"
description: "Create a report to help us improve"
title: "[BUG] "
labels: [bug]
assignees: []
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to fill out this bug report!
  - type: input
    id: what-happened
    attributes:
      label: What happened?
      description: Tell us what you see!
      placeholder: Tell us what you see!
    validations:
      required: true
  - type: input
    id: expected-behavior
    attributes:
      label: What did you expect to happen?
      description: Tell us what you expected!
      placeholder: Tell us what you expected!
    validations:
      required: true
  - type: textarea
    id: steps-to-reproduce
    attributes:
      label: Steps to reproduce
      description: How can we reproduce the bug?
      placeholder: Step-by-step instructions
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: Relevant log output
      description: Please copy and paste any relevant log output. This will be automatically formatted into code, so no need for backticks.
      render: shell
  - type: input
    id: environment
    attributes:
      label: Environment
      description: OS, Python version, Azure Function version, etc.
      placeholder: e.g. macOS, Python 3.11, Azure Functions v4
    validations:
      required: false
