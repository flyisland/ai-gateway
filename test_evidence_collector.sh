#!/bin/bash

# Simulates a user asking Duo Chat to help with readiness checklists
# Only testing purposes

echo "🤖 Testing Readiness Evidence Collector"
echo "=============================================================="
echo ""

# Configuration
export GDK_API_TOKEN="${GDK_API_TOKEN}"
export READINESS_PROJECT_ID="${READINESS_PROJECT_ID}"

# Validate environment
if [ -z "$GDK_API_TOKEN" ]; then
    echo "❌ Error: GDK_API_TOKEN not set"
    echo "Set it with: export GDK_API_TOKEN='your-token'"
    exit 1
fi

if [ -z "$READINESS_PROJECT_ID" ]; then
    echo "❌ Error: READINESS_PROJECT_ID not set"
    echo "Set it with: export READINESS_PROJECT_ID='XX'"
    exit 1
fi

# Example requests
echo "📝 Example requests you can test:"
echo ""
echo "1. Simple category request:"
echo "   'Help me fill the service_architecture checklist'"
echo ""
echo "2. With evidence source:"
echo "   'Fill the service_architecture checklist using epic https://gitlab.com/groups/gitlab-org/-/epics/1234 for evidence'"
echo ""
echo "3. With multiple sources:"
echo "   'Complete the production readiness checklist, check epic 1234 and issues in this project for evidence'"
echo ""
echo "4. Minimal request:"
echo "   'service architecture'"
echo ""

# Get user input or use provided argument
if [ -z "$1" ]; then
    echo "Enter your request (or press Ctrl+C to cancel):"
    read -p "> " USER_REQUEST
else
    USER_REQUEST="$1"
fi

echo ""
echo "🎯 Processing request: \"$USER_REQUEST\""
echo ""

# Show what the flow will do
echo "🔄 Flow execution steps:"
echo "  1. 📖 template_reader   - Discovers and reads checklists from templates/"
echo "  2. 🔎 evidence_scanner  - Scans GitLab resources for evidence"
echo "  3. 🧠 evidence_analyzer - Matches evidence to checklist items"
echo "  4. ✍️  checklist_filler  - Creates filled checklist"
echo ""

# Confirm execution
read -p "Start the flow? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "🚀 Triggering Evidence Collector flow..."
echo ""

# Trigger the flow with natural language goal
RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $GDK_API_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"project_id\": \"$READINESS_PROJECT_ID\",
        \"agent_privileges\": [1,2,3,4,5],
        \"goal\": \"$USER_REQUEST\",
        \"start_workflow\": true,
        \"workflow_definition\": \"readiness_evidence_collector/experimental\",
        \"environment\": \"web\",
        \"source_branch\": \"readiness-evidence-collector\"
    }" \
    http://gdk.test:3000/api/v4/ai/duo_workflows/workflows)

# Parse response
echo "Flow Response:"
echo "----------------"
echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
echo ""

WORKFLOW_ID=$(echo "$RESPONSE" | jq -r '.id // empty' 2>/dev/null)

if [ ! -z "$WORKFLOW_ID" ]; then
    echo "✅ Flow started successfully!"
    echo ""
    echo "📈 Workflow Details:"
    echo "  ID: $WORKFLOW_ID"
    echo "  Project: readiness (ID: $READINESS_PROJECT_ID)"
    echo "  Request: $USER_REQUEST"
    echo ""
    echo "📡 Monitor execution:"
    echo "  Logs:    gdk tail duo-workflow-service"
    echo "  Browser: http://gdk.test:3000/root/readiness/-/pipelines"
    echo ""
    echo "💡 Check results in Rails console:"
    echo "  gdk rails console"
    echo "  > workflow = Ai::DuoWorkflows::Workflow.find($WORKFLOW_ID)"
    echo "  > pp workflow.state"
    echo "  > workflow.checkpoints.last&.state"
fi

