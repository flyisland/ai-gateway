## Provision Bedrock Credentials

This reference provisions a long-term [Amazon Bedrock API key](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-generate.html#api-keys-generate-api-long-term) for local development, configured via `AWS_BEARER_TOKEN_BEDROCK`. This approach does not require IAM access keys or STS credentials.

### Quick start

Run the bundled script to create an IAM user, generate a 1-day Bedrock API key, and append it to the repository's `.env`:

```shell
.agents/skills/ai-gateway-aws/scripts/manage-bedrock-token create
```

To tear down the IAM user, all its Bedrock credentials, and remove `AWS_BEARER_TOKEN_BEDROCK` from `.env`:

```shell
.agents/skills/ai-gateway-aws/scripts/manage-bedrock-token delete
```

Override defaults with environment variables:

| Variable | Default | Description |
|---|---|---|
| `AWS_PROFILE` | `default` | AWS CLI named profile |
| `AWS_REGION` | `us-east-1` | AWS region |
| `IAM_USER_NAME` | `aigw-local-dev` | IAM user to create or reuse |
| `CREDENTIAL_AGE_DAYS` | `1` | Token validity in days |

### Manual steps

The sections below describe what the script does, for reference or if you prefer to run the commands yourself.

#### Create an IAM user

Check for existing IAM users to avoid duplicates:

```shell
aws iam list-users --profile <aws_account_name> --region <aws_region>
```

Create the IAM user:

```shell
aws iam create-user \
  --user-name <iam_user_name> \
  --tags '[
    {"Key": "gl_realm", "Value": "sandbox"},
    {"Key": "gl_env_name", "Value": "<aws_account_name>"},
    {"Key": "gl_env_type", "Value": "experiment"},
    {"Key": "gl_owner_email_handle", "Value": "<gl_owner_email_handle>"}
  ]' \
  --profile <aws_account_name> \
  --region <aws_region>
```

Attach the [AmazonBedrockLimitedAccess](https://docs.aws.amazon.com/bedrock/latest/userguide/security-iam-awsmanpol.html#security-iam-awsmanpol-AmazonBedrockLimitedAccess) managed policy:

```shell
aws iam attach-user-policy \
  --user-name <iam_user_name> \
  --policy-arn arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess \
  --profile <aws_account_name> \
  --region <aws_region>
```

#### Generate the long-term Bedrock API key

```shell
aws iam create-service-specific-credential \
  --user-name <iam_user_name> \
  --service-name bedrock.amazonaws.com \
  --credential-age-days <number_of_days> \
  --profile <aws_account_name> \
  --region <aws_region>
```

Save the `ServiceApiKeyValue` from the response — this is the Bedrock API key.

#### Configure the AI Gateway

Set the environment variable in the AI Gateway's `.env` file:

```shell
AWS_BEARER_TOKEN_BEDROCK=<ServiceApiKeyValue>
```

### Teardown

#### Delete service-specific credentials

List and delete the Bedrock API key:

```shell
aws iam list-service-specific-credentials \
  --user-name <iam_user_name> \
  --service-name bedrock.amazonaws.com \
  --profile <aws_account_name> \
  --region <aws_region>
```

```shell
aws iam delete-service-specific-credential \
  --user-name <iam_user_name> \
  --service-specific-credential-id <credential_id> \
  --profile <aws_account_name> \
  --region <aws_region>
```

#### Detach the managed policy from the IAM user

```shell
aws iam detach-user-policy \
  --user-name <iam_user_name> \
  --policy-arn arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess \
  --profile <aws_account_name> \
  --region <aws_region>
```

#### Delete the IAM user

```shell
aws iam delete-user \
  --user-name <iam_user_name> \
  --profile <aws_account_name> \
  --region <aws_region>
```

#### Manual teardown

Summarize a list of all AWS resources interacted with through this session for the user
with a list of commands they can run themselves to verify cleanup was successful.
