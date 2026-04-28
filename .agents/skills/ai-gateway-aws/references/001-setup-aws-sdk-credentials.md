## Setup AWS SDK Credentials

### Verify connectivity

Fetch the account details to verify connectivity. Save the `Account` ID from the response for later use.

```shell
aws sts get-caller-identity --profile <aws_account_name> --region <aws_region>
```

### Authenticate with AWS

To install the AWS CLI on MacOS:

```shell
brew install awscli
```

Users on other platforms should follow these [installation steps](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

Prompt the user to log into AWS CLI through their GitLab Cloud Sandbox AWS console credentials. If they are already logged in, skip this step.

```shell
aws sso login --profile <aws_account_name> --region <aws_region>
```

