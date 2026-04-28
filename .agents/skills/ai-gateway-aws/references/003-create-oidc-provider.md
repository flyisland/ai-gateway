## Create an OpenID Connect provider

### Check for existing OIDC provider

Verify whether the OIDC identity provider for `<gitlab_instance_hostname>` already exists:

```shell
aws iam list-open-id-connect-providers --profile <aws_account_name> --region <aws_region> | jq -e '.OpenIDConnectProviderList[] | select(.Arn | contains("<gitlab_instance_hostname>"))' || echo 'No ID provider defined to serve workloads through ID tokens for this GitLab instance.'
```

### Create the OIDC provider if missing

Create the OIDC identity provider:

```shell
aws iam create-open-id-connect-provider \
  --url https://<gitlab_instance_hostname> \
  --client-id-list https://<gitlab_instance_hostname> \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Create an IAM role for GitLab CI

Ask the user:
> What is the full project path on <gitlab_instance_hostname>? (e.g. `hackystack-environments/aws-provider-.../project-name`)
> What IAM role name would you like? (default: `gitlab-ci`)
> What permissions does the role need? (e.g. specific AWS services or a managed policy)

Create the IAM role with a trust policy scoped to the GitLab project:

```shell
aws iam create-role \
  --role-name <role_name> \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Federated": "arn:aws:iam::<account_id>:oidc-provider/<gitlab_instance_hostname>"
        },
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {
          "StringLike": {
            "<gitlab_instance_hostname>:sub": "project_path:<full_project_path>:*"
          },
          "StringEquals": {
            "<gitlab_instance_hostname>:aud": "https://<gitlab_instance_hostname>"
          }
        }
      }
    ]
  }' \
  --profile <aws_account_name> \
  --region <aws_region>
```

Attach the `AmazonBedrockLimitedAccess` managed policy:

```shell
aws iam attach-role-policy \
  --role-name <role_name> \
  --policy-arn arn:aws:iam::aws:policy/AmazonBedrockLimitedAccess \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Configure `.gitlab-ci.yml` with `id_tokens`

Instruct the user to add `id_tokens` to their CI jobs that need AWS access. Example job configuration:

```yaml
deploy:
  id_tokens:
    AWS_ID_TOKEN:
      aud: https://<gitlab_instance_hostname>
  variables:
    AWS_ROLE_ARN: arn:aws:iam::<account_id>:role/<role_name>
  before_script:
    - >
      export $(printf "AWS_ACCESS_KEY_ID=%s AWS_SECRET_ACCESS_KEY=%s AWS_SESSION_TOKEN=%s"
      $(aws sts assume-role-with-web-identity
      --role-arn "$AWS_ROLE_ARN"
      --role-session-name "gitlab-ci-${CI_JOB_ID}"
      --web-identity-token "$AWS_ID_TOKEN"
      --duration-seconds 3600
      --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]'
      --output text))
  script:
    - aws sts get-caller-identity
```

Key details:
- `id_tokens` declares a job token with `aud` matching the OIDC provider's client ID.
- `assume-role-with-web-identity` exchanges the token for temporary AWS credentials.
- The `sub` claim in the trust policy restricts which projects/branches can assume the role.

