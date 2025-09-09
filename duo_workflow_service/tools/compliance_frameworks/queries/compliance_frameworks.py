LIST_NAMESPACE_COMPLIANCE_FRAMEWORKS_QUERY = """
query ListNamespaceComplianceFrameworks($fullPath: ID!, $first: Int, $after: String) {
    namespace(fullPath: $fullPath) {
        id
        fullPath
        name
        complianceFrameworks(first: $first, after: $after) {
            pageInfo {
                hasNextPage
                endCursor
            }
            nodes {
                id
                name
                description
                color
                default
                pipelineConfigurationFullPath
                updatedAt
                projects {
                    count
                }
            }
        }
    }
}
"""

GET_COMPLIANCE_FRAMEWORK_FULL_DETAILS_QUERY = """
query GetComplianceFrameworkFullDetails($id: ComplianceMgmtFrameworkID!) {
    complianceFramework(id: $id) {
        id
        name
        description
        color
        default
        pipelineConfigurationFullPath
        namespace {
            id
            fullPath
            name
        }
        createdAt
        updatedAt
        projects {
            count
        }
        complianceRequirements {
            count
            nodes {
                id
                name
                description
                complianceRequirementsControls {
                    count
                    nodes {
                        id
                        name
                        description
                        createdAt
                        updatedAt
                    }
                }
            }
        }
    }
}
"""

GET_PROJECT_COMPLIANCE_FRAMEWORKS_QUERY = """
query GetProjectComplianceFrameworks($fullPath: ID!) {
    project(fullPath: $fullPath) {
        id
        name
        fullPath
        complianceFrameworks {
            count
            nodes {
                id
                name
                description
                default
                color
                complianceRequirements {
                    count
                }
            }
        }
    }
}
"""