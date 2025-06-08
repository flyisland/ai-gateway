import json
from typing import Any, List, NamedTuple, Optional, Type
from urllib.parse import unquote

from pydantic import BaseModel, Field

from duo_workflow_service.gitlab.url_parser import GitLabUrlParseError, GitLabUrlParser
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool
from duo_workflow_service.tools.gitlab_resource_input import ProjectResourceInput

PROJECT_IDENTIFICATION_DESCRIPTION = """To identify the project you must provide either:
- project_id parameter, or
- A GitLab URL like:
  - https://gitlab.com/namespace/project
  - https://gitlab.com/group/subgroup/project
"""

class ListVulnerabilitiesInput(ProjectResourceInput):
    severity: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by severity. Possible values: critical, high, medium, low, unknown, info.",
    )
    confidence: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by confidence. Possible values: confirmed, high, medium, low, unknown, experimental.",
    )
    report_type: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by report type. Possible values: sast, dependency_scanning, container_scanning, dast, secret_detection, coverage_fuzzing, api_fuzzing.",
    )
    state: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by state. Possible values: detected, confirmed, dismissed, resolved.",
    )
    scanner: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by scanner.",
    )
    scanner_id: Optional[str] = Field(
        default=None,
        description="Filter vulnerabilities by scanner ID.",
    )
    has_resolution: Optional[bool] = Field(
        default=None,
        description="Filter vulnerabilities by whether they have a resolution.",
    )
    has_issues: Optional[bool] = Field(
        default=None,
        description="Filter vulnerabilities by whether they have issues.",
    )
    include_false_positives: Optional[bool] = Field(
        default=None,
        description="Include false positives in the results.",
    )

