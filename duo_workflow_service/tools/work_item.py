import json
import urllib
from enum import Enum
from typing import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    NamedTuple,
    Optional,
    Type,
    Union,
)

from gitlab_cloud_connector import GitLabUnitPrimitive
from pydantic import BaseModel, Field, StringConstraints

from duo_workflow_service.gitlab.url_parser import GitLabUrlParseError, GitLabUrlParser
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool
from duo_workflow_service.tools.queries.work_items import (
    GET_GROUP_WORK_ITEM_NOTES_QUERY,
    GET_GROUP_WORK_ITEM_QUERY,
    GET_PROJECT_WORK_ITEM_NOTES_QUERY,
    GET_PROJECT_WORK_ITEM_QUERY,
    LIST_GROUP_WORK_ITEMS_QUERY,
    LIST_PROJECT_WORK_ITEMS_QUERY,
    UPDATE_WORK_ITEM_MUTATION,
)

PARENT_IDENTIFICATION_DESCRIPTION = """To identify the parent (group or project) you must provide either:
- group_id parameter, or
- project_id parameter, or
- A GitLab URL like:
    - https://gitlab.com/namespace/group
    - https://gitlab.com/groups/namespace/group
    - https://gitlab.com/namespace/project
    - https://gitlab.com/namespace/group/project
"""


WORK_ITEM_IDENTIFICATION_DESCRIPTION = """To identify a work item you must provide either:
- group_id/project_id and work_item_iid
    - group_id can be either a numeric ID (e.g., 42) or a path string (e.g., 'my-group' or 'namespace/subgroup')
    - project_id can be either a numeric ID (e.g., 13) or a path string (e.g., 'namespace/project')
    - work_item_iid is always a numeric value (e.g., 7)
- or a GitLab URL like:
    - https://gitlab.com/groups/namespace/group/-/work_items/42
    - https://gitlab.com/namespace/project/-/work_items/42
"""


class ResolvedParent(NamedTuple):
    type: Literal["group", "project"]
    full_path: str


class ResolvedWorkItem(NamedTuple):
    parent: ResolvedParent
    full_path: Optional[str] = None
    work_item_iid: Optional[int] = None
    id: Optional[str] = None
    full_data: Optional[dict] = None


class HealthStatus(str, Enum):
    ON_TRACK = "onTrack"
    NEEDS_ATTENTION = "needsAttention"
    AT_RISK = "atRisk"


