from pathlib import Path
from textwrap import dedent

import pytest
from gitlab_cloud_connector import GitLabUnitPrimitive
from pyfakefs.fake_filesystem import FakeFilesystem

from ai_gateway.model_selection.model_selection_config import (
    LLMDefinition,
    ModelSelectionConfig,
    UnitPrimitiveConfig,
)


# editorconfig-checker-disable
@pytest.fixture(name="mock_fs")
def mock_fs_fixture(fs: FakeFilesystem):
    print(Path(__file__).parent.parent.parent / "ai_gateway" / "model_selection")
    model_selection_dir = (
        Path(__file__).parent.parent.parent / "ai_gateway" / "model_selection"
    )
    fs.create_file(
        model_selection_dir / "models.yml",
        contents=dedent(
            """
            models:
              - name: Model One
                gitlab_identifier: gitlab-model-1
                params:
                  model: provider-model-1
                  param1: value1
              - name: Model Two
                gitlab_identifier: gitlab-model-2
                params:
                  model: provider-model-2
            """
        ),
    )

    fs.create_file(
        model_selection_dir / "unit_primitives.yml",
        contents=dedent(
            """
            configurable_unit_primitives:
              - feature_setting: "test_config"
                unit_primitives:
                  - "ask_commit"
                  - "ask_epic"
                default_model: "gitlab-model-1"
                selectable_models:
                  - "gitlab-model-1"
                beta_models:
                  - "gitlab-model-2"
            """
        ),
    )


# editorconfig-checker-enable


@pytest.fixture(name="selection_config")
def selection_config_fixture(mock_fs):  # pylint: disable=unused-argument
    return ModelSelectionConfig()


def test_load_llm_definitions(selection_config):
    assert selection_config.get_llm_definitions() == {
        "gitlab-model-1": LLMDefinition(
            name="Model One",
            gitlab_identifier="gitlab-model-1",
            params={"model": "provider-model-1", "param1": "value1"},
        ),
        "gitlab-model-2": LLMDefinition(
            name="Model Two",
            gitlab_identifier="gitlab-model-2",
            params={"model": "provider-model-2"},
        ),
    }


def test_get_unit_primitive_config(selection_config):
    assert list(selection_config.get_unit_primitive_config()) == [
        UnitPrimitiveConfig(
            feature_setting="test_config",
            unit_primitives=[
                GitLabUnitPrimitive.ASK_COMMIT,
                GitLabUnitPrimitive.ASK_EPIC,
            ],
            default_model="gitlab-model-1",
            selectable_models=["gitlab-model-1"],
            beta_models=["gitlab-model-2"],
        )
    ]


def test_get_unit_primitive_config_map(selection_config):
    assert selection_config.get_unit_primitive_config_map() == {
        "test_config": UnitPrimitiveConfig(
            feature_setting="test_config",
            unit_primitives=[
                GitLabUnitPrimitive.ASK_COMMIT,
                GitLabUnitPrimitive.ASK_EPIC,
            ],
            default_model="gitlab-model-1",
            selectable_models=["gitlab-model-1"],
            beta_models=["gitlab-model-2"],
        )
    }


@pytest.mark.usefixtures("mock_fs")
def test_is_singleton():
    config_instance_1 = ModelSelectionConfig()
    config_instance_2 = ModelSelectionConfig()

    assert config_instance_1 is config_instance_2


def test_get_model(selection_config):
    assert selection_config.get_model("gitlab-model-1") == LLMDefinition(
        name="Model One",
        gitlab_identifier="gitlab-model-1",
        params={"model": "provider-model-1", "param1": "value1"},
    )


def test_get_model_missing_key(selection_config):
    with pytest.raises(ValueError):
        selection_config.get_model("non-existing-model")


def test_get_model_for_feature(selection_config):
    assert selection_config.get_model_for_feature("test_config") == LLMDefinition(
        name="Model One",
        gitlab_identifier="gitlab-model-1",
        params={"model": "provider-model-1", "param1": "value1"},
    )


def test_get_model_for_feature_no_feature(selection_config):
    with pytest.raises(ValueError, match="Invalid feature setting: random-feature"):
        selection_config.get_model_for_feature("random-feature")


@pytest.mark.usefixtures("mock_fs")
def test_validate_without_error():
    assert ModelSelectionConfig().validate() is None


