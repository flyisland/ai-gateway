## Create a Bedrock Guardrail

### Check for existing guardrails

List existing guardrails to avoid duplicates:

```shell
aws bedrock list-guardrails --profile <aws_account_name> --region <aws_region>
```

To inspect a specific guardrail's full configuration:

```shell
aws bedrock get-guardrail \
  --guardrail-identifier <guardrail_id> \
  --profile <aws_account_name> \
  --region <aws_region>
```

To view tags on an existing guardrail:

```shell
aws bedrock list-tags-for-resource \
  --resource-arn <guardrail_arn> \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Gather requirements

Ask the user:
> What should the guardrail be named? (e.g. `my-bedrock-guardrail`)
> What sensitive information filters do you need? (e.g. AWS key redaction, PII anonymization)
> Do you need topic policies, content filters, word filters, or regex filters?

Prefer minimal configurations — skip optional policy sections (topic policies, content filters, word policies) unless the user explicitly requests them.

### Blocked messages

The `--blocked-input-messaging` and `--blocked-outputs-messaging` parameters are **required**. Use descriptive messages that help differentiate between:

- **Input blocked**: The user's request was rejected (human error or policy violation on the request side)
- **Output blocked**: The model's response was rejected (LLM-side policy violation)

Example messages:

- Input: `"Your request was blocked by a guardrail policy. Please revise your input and try again."`
- Output: `"The model's response was blocked by a guardrail policy. The generated content violated a configured restriction."`

### Create the guardrail

The `create-guardrail` CLI uses `*Config` suffixed key names (not the field names returned by `get-guardrail`). The key mapping is:

| `get-guardrail` response field | `create-guardrail` parameter field |
|--------------------------------|------------------------------------|
| `topics`                       | `topicsConfig`                     |
| `filters`                      | `filtersConfig`                    |
| `piiEntities`                  | `piiEntitiesConfig`                |
| `regexes`                      | `regexesConfig`                    |
| `managedWordLists`             | `managedWordListsConfig`           |
| `words`                        | `wordsConfig`                      |

#### Minimal example (sensitive information only)

This creates a guardrail with only AWS key redaction and a regex filter:

```shell
aws bedrock create-guardrail \
  --name <guardrail_name> \
  --blocked-input-messaging "Your request was blocked by a guardrail policy. Please revise your input and try again." \
  --blocked-outputs-messaging "The model's response was blocked by a guardrail policy. The generated content violated a configured restriction." \
  --sensitive-information-policy-config '{
    "piiEntitiesConfig": [
      {"type": "AWS_SECRET_KEY", "action": "BLOCK"},
      {"type": "AWS_ACCESS_KEY", "action": "ANONYMIZE"}
    ],
    "regexesConfig": [
      {
        "name": "example-pattern",
        "pattern": "\\b(pattern-to-match)\\b",
        "action": "ANONYMIZE",
        "description": "Describe what this regex matches"
      }
    ]
  }' \
  --tags '[
    {"key": "gl_realm", "value": "sandbox"},
    {"key": "gl_env_name", "value": "<aws_account_name>"},
    {"key": "gl_env_type", "value": "experiment"},
    {"key": "gl_owner_email_handle", "value": "ai_agents"}
  ]' \
  --profile <aws_account_name> \
  --region <aws_region>
```

#### Full example (all policy types)

This creates a guardrail with topic policies, content filters, word filters, and sensitive information filters:

```shell
aws bedrock create-guardrail \
  --name <guardrail_name> \
  --blocked-input-messaging "Your request was blocked by a guardrail policy. Please revise your input and try again." \
  --blocked-outputs-messaging "The model's response was blocked by a guardrail policy. The generated content violated a configured restriction." \
  --topic-policy-config '{
    "topicsConfig": [
      {
        "name": "TopicName",
        "definition": "Description of what this topic covers",
        "examples": ["example input that should be denied"],
        "type": "DENY"
      }
    ]
  }' \
  --content-policy-config '{
    "filtersConfig": [
      {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
      {"type": "HATE", "inputStrength": "NONE", "outputStrength": "NONE"},
      {"type": "INSULTS", "inputStrength": "NONE", "outputStrength": "NONE"},
      {"type": "SEXUAL", "inputStrength": "NONE", "outputStrength": "NONE"},
      {"type": "VIOLENCE", "inputStrength": "NONE", "outputStrength": "NONE"},
      {"type": "MISCONDUCT", "inputStrength": "NONE", "outputStrength": "NONE"}
    ]
  }' \
  --word-policy-config '{
    "wordsConfig": [
      {"text": "blocked-word"}
    ],
    "managedWordListsConfig": [
      {"type": "PROFANITY"}
    ]
  }' \
  --sensitive-information-policy-config '{
    "piiEntitiesConfig": [
      {"type": "AWS_SECRET_KEY", "action": "BLOCK"},
      {"type": "AWS_ACCESS_KEY", "action": "ANONYMIZE"},
      {"type": "IP_ADDRESS", "action": "ANONYMIZE"}
    ],
    "regexesConfig": [
      {
        "name": "pattern-name",
        "pattern": "\\b(regex-here)\\b",
        "action": "ANONYMIZE",
        "description": "What this regex matches"
      }
    ]
  }' \
  --tags '[
    {"key": "gl_realm", "value": "sandbox"},
    {"key": "gl_env_name", "value": "<aws_account_name>"},
    {"key": "gl_env_type", "value": "experiment"},
    {"key": "gl_owner_email_handle", "value": "ai_agents"}
  ]' \
  --profile <aws_account_name> \
  --region <aws_region>
```

### PII entity types

Common PII entity types available for `piiEntitiesConfig`:

- `AWS_SECRET_KEY`, `AWS_ACCESS_KEY` — AWS credentials
- `IP_ADDRESS` — IP addresses
- `EMAIL`, `PHONE`, `NAME`, `ADDRESS` — Personal contact info
- `SSN_OR_SIN`, `CREDIT_DEBIT_CARD_NUMBER` — Financial/identity numbers
- `US_PASSPORT_NUMBER`, `DRIVER_ID`, `US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER` — Government IDs
- `USERNAME`, `PASSWORD`, `URL` — Digital identifiers

Actions: `BLOCK` (reject entirely) or `ANONYMIZE` (redact/mask the value).

### Verify creation

After creating the guardrail, verify it exists and inspect the configuration:

```shell
aws bedrock get-guardrail \
  --guardrail-identifier <guardrail_id> \
  --profile <aws_account_name> \
  --region <aws_region>
```

### Delete a guardrail

To remove a guardrail:

```shell
aws bedrock delete-guardrail \
  --guardrail-identifier <guardrail_id> \
  --profile <aws_account_name> \
  --region <aws_region>
```