DateString = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class WorkItemBaseTool(DuoBaseTool):
    unit_primitive: GitLabUnitPrimitive = GitLabUnitPrimitive.ASK_WORK_ITEM

    async def _validate_parent_url(
        self,
        url: Optional[str],
        group_id: Optional[Union[int, str]],
        project_id: Optional[Union[int, str]],
    ) -> Union[ResolvedParent, str]:
        """Resolve parent information (group or project) from URL or IDs."""
        if url:
            return self._parse_parent_work_item_url(url)
        if group_id:
            return await self._resolve_parent_path(
                parent_type="group", identifier=group_id
            )
        if project_id:
            return await self._resolve_parent_path(
                parent_type="project", identifier=project_id
            )

        return "Must provide either URL, group_id, or project_id"

    async def _validate_work_item_url(
        self,
        url: Optional[str],
        group_id: Optional[Union[int, str]],
        project_id: Optional[Union[int, str]],
        work_item_iid: Optional[int],
    ) -> Union[ResolvedWorkItem, str]:
        """Resolve work item information from URL or IDs."""
        if not work_item_iid and not url:
            return "Must provide work_item_iid if no URL is given"

        if url:
            return self._parse_work_item_url(url)

        parent = await self._validate_parent_url(
            url=None, group_id=group_id, project_id=project_id
        )

        if isinstance(parent, str):
            return parent

        if not work_item_iid:
            return "Must provide work_item_iid if no URL is given"

        return ResolvedWorkItem(parent=parent, work_item_iid=work_item_iid)

    async def _resolve_parent_path(
        self,
        parent_type: Literal["group", "project"],
        identifier: Union[int, str],
    ) -> Union[ResolvedParent, str]:
        identifier_str = str(identifier)

        if identifier_str.isdigit():
            try:
                endpoint = "projects" if parent_type == "project" else "groups"
                data = await self.gitlab_client.aget(
                    f"/api/v4/{endpoint}/{identifier_str}"
                )
                full_path = data.get(
                    "path_with_namespace" if parent_type == "project" else "full_path"
                )
                if not full_path:
                    return f"Could not resolve {parent_type} full path from ID '{identifier_str}'"
            except Exception as e:
                return f"Failed to resolve {parent_type} from ID '{identifier_str}': {str(e)}"
        else:
            full_path = identifier_str

        return ResolvedParent(
            type=parent_type,
            full_path=self._decode_path(full_path),
        )

    @staticmethod
    def _decode_path(path: str) -> str:
        """Make sure the path is safe for GraphQL (i.e., decoded slashes)."""

        return urllib.parse.unquote(path)

    def _parse_parent_work_item_url(self, url: str) -> Union[ResolvedParent, str]:
        """Parse parent work item (by group or project) from URL."""
        try:
            parent_type = GitLabUrlParser.detect_parent_type(url)

            parser_map = {
                "group": GitLabUrlParser.parse_group_url,
                "project": GitLabUrlParser.parse_project_url,
            }

            parsed_url = parser_map.get(parent_type)
            if not parsed_url:
                return f"Unknown parent type: {parent_type}"

            path = parsed_url(url, self.gitlab_host)
            return ResolvedParent(type=parent_type, full_path=self._decode_path(path))
        except GitLabUrlParseError as e:
            return f"Failed to parse parent work item URL: {e}"

    def _parse_work_item_url(self, url: str) -> Union[ResolvedWorkItem, str]:
        """Parse work item from URL."""
        if "/-/work_items/" not in url:
            return "URL is not a work item URL"

        try:
            work_item = GitLabUrlParser.parse_work_item_url(url, self.gitlab_host)

            return ResolvedWorkItem(
                parent=ResolvedParent(
                    type=work_item.parent_type,
                    full_path=self._decode_path(work_item.full_path),
                ),
                work_item_iid=work_item.work_item_iid,
            )
        except GitLabUrlParseError as e:
            return f"Failed to parse work item URL: {e}"

    @staticmethod
    def _build_work_item_input_fields(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        input_data = {}
        type_name = kwargs.get("type_name")

        if type_name in ["issue", "epic"]:
            start_and_due = {}

            for key in ["start_date", "due_date", "is_fixed"]:
                value = kwargs.get(key)
                if value is not None:
                    graphql_key = "".join(
                        part.capitalize() if i > 0 else part
                        for i, part in enumerate(key.split("_"))
                    )
                    start_and_due[graphql_key] = value

            if start_and_due:
                input_data["startAndDueDateWidget"] = start_and_due

        if kwargs.get("title") is not None:
            input_data["title"] = kwargs["title"]

        if kwargs.get("description") is not None:
            input_data["descriptionWidget"] = {"description": kwargs["description"]}

        if kwargs.get("health_status") is not None and type_name in ["issue", "epic"]:
            input_data["healthStatusWidget"] = {"healthStatus": kwargs["health_status"]}

        if kwargs.get("confidential") is not None:
            input_data["confidential"] = kwargs["confidential"]

        if kwargs.get("assignee_ids") is not None:
            input_data["assigneesWidget"] = {
                "assigneeIds": [
                    (
                        assignee
                        if isinstance(assignee, str) and assignee.startswith("gid://")
                        else f"gid://gitlab/User/{assignee}"
                    )
                    for assignee in kwargs["assignee_ids"]
                ]
            }

        # Handle labels
        if kwargs.get("add_label_ids") or kwargs.get("remove_label_ids"):
            widget = {}
            if kwargs.get("add_label_ids"):
                widget["addLabelIds"] = [
                    (
                        lid
                        if isinstance(lid, str) and lid.startswith("gid://")
                        else f"gid://gitlab/Label/{lid}"
                    )
                    for lid in kwargs["add_label_ids"]
                ]
            if kwargs.get("remove_label_ids"):
                widget["removeLabelIds"] = [
                    (
                        lid
                        if isinstance(lid, str) and lid.startswith("gid://")
                        else f"gid://gitlab/Label/{lid}"
                    )
                    for lid in kwargs["remove_label_ids"]
                ]
            input_data["labelsWidget"] = widget

        return input_data

    async def _resolve_work_item_data(
        self,
        *,
        url: Optional[str],
        group_id: Optional[str],
        project_id: Optional[str],
        work_item_iid: Optional[int],
    ) -> Union[str, ResolvedWorkItem]:
        resolved = await self._validate_work_item_url(
            url=url,
            group_id=group_id,
            project_id=project_id,
            work_item_iid=work_item_iid,
        )

        if isinstance(resolved, str):
            return resolved

        query = (
            GET_GROUP_WORK_ITEM_QUERY
            if resolved.parent.type == "group"
            else GET_PROJECT_WORK_ITEM_QUERY
        )

        variables = {
            "fullPath": resolved.parent.full_path,
            "iid": str(resolved.work_item_iid),
        }

        response = await self.gitlab_client.graphql(query, variables)
        if not isinstance(response, dict):
            return "GraphQL query returned no response or invalid format"

        root_key = "namespace" if resolved.parent.type == "group" else "project"

        if root_key not in response:
            return f"No {root_key} found in response"

        work_items = response.get(root_key, {}).get("workItems", {}).get("nodes", [])
        work_item = work_items[0] if work_items else None

        if not work_item:
            return f"Work item {resolved.work_item_iid} not found"

        work_item_id = work_item.get("id")
        if not work_item_id:
            return "Could not find work item ID"

        return ResolvedWorkItem(
            id=work_item_id,
            full_data=work_item,
            parent=resolved.parent,
        )


class ParentResourceInput(BaseModel):
    url: Optional[str] = Field(
        default=None,
        description="GitLab URL for the resource. If provided, other ID fields are not required.",
    )
    group_id: Optional[Union[int, str]] = Field(
        default=None,
        description="The ID or URL-encoded path of the group. Required if URL and project_id are not provided.",
    )
    project_id: Optional[Union[int, str]] = Field(
        default=None,
        description="The ID or URL-encoded path of the project. Required if URL and group_id are not provided.",
    )


class ListWorkItemsInput(ParentResourceInput):
    state: Optional[str] = Field(
        default=None,
        description="Filter by work item state (e.g., 'opened', 'closed', 'all'). If not set, all states are included.",
    )
    search: Optional[str] = Field(
        default=None, description="Search for work items by title or description."
    )
    author_username: Optional[str] = Field(
        default=None, description="Filter by username of the author."
    )
    created_after: Optional[str] = Field(
        default=None,
        description="Include only work items created on or after this date (ISO 8601 format).",
    )
    created_before: Optional[str] = Field(
        default=None,
        description="Include only work items created on or before this date (ISO 8601 format).",
    )
    updated_after: Optional[str] = Field(
        default=None,
        description="Include only work items updated on or after this date (ISO 8601 format).",
    )
    updated_before: Optional[str] = Field(
        default=None,
        description="Include only work items updated on or before this date (ISO 8601 format).",
    )
    due_after: Optional[str] = Field(
        default=None,
        description="Include only work items due on or after this date (ISO 8601 format).",
    )
    due_before: Optional[str] = Field(
        default=None,
        description="Include only work items due on or before this date (ISO 8601 format).",
    )
    sort: Optional[str] = Field(
        default=None,
        description="Sort results by field and direction (e.g., 'CREATED_DESC', 'UPDATED_ASC').",
    )


class ListWorkItems(WorkItemBaseTool):
    name: str = "list_work_items"
    description: str = f"""Get all work items of the requested group or project.

    {PARENT_IDENTIFICATION_DESCRIPTION}

    For example:
    - Given group_id 'namespace/group', the tool call would be:
        list_work_items(group_id='namespace/group')
    - Given project_id 'namespace/project', the tool call would be:
        list_work_items(project_id='namespace/project')
    - Given the URL https://gitlab.com/groups/namespace/group, the tool call would be:
        list_work_items(url="https://gitlab.com/groups/namespace/group")
    - Given the URL https://gitlab.com/namespace/project, the tool call would be:
        list_work_items(url="https://gitlab.com/namespace/project")
    """
    args_schema: Type[BaseModel] = ListWorkItemsInput

    async def _arun(self, **kwargs: Any) -> str:
        url = kwargs.pop("url", None)
        group_id = kwargs.pop("group_id", None)
        project_id = kwargs.pop("project_id", None)

        resolved = await self._validate_parent_url(url, group_id, project_id)
        if isinstance(resolved, str):
            return json.dumps({"error": resolved})

        query = (
            LIST_GROUP_WORK_ITEMS_QUERY
            if resolved.type == "group"
            else LIST_PROJECT_WORK_ITEMS_QUERY
        )

        variables = {
            "fullPath": resolved.full_path,
            **{k: v for k, v in kwargs.items() if v is not None},
        }

        try:
            response = await self.gitlab_client.graphql(query, variables)
            data = response.get("data", response)
            root_key = "namespace" if resolved.type == "group" else "project"

            if root_key not in data:
                return json.dumps({"error": f"No {root_key} found in response"})

            work_items = data.get(root_key, {}).get("workItems", {}).get("nodes", [])

            return json.dumps({"work_items": work_items})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: ListWorkItemsInput) -> str:
        if args.url:
            return f"List work items in {args.url}"
        if args.group_id:
            return f"List work items in group {args.group_id}"

        return f"List work items in project {args.project_id}"


