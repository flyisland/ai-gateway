from http import HTTPMethod
import json
import logging
from typing import Any, Optional, Type

from pydantic import BaseModel, Field

from contract import contract_pb2
from duo_workflow_service.executor.action import _execute_action
from duo_workflow_service.tools.gitlab_resource_input import GitLabResourceInput
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

# Setup logger
logger = logging.getLogger(__name__)


DESCRIPTION_CHARACTER_LIMIT = 1_048_576

AGENT_IDENTIFICATION_DESCRIPTION = """To identify the agent you must provide the agent_id parameter"""


class GitLabAgentForKubernetesInput(GitLabResourceInput):
    agent_id: int = Field(description="ID GitLab Agent for Kubernetes")


class KubernetesGVRInput:
    group: Optional[str] = Field(
        default="", description="Group of the Kubernetes resources")
    version: Optional[str] = Field(
        default="v1", description="Version of the Kubernetes resources")
    resource: str = Field(
        description="Name of the Kubernetes resource. It should match the resource as it's used in the Kubernetes API path, like pods for Pods.")


class KubernetesNamespacedInput:
    namespace: str = Field(description="Namespace of the Kubernetes resource")


class KubernetesUnstructuredObjectInput:
    unstructured_resource_object: str = Field(
        description="Unstructured Kubernetes resource object")


class ListKubernetesResourcesInput(
    GitLabAgentForKubernetesInput, KubernetesGVRInput
):
    pass


class CreateKubernetesResourceInNamespaceInput(
    GitLabAgentForKubernetesInput, KubernetesGVRInput, KubernetesNamespacedInput, KubernetesUnstructuredObjectInput
):
    pass


class ListKubernetesResources(DuoBaseTool):
    name: str = "list_kubernetes_resources"
    description: str = f"""List all the Kubernetes resources in the cluster of the GitLab Agent from all namespaces

    {AGENT_IDENTIFICATION_DESCRIPTION}
    """
    args_schema: Type[BaseModel] = ListKubernetesResourcesInput

    async def _arun(
        self,
        agent_id: int,
        resource: str,
        version: Optional[str],
        group: Optional[str],
        **kwargs: Any,
    ) -> str:
        resource_path = get_raw_resource_path_for_k8s_api(
            group, version, resource)
        request = contract_pb2.GitLabAgentKubernetesRequest(
            agent_id=agent_id, path=resource_path, method=HTTPMethod.GET)

        try:
            response = await _execute_action(
                self.metadata,
                contract_pb2.Action(runGitLabAgentKubernetesRequest=request)
            )

            return json.loads(response)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(
            self, args: ListKubernetesResourcesInput) -> str:
        return f"List resources {args.resource} of version {args.version} from group {args.group} for GitLab Agent for Kubernetes {args.agent_id}"


class CreateKubernetesResourceInNamespace(DuoBaseTool):
    name: str = "create_kubernetes_resource_in_namespace"
    description: str = f"""Create a Kubernetes resource in the given namespace and in the cluster of the GitLab Agent

    The Kubernetes resource may be a pod, deployment, service, configmap, secret or any other valid Kubernetes object.

    {AGENT_IDENTIFICATION_DESCRIPTION}
    """
    args_schema: Type[BaseModel] = CreateKubernetesResourceInNamespaceInput

    async def _arun(
        self,
        agent_id: int,
        resource: str,
        namespace: str,
        unstructured_resource_object: str,
        version: Optional[str],
        group: Optional[str],
        **kwargs: Any,
    ) -> str:
        resource_path = get_raw_resource_path_for_k8s_api(
            group, version, resource, namespace)
        request = contract_pb2.GitLabAgentKubernetesRequest(
            agent_id=agent_id,
            path=resource_path,
            method=HTTPMethod.POST,
            body=unstructured_resource_object)

        try:
            response = await _execute_action(
                self.metadata,
                contract_pb2.Action(runGitLabAgentKubernetesRequest=request)
            )

            return json.loads(response)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(
            self, args: CreateKubernetesResourceInNamespaceInput) -> str:
        return f"Create resource {args.resource} of version {args.version} from group {args.group} in namespace {args.namespace} for GitLab Agent for Kubernetes {args.agent_id}"


def get_raw_resource_path_for_k8s_api(
        group, version, resource, namespace=None) -> str:
    # Build the API path
    if group == "":
        # Core API
        base_path = f"/api/{version}"
    else:
        # Named group
        base_path = f"/apis/{group}/{version}"

    # Add namespace if provided
    if namespace:
        resource_path = f"{base_path}/namespaces/{namespace}/{resource}"
    else:
        resource_path = f"{base_path}/{resource}"

    return resource_path
