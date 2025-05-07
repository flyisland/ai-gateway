import os
import re
from typing import Dict, Optional, cast

import typer
from dependency_injector.wiring import Provide, inject
from eli5.datasets.generator import generate_dataset as eli5_generate_dataset
from jinja2 import PackageLoader
from jinja2.loaders import BaseLoader
from jinja2.sandbox import SandboxedEnvironment

from ai_gateway.config import Config
from ai_gateway.container import ContainerApplication
from ai_gateway.prompts.base import BasePromptRegistry


def get_message_source(prompt_template: Dict[str, str]) -> Dict[str, str]:
    """
    Gets the raw Jinja templates content from include statements.

    Args:
        prompt_template: A dictionary of template strings keyed by their role (e.g., "system", "user")

    Returns:
        A dictionary with the same keys as prompt_template, but with raw template content
    """
    jinja_env = SandboxedEnvironment(
        loader=PackageLoader("ai_gateway.prompts", "definitions")
    )

    raw_templates = {}

    for role, template_str in prompt_template.items():
        # Extract the template path from include statement
        # Example: "{% include 'chat/explain_code/system/1.0.0.jinja' %}\n"
        if "{% include" in template_str:
            match = re.search(r"{% include '([^']+)' %}", template_str)
            if match:
                template_path = match.group(1)
                try:
                    loader = cast(BaseLoader, jinja_env.loader)
                    raw_content = loader.get_source(jinja_env, template_path)[0]
                    raw_templates[role] = raw_content
                except Exception as e:
                    print(f"Error loading template {template_path}: {e}")
        else:
            raw_templates[role] = template_str

    return raw_templates


@inject
def get_prompt_source(
    prompt_id: str,
    prompt_version: str,
    prompt_registry: BasePromptRegistry = Provide[
        ContainerApplication.pkg_prompts.prompt_registry
    ],
):
    prompt = prompt_registry.get(prompt_id, prompt_version)

    # Extract prompt message templates from LangChain objects encapsulated by the Prompt returned from the registry
    chat_prompt_template = prompt.prompt_tpl
    prompt_template = {}
    messages = getattr(chat_prompt_template, "messages", [])
    for message in messages:
        if message.__class__.__name__ == "SystemMessagePromptTemplate":
            role = "system"
        elif message.__class__.__name__ == "HumanMessagePromptTemplate":
            role = "user"
        elif message.__class__.__name__ == "AIMessagePromptTemplate":
            role = "assistant"
        else:
            message_type = getattr(message, "message_type", None)
            if message_type:
                role = message_type
            else:
                role = getattr(message, "type", message.__class__.__name__)

        template = message.prompt.template
        prompt_template[role] = template

    source_messages = get_message_source(prompt_template)

    return {
        "name": prompt.name,
        "prompt_template": {
            "system": source_messages.get("system", None),
            "user": source_messages.get("user", None),
        },
    }


def run(
    prompt_id: str = typer.Argument(..., help="Prompt ID (e.g., 'chat/explain_code')"),
    prompt_version: str = typer.Argument(..., help="Prompt version constraint"),
    dataset_name: str = typer.Argument(..., help="Name for the dataset"),
    output_dir: Optional[str] = typer.Option(
        os.path.join(os.path.dirname(__file__), ".."),
        help="Directory to save the dataset (default: current directory)",
    ),
    num_examples: int = typer.Option(10, help="Number of examples to generate"),
    temperature: float = typer.Option(0.7, help="Temperature setting for generation"),
):
    """
    Generate a synthetic dataset for evaluating prompts using templates from the prompt registry.

    Args:
        prompt_id: The ID of the prompt template in the registry (e.g., 'chat/explain_code')
        prompt_version: Version constraint for the prompt template (e.g., '1.0.0')
        dataset_name: Name for the generated dataset (will be used in the output filename)
        output_dir: Directory to save the dataset file (defaults to the project root directory)
        num_examples: Number of examples to generate (default: 10)
        temperature: Temperature setting for generation (higher values = more diverse examples)

    Returns:
        Path to the generated dataset file
    """
    container_application = ContainerApplication()
    container_application.config.from_dict(Config().model_dump())
    container_application.wire(modules=[__name__])

    typer.echo(
        f"Generating dataset with {num_examples} examples from prompt: {prompt_id}"
    )

    prompt_source = get_prompt_source(prompt_id, prompt_version)

    output_file = eli5_generate_dataset(
        prompt_source=prompt_source,
        dataset_name=dataset_name,
        output_dir=output_dir,
        num_examples=num_examples,
        temperature=temperature,
    )

    typer.echo(f"Dataset generated successfully: {output_file.resolve()}")

    return output_file


def main() -> None:
    typer.run(run)


if __name__ == "__main__":
    main()
