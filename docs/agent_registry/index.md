# Agent Registry

The Agent Registry defines and manages AI agents in GitLab using YAML configuration files.
In GitLab, we define the agent as an ML component that combines a prompt, a model, and a parser to process the output.
All agents implement the LangChain Runnable interface, which provides various methods for interaction.
For more details on the Runnable interface, refer to the official [LangChain documentation](https://python.langchain.com/v0.1/docs/expression_language/interface/).

## Defining an Agent

To create an agent, follow these steps:

1. Create a new directory for your agent using the following path structure:
   `agents/definitions/<agent_id>`

   Replace `<agent_id>` with a short, descriptive name for your agent, using underscores instead of spaces. For example:
   - Good: `my_custom_agent`
   - Bad: `My Complex Agent Name`

   This `agent_id` will be used to identify and reference your agent throughout the system. 
1. Inside this directory, create a `base.yml` file with the following structure:

```yaml
---
name: <agent_name>
model:
  name: <model_name>
  params:
    # Model-specific parameters
    model_class_provider: <provider>
    # Additional parameters based on the provider
unit_primitives:
  - <primitive_1>
  - <primitive_2>
prompt_template:
  system: |
    # Optional: System prompt content
  user: |
    # User prompt format
  assistant: |
    # Optional: Assistant prompt format
stop:
  - <stop_sequence>
```

### YAML File Sections

#### Name

The `name` field provides a human-readable name for your agent.
It is used for display purposes only and can include spaces and be descriptive.
This differs from the `agent_id`, which is used for system identification:

```yaml
name: GitLab Code Review Agent
```

#### Model

The `model` section defines the AI model and its parameters:

```yaml
model:
  name: claude-3-sonnet-20240229
  params:
    model_class_provider: anthropic
    # Additional parameters depend on the model_class_provider
```

- `name`: Specifies the model to use (e.g., `claude-3-sonnet-20240229`)
- `params`: Defines model-specific parameters:
  - `model_class_provider`: Specifies the provider of the model (currently supports `anthropic` and `lite_llm`)
  - Additional parameters depend on the `model_class_provider`:
    - For `anthropic`, refer to the `agents.config.ChatAnthropicParams` class
    - For `lite_llm`, refer to the `agents.config.ChatLiteLLMParams` class

#### Unit Primitives

The `unit_primitives` section lists the unit primitives required for agent access.

```yaml
unit_primitives:
  - duo_chat
```

Refer to the [gitlab_features.py](../ai_gateway/gitlab_features.py) module for available unit primitives.

#### Prompt Template

The `prompt_template` section defines prompts for different roles:

```yaml
prompt_template:
  system: |
    # Optional: System prompt content
  user: |
    Question: {question}
  assistant: |
    # Optional: Assistant prompt format
```

Internally, we translate this prompt template to the LangChain `ChatPromptTemplate`.
For more information, refer to https://python.langchain.com/v0.1/docs/modules/model_io/prompts/quick_start/#chatprompttemplate.

#### Stop Sequences

The `stop` section defines sequences that will cause the model to stop generating:

```yaml
stop:
  - "Observation:"
```

## Basic Example

Here's a basic example of an agent definition:

```yaml
---
name: Simple GitLab Assistant
model:
  name: claude-3-sonnet-20240229
  params:
    model_class_provider: anthropic
    temperature: 0.0
    max_tokens: 1000
unit_primitives:
  - duo_chat
prompt_template:
  user: |
    Question: {question}
stop:
  - "Observation:"
```

This example defines a simple GitLab assistant using the Claude 3 model with basic parameters and a minimal prompt template.
Save this configuration as `agents/definitions/simple_gitlab_assistant/base.yml`.

### Accessing the Agent

You can access the defined agent in several ways.

#### Using Python Code

```python
import asyncio
from dotenv import load_dotenv

from ai_gateway.container import ContainerApplication

# Load environment variables from a .env file
load_dotenv()


async def main():
    # Create an instance of the ContainerApplication
    container = ContainerApplication()

    # Retrieve the agent registry from the container
    agent_registry = container.pkg_agents.agent_registry()

    # Get the specific agent named "simple_gitlab_assistant"
    agent = agent_registry.get("simple_gitlab_assistant")
    # Another way to access the same agent
    # agent = agent_registry.get("simple_gitlab_assistant/base")

    # Demonstrate a single response interaction
    # Invoke the agent with a question and await the response
    answer = await agent.ainvoke({"question": "What's the capital of France?"})

    # Print the answer, which is expected to be a dictionary with a 'content' key
    print(answer)

    # Demonstrate a streaming response interaction
    # Use astream to get responses in chunks
    async for s in agent.astream({"question": "What's the capital of France?"}):
        # Print each chunk of the response without a newline, flushing the output
        print(s.content, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
```

#### Via API Endpoint

1. Start the `ai_gateway` server (with or without authentication enabled).
1. Make a POST request to the `/v1/agents/{agent_id}` endpoint:
   ```shell
   curl -X 'POST' \
      'http://localhost:5052/v1/agents/simple_gitlab_assistant' \
      -H 'accept: application/json' \
      -H 'Content-Type: application/json' \
      -d '{"question": "What'\''s the capital of France?"}'
   ```

   >Note: Add appropriate headers if authentication is enabled.
   Refer to the [authentication documentation](../auth.md) for details on disabling authentication in the AI Gateway.

## How-To Guides

TBD
