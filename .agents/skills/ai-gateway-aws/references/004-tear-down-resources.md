## Teardown

To remove the AWS resources created by this skill, run the following steps in order.

### Delete inline policies from the IAM role

List inline policies attached to the role, then delete each one:

```shell
aws iam list-role-policies --role-name <role_name> --profile <aws_account_name> --region <aws_region>
```

```shell
aws iam delete-role-policy \
  --role-name <role_name> \
  --policy-name <policy_name> \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Detach managed policies from the IAM role

List managed policies attached to the role, then detach each one:

```shell
aws iam list-attached-role-policies --role-name <role_name> --profile <aws_account_name> --region <aws_region>
```

```shell
aws iam detach-role-policy \
  --role-name <role_name> \
  --policy-arn <managed_policy_arn> \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Delete the IAM role

```shell
aws iam delete-role \
  --role-name <role_name> \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Delete the OIDC provider

```shell
aws iam delete-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::<account_id>:oidc-provider/<gitlab_instance_hostname> \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Manual teardown

Summarize a list of all AWS resources interacted with through this session for the user
with a list of commands they can run themselves to verify cleanup was successful.