class ListVulnerabilities(DuoBaseTool):
    name: str = "list_vulnerabilities"
    description: str = f"""List security vulnerabilities in a GitLab project using GraphQL API.

    {PROJECT_IDENTIFICATION_DESCRIPTION}

    For example:
    - Given project_id 13, the tool call would be:
        list_vulnerabilities(project_id=13)
    - Given the URL https://gitlab.com/namespace/project, the tool call would be:
        list_vulnerabilities(url="https://gitlab.com/namespace/project")
    """
    args_schema: Type[BaseModel] = ListVulnerabilitiesInput  # type: ignore

    def _convert_rest_filters_to_graphql(self, filters: dict) -> dict:
        """Convert REST API filter parameters to GraphQL format."""
        graphql_filters = {}

        # Map REST API parameter names to GraphQL enum values
        if "severity" in filters and filters["severity"]:
            graphql_filters["severity"] = [filters["severity"].upper()]

        if "state" in filters and filters["state"]:
            # Map REST states to GraphQL states
            state_mapping = {
                "detected": "DETECTED",
                "confirmed": "CONFIRMED",
                "dismissed": "DISMISSED",
                "resolved": "RESOLVED"
            }
            rest_state = filters["state"].lower()
            if rest_state in state_mapping:
                graphql_filters["state"] = [state_mapping[rest_state]]

        if "report_type" in filters and filters["report_type"]:
            # Map REST report types to GraphQL enum values
            report_type_mapping = {
                "sast": "SAST",
                "dependency_scanning": "DEPENDENCY_SCANNING",
                "container_scanning": "CONTAINER_SCANNING",
                "dast": "DAST",
                "secret_detection": "SECRET_DETECTION",
                "coverage_fuzzing": "COVERAGE_FUZZING",
                "api_fuzzing": "API_FUZZING"
            }
            rest_type = filters["report_type"].lower()
            if rest_type in report_type_mapping:
                graphql_filters["reportType"] = [report_type_mapping[rest_type]]

        if "scanner" in filters and filters["scanner"]:
            graphql_filters["scanner"] = [filters["scanner"]]

        if "has_resolution" in filters and filters["has_resolution"] is not None:
            graphql_filters["hasResolution"] = filters["has_resolution"]

        if "has_issues" in filters and filters["has_issues"] is not None:
            graphql_filters["hasIssues"] = filters["has_issues"]

        if "include_false_positives" in filters and filters["include_false_positives"] is not None:
            graphql_filters["includeFalsePositives"] = filters["include_false_positives"]

        return graphql_filters

    def _build_graphql_query(self, project_path: str, filters: dict) -> str:
        """Build GraphQL query for project vulnerabilities."""

        # Build filter arguments
        filter_args = []
        if "severity" in filters:
            severity_list = ", ".join([f'"{s}"' for s in filters["severity"]])
            filter_args.append(f"severity: [{severity_list}]")

        if "state" in filters:
            state_list = ", ".join([f'"{s}"' for s in filters["state"]])
            filter_args.append(f"state: [{state_list}]")

        if "reportType" in filters:
            report_type_list = ", ".join([f'"{rt}"' for rt in filters["reportType"]])
            filter_args.append(f"reportType: [{report_type_list}]")

        if "scanner" in filters:
            scanner_list = ", ".join([f'"{s}"' for s in filters["scanner"]])
            filter_args.append(f"scanner: [{scanner_list}]")

        if "hasResolution" in filters:
            filter_args.append(f"hasResolution: {str(filters['hasResolution']).lower()}")

        if "hasIssues" in filters:
            filter_args.append(f"hasIssues: {str(filters['hasIssues']).lower()}")

        if "includeFalsePositives" in filters:
            filter_args.append(f"includeFalsePositives: {str(filters['includeFalsePositives']).lower()}")

        # Always add pagination
        filter_args.append("first: 100")

        filter_string = ", ".join(filter_args)

        query = f"""
        query getProjectVulnerabilities {{
            project(fullPath: "{project_path}") {{
                id
                name
                fullPath
                vulnerabilities({filter_string}) {{
                    nodes {{
                        id
                        title
                        description
                        severity
                        state
                        confidence
                        reportType
                        scanner {{
                            name
                            vendor
                            externalId
                        }}
                        identifiers {{
                            name
                            value
                            type
                            externalType
                            externalId
                            url
                        }}
                        location {{
                            ... on VulnerabilityLocationSast {{
                                file
                                startLine
                                endLine
                                vulnerableClass
                                vulnerableMethod
                            }}
                            ... on VulnerabilityLocationDependencyScanning {{
                                file
                                dependency {{
                                    package {{
                                        name
                                    }}
                                    version
                                }}
                            }}
                            ... on VulnerabilityLocationContainerScanning {{
                                file
                                image
                                operatingSystem
                            }}
                            ... on VulnerabilityLocationDast {{
                                hostname
                                path
                                requestMethod
                            }}
                            ... on VulnerabilityLocationSecretDetection {{
                                file
                                startLine
                                endLine
                                vulnerableClass
                                vulnerableMethod
                            }}
                        }}
                        project {{
                            id
                            name
                            fullPath
                        }}
                        detectedAt
                        createdAt
                        updatedAt
                        dismissedAt
                        dismissedBy {{
                            id
                            name
                            username
                        }}
                        resolvedAt
                        resolvedBy {{
                            id
                            name
                            username
                        }}
                        confirmedAt
                        confirmedBy {{
                            id
                            name
                            username
                        }}
                        falsePositive
                        hasIssues
                        hasResolution
                        hasSolutions
                        userNotesCount
                        vulnerabilityPath
                        links {{
                            name
                            url
                        }}
                    }}
                    pageInfo {{
                        hasNextPage
                        hasPreviousPage
                        startCursor
                        endCursor
                    }}
                    count: totalCount
                }}
            }}
        }}
        """
        return query.strip()

    async def _arun(self, **kwargs: Any) -> str:
        url = kwargs.pop("url", None)
        project_id = kwargs.pop("project_id", None)

        project_id, errors = self._validate_project_url(url, project_id)

        if errors:
            return json.dumps({"error": "; ".join(errors)})

        # For GraphQL, we need to decode the URL-encoded project path
        # The URL parser returns URL-encoded paths for REST API compatibility,
        # but GraphQL expects normal paths
        if project_id:
            project_path = unquote(str(project_id))
        else:
            return json.dumps({"error": "No valid project path found"})

        # Remove None values and prepare filters
        filters = {k: v for k, v in kwargs.items() if v is not None}

        # Convert REST-style filters to GraphQL format
        graphql_filters = self._convert_rest_filters_to_graphql(filters)

        try:
            # Build GraphQL query
            query = self._build_graphql_query(project_path, graphql_filters)

            # Execute GraphQL query using the existing HTTP client
            graphql_body = {
                "query": query
            }

            response = await self.gitlab_client.apost(
                path="/api/graphql",
                body=json.dumps(graphql_body),
                parse_json=True,
            )

            # Extract vulnerabilities from GraphQL response
            if "data" in response and response["data"] and "project" in response["data"]:
                project_data = response["data"]["project"]
                if project_data and "vulnerabilities" in project_data:
                    vulnerabilities = project_data["vulnerabilities"]["nodes"]
                    return json.dumps({
                        "vulnerabilities": vulnerabilities,
                        "project": {
                            "id": project_data.get("id"),
                            "name": project_data.get("name"),
                            "fullPath": project_data.get("fullPath")
                        },
                        "pagination": project_data["vulnerabilities"]["pageInfo"],
                        "total_count": project_data["vulnerabilities"]["count"]
                    })
                else:
                    return json.dumps({
                        "vulnerabilities": [],
                        "error": "Project not found or no vulnerabilities available"
                    })
            elif "errors" in response:
                return json.dumps({"error": f"GraphQL errors: {response['errors']}"})
            else:
                return json.dumps({"error": "Unexpected GraphQL response format"})

        except Exception as e:
            return json.dumps({"error": str(e)})

    def format_display_message(self, args: ListVulnerabilitiesInput) -> str:
        if args.url:
            return f"List vulnerabilities in {args.url} (using GraphQL)"
        return f"List vulnerabilities in project {args.project_id} (using GraphQL)"