class WorkItemResourceInput(ParentResourceInput):
    work_item_iid: Optional[int] = Field(
        default=None,
        description="The internal ID of the work item. Required if URL is not provided.",
    )


class GetWorkItem(WorkItemBaseTool):
    name: str = "get_work_item"
    description: str = f"""Get a single work item in a GitLab group or project.

    {WORK_ITEM_IDENTIFICATION_DESCRIPTION}

    For example:
    - Given group_id 'namespace/group' and work_item_iid 42, the tool call would be:
        get_work_item(group_id='namespace/group', work_item_iid=42)
    - Given project_id 'namespace/project' and work_item_iid 42, the tool call would be:
        get_work_item(project_id='namespace/project', work_item_iid=42)
    - Given the URL https://gitlab.com/groups/namespace/group/-/work_items/42, the tool call would be:
        get_work_item(url="https://gitlab.com/groups/namespace/group/-/work_items/42")
    - Given the URL https://gitlab.com/namespace/project/-/work_items/42, the tool call would be:
        get_work_item(url="https://gitlab.com/namespace/project/-/work_items/42")
    """
    args_schema: Type[BaseModel] = WorkItemResourceInput

    async def _arun(self, **kwargs: Any) -> str:
        resolved = await self._validate_work_item_url(
            url=kwargs.get("url"),
            group_id=kwargs.get("group_id"),
            project_id=kwargs.get("project_id"),
            work_item_iid=kwargs.get("work_item_iid"),
        )

        if isinstance(resolved, str):
            return json.dumps({"error": resolved})

        # Select the appropriate query based on parent type
        query = (
            GET_GROUP_WORK_ITEM_QUERY
            if resolved.parent.type == "group"
            else GET_PROJECT_WORK_ITEM_QUERY
        )

        variables = {
            "fullPath": resolved.parent.full_path,
            "iid": str(resolved.work_item_iid),
        }

        try:
            response = await self.gitlab_client.graphql(query, variables)
            root_key = "namespace" if resolved.parent.type == "group" else "project"

            if root_key not in response:
                return json.dumps({"error": f"No {root_key} found in response"})

            work_items = (
                response.get(root_key, {}).get("workItems", {}).get("nodes", [])
            )
            work_item = work_items[0] if work_items else None

            return json.dumps({"work_item": work_item})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: WorkItemResourceInput) -> str:
        if args.url:
            return f"Read work item {args.url}"
        if args.group_id:
            return f"Read work item #{args.work_item_iid} in group {args.group_id}"

        return f"Read work item #{args.work_item_iid} in project {args.project_id}"


