---
name: ai-gateway-aws
description: Manage AWS resources required for testing Duo self-hosted or GitLab Bedrock vendor models.
license: MIT
compatibility: opencode duo
metadata:
  slash-command: enabled
---

## Identify the AWS Cloud Sandbox environment

Ask the user the following question:
> Have you already created an AWS cloud account inside of GitLab Cloud Sandbox?

If not recommend they self-service creation of an [individual AWS account](https://handbook.gitlab.com/handbook/company/infrastructure-standards/realms/sandbox/#individual-aws-account-or-gcp-project) following the handbook instructions.

Ask the user which sandbox environment to log into including the AWS region:
> Which Cloud Sandbox would you like to configure? (e.g. `eng-dev-sandbox-ecarey-50180192`)
> Which AWS region? (e.g. `us-east-1`)

In case of any AWS resources being created ensure tags are applied according to our [resource tag guidelines](references/002-resource-tag-guidelines.md).

In case of accessing AWS CLI first follow [setup AWS SDK credentials](references/001-setup-aws-sdk-credentials.md) to ensure ability to continue executing AWS CLI commands.

## Prompt the user to figure out which nested skills they'd like to execute

1. [Create OIDC provider](references/003-create-oidc-provider.md)
2. [Create Bedrock guardrail](references/005-create-bedrock-guardrail.md)
3. [Provision Bedrock credentials](references/006-provision-bedrock-credentials.md)
4. [Tear down resources](references/004-tear-down-resources.md)
