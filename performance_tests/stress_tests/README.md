## Description

The tests in this folder are designed to be used with [GitLab Performance Tool](https://gitlab.com/gitlab-org/quality/performance), to generate Duo Agent load on a GitLab instance and identify performance bottlenecks.

They should not be added to CI pipelines at this time.

## How to run

1. Clone GPT, or use the Docker container
1. Identify the appropriate ENVIRONMENT_FILE, or create a new one if it does not exist.
1. Identify the appropriate OPTIONS_FILE, or create a new one if it does not exist.
1. Identify the project in your target environment that you want to run these tests against. Its project ID should be used later as PROJECTID.
1. Identify the user in your target environment that you want to use for running these tests. Generate a PAT.
1. Ensure that the user and project have all of the appropriate feature flags and licenses enabled to run Duo Agent in CI.
1. Run `AI_DUO_WORKFLOW_PROJECT_ID=<PROJECTID> ./bin/run-k6 --environment <ENVIRONMENT_FILE> --options <OPTIONS_FILE> --tests api_v4_duo_workflow_chat.js`