class GetWorkItemNotesInput(WorkItemResourceInput):
    sort: Optional[str] = Field(
        default=None,
        description="Return work item notes sorted in asc or desc order. Default is desc.",
    )
    order_by: Optional[str] = Field(
        default=None,
        description="Return work item notes ordered by created_at or updated_at fields. Default is created_at",
    )


class GetWorkItemNotes(WorkItemBaseTool):
    name: str = "get_work_item_notes"
    description: str = f"""Get all comments (notes) for a specific work item.

    {WORK_ITEM_IDENTIFICATION_DESCRIPTION}

    For example:
    - Given group_id 'namespace/group' and work_item_iid 42, the tool call would be:
        get_work_item_notes(group_id='namespace/group', work_item_iid=42)
    - Given project_id 'namespace/project' and work_item_iid 42, the tool call would be:
        get_work_item_notes(project_id='namespace/project', work_item_iid=42)
    - Given the URL https://gitlab.com/groups/namespace/group/-/work_items/42, the tool call would be:
        get_work_item_notes(url="https://gitlab.com/groups/namespace/group/-/work_items/42")
    - Given the URL https://gitlab.com/namespace/project/-/work_items/42, the tool call would be:
        get_work_item_notes(url="https://gitlab.com/namespace/project/-/work_items/42")
    """
    args_schema: Type[BaseModel] = GetWorkItemNotesInput

    async def _arun(self, **kwargs: Any) -> str:
        url = kwargs.pop("url", None)
        group_id = kwargs.pop("group_id", None)
        project_id = kwargs.pop("project_id", None)
        work_item_iid = kwargs.pop("work_item_iid", None)

        resolved = await self._validate_work_item_url(
            url, group_id, project_id, work_item_iid
        )

        if isinstance(resolved, str):
            return json.dumps({"error": resolved})

        query = (
            GET_GROUP_WORK_ITEM_NOTES_QUERY
            if resolved.parent.type == "group"
            else GET_PROJECT_WORK_ITEM_NOTES_QUERY
        )

        variables = {
            "fullPath": resolved.parent.full_path,
            "workItemIid": str(resolved.work_item_iid),
        }

        try:
            response = await self.gitlab_client.graphql(query, variables)
            root_key = "namespace" if resolved.parent.type == "group" else "project"
            nodes = response.get(root_key, {}).get("workItems", {}).get("nodes", [])

            if not nodes:
                return json.dumps({"error": "No work item found."})

            widgets = nodes[0].get("widgets", [])
            for widget in widgets:
                if "notes" in widget:
                    notes = widget.get("notes", {}).get("nodes", [])
                    return json.dumps({"notes": notes}, indent=2)

            return json.dumps({"notes": []})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: GetWorkItemNotesInput) -> str:
        if args.url:
            return f"Read comments on work item {args.url}"
        if args.group_id:
            return f"Read comments on work item #{args.work_item_iid} in group {args.group_id}"

        return f"Read comments on work item #{args.work_item_iid} in project {args.project_id}"


