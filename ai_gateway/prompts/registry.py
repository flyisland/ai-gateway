from pathlib import Path
from typing import List, NamedTuple, Optional, Type

import structlog
import yaml
from langchain.tools import BaseTool
from poetry.core.constraints.version import Version, parse_constraint

from ai_gateway.config import ConfigModelLimits
from ai_gateway.internal_events.client import InternalEventsClient
from ai_gateway.model_metadata import TypeModelMetadata
from ai_gateway.model_selection.model_selection_config import LLMDefinition, UnitPrimitiveConfig
from ai_gateway.prompts.base import BasePromptRegistry, Prompt
from ai_gateway.prompts.config import BaseModelConfig, ModelClassProvider, PromptConfig
from ai_gateway.prompts.typing import TypeModelFactory
from ai_gateway.model_selection import ModelSelectionConfig


__all__ = ["LocalPromptRegistry", "PromptRegistered"]

log = structlog.stdlib.get_logger("prompts")


class PromptRegistered(NamedTuple):
    klass: Type[Prompt]
    versions: dict[str, PromptConfig]


class LocalPromptRegistry(BasePromptRegistry):
    key_prompt_type_base: str = "base"

    def __init__(
        self,
        model_selection: ModelSelectionConfig,
        prompts_registered: dict[str, PromptRegistered],
        model_factories: dict[ModelClassProvider, TypeModelFactory],
        default_prompts: dict[str, str],
        internal_event_client: InternalEventsClient,
        model_limits: ConfigModelLimits,
        custom_models_enabled: bool,
        disable_streaming: bool = False,
    ):
        self.model_selection = model_selection
        self.prompts_registered = prompts_registered
        self.model_factories = model_factories
        self.default_prompts = default_prompts
        self.internal_event_client = internal_event_client
        self.model_limits = model_limits
        self.custom_models_enabled = custom_models_enabled
        self.disable_streaming = disable_streaming

    def _resolve_id(
        self,
        prompt_id: str,
        model_metadata: Optional[TypeModelMetadata] = None,
    ) -> str:
        if model_metadata:
            return f"{prompt_id}/{model_metadata.name}"

        type = self.default_prompts.get(prompt_id, self.key_prompt_type_base)
        return f"{prompt_id}/{type}"

    def _get_prompt_config(
        self, versions: dict[str, PromptConfig], prompt_version: str
    ) -> PromptConfig:
        # Parse constraint according to poetry rules. See
        # https://python-poetry.org/docs/dependency-specification/#version-constraints
        constraint = parse_constraint(prompt_version)
        all_versions = [Version.parse(version) for version in versions.keys()]

        # If the query is not "simple" (in other words, it's not referencing specific versions but is a constraint or
        # set of constraints, for example a range) we only want to consider stable versions. This allows us to not
        # auto-serve dev/rc versions to clients using queries like `^1.0.0`
        if not constraint.is_simple():
            all_versions = [version for version in all_versions if version.is_stable()]

        compatible_versions = list(filter(constraint.allows, all_versions))
        if not compatible_versions:
            log.info(
                "No compatible versions found",
                versions=versions,
                prompt_version=prompt_version,
            )
            raise ValueError(
                f"No prompt version found matching the query: {prompt_version}"
            )
        compatible_versions.sort(reverse=True)

        return versions[str(compatible_versions[0])]

    def get(
        self,
        prompt_id: str,
        prompt_version: str,
        model_metadata: Optional[TypeModelMetadata] = None,
        tools: Optional[List[BaseTool]] = None,
    ) -> Prompt:
        prompt_id = self._resolve_id(prompt_id, model_metadata)

        log.info("Resolved prompt id", prompt_id=prompt_id)

        prompt_registered = self.prompts_registered[prompt_id]
        config = self._get_prompt_config(prompt_registered.versions, prompt_version)
        model_class_provider = config.model.params.model_class_provider
        model_factory = self.model_factories.get(model_class_provider, None)

        if not model_factory:
            raise ValueError(
                f"unrecognized model class provider `{model_class_provider}`."
            )

        log.info(
            "Returning prompt from the registry",
            prompt_id=prompt_id,
            prompt_name=config.name,
            prompt_version=prompt_version,
        )

        return prompt_registered.klass(
            model_factory,
            config,
            model_metadata,
            disable_streaming=self.disable_streaming,
            tools=tools,
        )

    @classmethod
    def from_local_yaml(
        cls,
        model_selection: ModelSelectionConfig,
        class_overrides: dict[str, Type[Prompt]],
        model_factories: dict[ModelClassProvider, TypeModelFactory],
        default_prompts: dict[str, str],
        internal_event_client: InternalEventsClient,
        model_limits: ConfigModelLimits,
        custom_models_enabled: bool = False,
        disable_streaming: bool = False,
    ) -> "LocalPromptRegistry":
        """Iterate over all prompt definition files matching [usecase]/[type]/[version].yml, and create a corresponding
        prompt for each one.

        The base Prompt class is used if no matching override is provided in `class_overrides`.
        """

        base_path = Path(__file__).parent
        prompts_definitions_dir = base_path / "definitions"
        model_configs_dir = base_path / "model_configs"
        prompts_registered = {}

        model_definitions = model_selection.get_llm_definitions()
        unit_primitive_configuration = model_selection.get_unit_primitive_config()
        
        model_configs = {
            file.stem: cls._parse_base_model(file)
            for file in model_configs_dir.glob("*.yml")
        }

        # Iterate over each folder
        for path in prompts_definitions_dir.glob("**"):
            # Iterate over each version file
            versions = {
                version.stem: cls._process_version_file(
                    version, 
                    model_definitions, 
                    unit_primitive_configuration,
                    model_configs  # Pass model_configs for fallback
                )
                for version in path.glob("*.yml")
            }

            # If there were no yml files in this folder, skip it
            if not versions:
                continue

            # E.g., "chat/react/base", "generate_description/mistral", etc.
            prompt_id_with_model_name = path.relative_to(prompts_definitions_dir)

            klass = class_overrides.get(str(prompt_id_with_model_name.parent), Prompt)
            prompts_registered[str(prompt_id_with_model_name)] = PromptRegistered(
                klass=klass, versions=versions
            )

        log.info(
            "Initializing prompt registry from local yaml",
            default_prompts=default_prompts,
            custom_models_enabled=custom_models_enabled,
        )

        return cls(
            model_selection,
            prompts_registered,
            model_factories,
            default_prompts,
            internal_event_client,
            model_limits,
            custom_models_enabled,
            disable_streaming,
        )

    @classmethod
    def _parse_base_model(cls, file_name: Path) -> BaseModelConfig:
        """Parses a YAML file and converts its content to a BaseModelConfig object.

        This method reads the specified YAML file, extracts the configuration
        parameters, and constructs a BaseModelConfig object. It handles the
        conversion of YAML data types to appropriate Python types.

        Args:
            file (Path): A Path object pointing to the YAML file to be parsed.

        Returns:
            BaseModelConfig: An instance of BaseModelConfig containing the
            parsed configuration data.
        """

        with open(file_name, "r") as fp:
            return BaseModelConfig(**yaml.safe_load(fp))

    @classmethod
    def _process_version_file(
        cls, 
        version_file: Path,
        model_definitions: dict[str, LLMDefinition], 
        unit_primitive_configuration: list[UnitPrimitiveConfig],
        model_configs: dict[str, BaseModelConfig]
    ) -> PromptConfig:
        """Processes a single version YAML file and returns a PromptConfig.

        Args:
            version_file: Path to the version YAML file
            model_definitions: LLM definitions as a mapping of identifier to LLMDefinition
            unit_primitive_configuration: unit primitive configuration for specific model selection
            model_configs: Dictionary of model configurations for fallback

        Returns:
            PromptConfig: Processed prompt configuration
        """

        with open(version_file, "r") as fp:
            prompt_config_params = yaml.safe_load(fp)

            model_family = prompt_config_params.get('model', {}).get('name')

            # Model metadata is provided in the respctives request to include
            if model_family:
                log.info("Using explicit model family", model_family=model_family, version_file=version_file)
                return PromptConfig(**prompt_config_params)

            unit_primitives = prompt_config_params.get('unit_primitives', [])
            if unit_primitives:
                unit_primitive_config = cls.get_config_for_unit_primitive(unit_primitive_configuration, unit_primitives)
                
                if unit_primitive_config is not None:
                    gitlab_identifier = unit_primitive_config.default_model
                    model_definition = model_definitions[gitlab_identifier]

                    
                    model_selection_prompt_config_params = model_definition.params.copy()
                    model_selection_prompt_config_params['model_class_provider'] = model_definition.provider
                    model_selection_prompt_config_params["name"] = model_definition.provider_identifier

                    log.info("Using unit primitive model selection", 
                            model_selection_prompt_config_params=model_selection_prompt_config_params, 
                            version_file=version_file,
                            unit_primitives=unit_primitives)

                    prompt_config_params = cls._patch_model_configuration_from_unit_primitive(
                        model_selection_prompt_config_params, prompt_config_params
                    )
                    
                    log.info("Final prompt config from unit primitive", prompt_config_params=prompt_config_params)
                    return PromptConfig(**prompt_config_params)
                else:
                    log.info(f"Model selection for unit primitives {unit_primitives} is not defined in config, trying config_file fallback")

            # Fallback to config_file approach if unit primitive lookup failed or no unit_primitives specified
            if "config_file" in prompt_config_params.get("model", {}):
                model_config_name = prompt_config_params["model"]["config_file"]
                config_for_general_model = model_configs.get(model_config_name)
                
                if config_for_general_model:
                    log.info("Using config_file fallback", 
                            config_file=model_config_name, 
                            version_file=version_file)
                    
                    prompt_config_params = cls._patch_model_configuration_from_config_file(
                        config_for_general_model, prompt_config_params
                    )
                    
                    log.info("Final prompt config from config_file", prompt_config_params=prompt_config_params)
                    return PromptConfig(**prompt_config_params)
                else:
                    log.error(f"Config file '{model_config_name}' not found in model_configs")
                    raise ValueError(f"Config file '{model_config_name}' not found in model_configs")
            
            # If we get here, neither unit primitive nor config_file approach worked
            log.error("No valid model configuration found", 
                     version_file=version_file,
                     unit_primitives=unit_primitives,
                     has_config_file="config_file" in prompt_config_params.get("model", {}))
            raise ValueError(f"No valid model configuration found for {version_file}")

    @classmethod
    def _patch_model_configuration_from_unit_primitive(
        cls, model_selection_prompt_config_params: dict, prompt_config_params: dict
    ) -> dict:
        """Patch model configuration from unit primitive selection."""
        params_without_name = model_selection_prompt_config_params.copy()
        params_without_name.pop('name', None)
        
        params = {
            **params_without_name,
            **prompt_config_params["model"].get("params", {}),
        }

        return {
            **prompt_config_params,
            "model": {
                "name": model_selection_prompt_config_params['name'],
                "params": params,
            },
        }

    @classmethod
    def _patch_model_configuration_from_config_file(
        cls, config_for_general_model: BaseModelConfig, prompt_config_params: dict
    ) -> dict:
        """
        TODO: please remove this codepath once all the tool unit primitives have
        been moved over to the ai_gateway/model_selection/unit_primitives.yml, 
        model selection. The following is only meant for a fallover assuming
        the model selection information isn't present.
        Patch model configuration from config file."""
        params = {
            **config_for_general_model.params.model_dump(),
            **prompt_config_params["model"].get("params", {}),
        }

        return {
            **prompt_config_params,
            "model": {
                "name": config_for_general_model.name,
                "params": params,
            },
        }
    
    @classmethod
    def get_config_for_unit_primitive(cls, configs: list[UnitPrimitiveConfig], unit_primitives: list[str]) -> UnitPrimitiveConfig:
        """
        Find the UnitPrimitiveConfig object that has exactly the same unit_primitives list
        as the specified unit_primitives.
        
        Args:
            configs: List of UnitPrimitiveConfig objects
            unit_primitives: The list of unit primitives to match exactly
            
        Returns:
            The matching UnitPrimitiveConfig or None if not found
        """
        # Convert the input unit_primitives to a set of strings
        unit_primitives_set = set(unit_primitives)
        
        for config in configs:
            # Convert the enum values to strings for comparison
            config_unit_primitives_set = {str(primitive) for primitive in config.unit_primitives}
            
            # Check if the sets contain exactly the same elements
            if config_unit_primitives_set == unit_primitives_set:
                return config
        return None