def test_validate_with_error(fs: FakeFilesystem):
    model_selection_dir = (
        Path(__file__).parent.parent.parent / "ai_gateway" / "model_selection"
    )

    # editorconfig-checker-disable
    fs.create_file(
        model_selection_dir / "unit_primitives.yml",
        contents=dedent(
            """
            configurable_unit_primitives:
              - feature_setting: "test_config"
                unit_primitives:
                  - "ask_commit"
                default_model: "non_existent_model"
                selectable_models:
                  - "model_1"
                  - "another_non_existent_model"
                beta_models:
                  - "third_non_existent_model"
            """
        ),
    )

    # Create a models.yml file with valid models
    fs.create_file(
        model_selection_dir / "models.yml",
        contents=dedent(
            """
            models:
              - name: Model One
                gitlab_identifier: model_1
                params:
                  model: provider-model-1
            """
        ),
    )
    # editorconfig-checker-enable

    with pytest.raises(ValueError) as excinfo:
        ModelSelectionConfig().validate()

    error_message = str(excinfo.value)
    assert "non_existent_model" in error_message
    assert "another_non_existent_model" in error_message
    assert "third_non_existent_model" in error_message


def test_validate_default_model_not_in_selectable_models(fs: FakeFilesystem):
    """Test that validation fails when default models are not in selectable_models."""
    model_selection_dir = (
        Path(__file__).parent.parent.parent / "ai_gateway" / "model_selection"
    )

    # editorconfig-checker-disable
    fs.create_file(
        model_selection_dir / "models.yml",
        contents=dedent(
            """
            models:
              - name: Model One
                gitlab_identifier: model_1
                params:
                  model: provider-model-1
              - name: Model Two
                gitlab_identifier: model_2
                params:
                  model: provider-model-2
              - name: Model Three
                gitlab_identifier: model_3
                params:
                  model: provider-model-3
            """
        ),
    )

    fs.create_file(
        model_selection_dir / "unit_primitives.yml",
        contents=dedent(
            """
            configurable_unit_primitives:
              - feature_setting: "test_config"
                unit_primitives:
                  - "ask_commit"
                default_model: "model_1"
                selectable_models:
                  - "model_2"
                  - "model_3"
              - feature_setting: "another_config"
                unit_primitives:
                  - "generate_code"
                default_model: "model_2"
                selectable_models:
                  - "model_1"
                  - "model_3"
            """
        ),
    )
    # editorconfig-checker-enable

    with pytest.raises(ValueError) as excinfo:
        ModelSelectionConfig().validate()

    error_message = str(excinfo.value)
    expected_error = (
        "Default models must be included in selectable_models:\n"
        "  - Feature 'test_config' has default model 'model_1' that is not in selectable_models.\n"
        "  - Feature 'another_config' has default model 'model_2' that is not in selectable_models."
    )
    assert error_message == expected_error


def test_validate_selectable_models_not_in_alphabetical_order(fs: FakeFilesystem):
    model_selection_dir = (
        Path(__file__).parent.parent.parent / "ai_gateway" / "model_selection"
    )

    # editorconfig-checker-disable
    fs.create_file(
        model_selection_dir / "models.yml",
        contents=dedent(
            """
            models:
              - name: Claude 3.5 Sonnet
                gitlab_identifier: claude_3_5_sonnet_20240620
                params:
                  model: claude-3-5-sonnet-20240620
              - name: Claude Sonnet 3.7
                gitlab_identifier: claude_sonnet_3_7_20250219
                params:
                  model: claude-sonnet-3-7-20250219
              - name: Claude Sonnet 4
                gitlab_identifier: claude_sonnet_4_20250514
                params:
                  model: claude-sonnet-4-20250514
            """
        ),
    )

    fs.create_file(
        model_selection_dir / "unit_primitives.yml",
        contents=dedent(
            """
            configurable_unit_primitives:
              - feature_setting: "ordered_config"
                unit_primitives:
                  - "ask_commit"
                default_model: "claude_sonnet_4_20250514"
                selectable_models:
                    - "claude_3_5_sonnet_20240620"
                    - "claude_sonnet_3_7_20250219"
                    - "claude_sonnet_4_20250514"
              - feature_setting: "another_unordered_config"
                unit_primitives:
                  - "generate_code"
                default_model: "claude_sonnet_4_20250514"
                selectable_models:
                    - "claude_3_5_sonnet_20240620"
                    - "claude_sonnet_4_20250514"
                    - "claude_sonnet_3_7_20250219"
            """
        ),
    )
    # editorconfig-checker-enable

    with pytest.raises(ValueError) as excinfo:
        ModelSelectionConfig().validate()

    error_message = str(excinfo.value)
    expected_error = (
        "The following features have selectable_models not in alphabetical order:\n"
        "  - Feature 'another_unordered_config' has selectable_models not in alphabetical order"
    )
    assert error_message == expected_error