class UpdateWorkItemInput(WorkItemResourceInput):
    title: Optional[str] = Field(default=None, description="Title of the work item")
    description: Optional[str] = Field(
        default=None, description="Description of the work item."
    )
    assignee_ids: Optional[List[int]] = Field(
        default=None, description="IDs of users to assign"
    )
    confidential: Optional[bool] = Field(
        default=None, description="Set to true to make the work item confidential"
    )
    start_date: Optional[DateString] = Field(
        default=None,
        description="The start date. Date time string in the format YYYY-MM-DD.",
    )
    due_date: Optional[DateString] = Field(
        default=None,
        description="The due date. Date time string in the format YYYY-MM-DD.",
    )
    is_fixed: Optional[bool] = Field(
        default=None, description="Whether the start and due dates are fixed."
    )
    health_status: Optional[HealthStatus] = Field(
        default=None,
        description="Health status of the work item. Values: 'onTrack', 'needsAttention', 'atRisk'.",
    )
    state: Optional[str] = Field(
        default=None,
        description="The state of the work item. Use 'opened' or 'closed'.",
    )
    add_label_ids: Optional[List[str]] = Field(
        default=None,
        description="Label global IDs or numeric IDs to add to the work item.",
    )
    remove_label_ids: Optional[List[str]] = Field(
        default=None,
        description="Label global IDs or numeric IDs to remove from the work item.",
    )


class UpdateWorkItem(WorkItemBaseTool):
    name: str = "update_work_item"
    description: str = f"""Update an existing work item in a GitLab group or project.

    {WORK_ITEM_IDENTIFICATION_DESCRIPTION}

    For example:
    - update_work_item(group_id='namespace/group', work_item_iid=42, title="Updated title")
    - update_work_item(project_id='namespace/project', work_item_iid=42, title="Updated title")
    - update_work_item(url="https://gitlab.com/groups/namespace/group/-/work_items/42", title="Updated title")
    - update_work_item(url="https://gitlab.com/namespace/project/-/work_items/42", title="Updated title")
    """
    args_schema: Type[BaseModel] = UpdateWorkItemInput

    async def _arun(self, **kwargs: Any) -> str:
        resolved = await self._resolve_work_item_data(
            url=kwargs.get("url"),
            group_id=kwargs.get("group_id"),
            project_id=kwargs.get("project_id"),
            work_item_iid=kwargs.get("work_item_iid"),
        )

        if isinstance(resolved, str):
            return json.dumps({"error": resolved})

        work_item_id = resolved.id

        type_name = kwargs.get("type_name") or resolved.full_data.get(
            "workItemType", {}
        ).get("name", "")
        type_name_normalized = type_name.lower()
        kwargs["type_name"] = type_name_normalized  # ensure consistent downstream use

        input_fields = self._build_work_item_input_fields(kwargs)

        state = kwargs.get("state")
        if state == "closed":
            input_fields["stateEvent"] = "CLOSE"
        elif state == "opened":
            input_fields["stateEvent"] = "REOPEN"

        variables = {
            "input": {
                "id": work_item_id,
                **input_fields,
            }
        }

        try:
            response = await self.gitlab_client.graphql(
                UPDATE_WORK_ITEM_MUTATION, variables
            )

            if "errors" in response:
                return json.dumps({"error": response["errors"]})

            updated = (
                response.get("data", {}).get("workItemUpdate", {}).get("workItem", {})
            )
            return json.dumps({"updated_work_item": updated})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: UpdateWorkItemInput) -> str:
        if args.url:
            return f"Update work item in {args.url}"
        if args.group_id:
            return f"Update work item #{args.work_item_iid} in group {args.group_id}"
        return f"Update work item #{args.work_item_iid} in project {args.project_id}"
