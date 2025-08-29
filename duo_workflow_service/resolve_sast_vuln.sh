#!/bin/bash

curl -X POST \
    -H "Authorization: Bearer $GDK_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "project_id": "26",
        "agent_privileges": [1, 2, 3, 4, 5],
        "goal": "Fix vulnerability ID: 773",
        "start_workflow": true,
        "workflow_definition": "resolve_sast_vulnerability/experimental",
        "environment": "web",
        "source_branch": "security/sast/resolve-vulnerability-773"
    }' \
    http://gdk.test:3000/api/v4/ai/duo_workflows/workflows
