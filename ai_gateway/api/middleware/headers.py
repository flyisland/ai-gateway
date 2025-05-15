from pydantic import BaseModel, ConfigDict, model_validator

X_GITLAB_REALM_HEADER = "X-Gitlab-Realm"
X_GITLAB_INSTANCE_ID_HEADER = "X-Gitlab-Instance-Id"
X_GITLAB_GLOBAL_USER_ID_HEADER = "X-Gitlab-Global-User-Id"
X_GITLAB_TEAM_MEMBER_HEADER = "X-Gitlab-Is-Team-Member"
X_GITLAB_HOST_NAME_HEADER = "X-Gitlab-Host-Name"
X_GITLAB_VERSION_HEADER = "X-Gitlab-Version"
X_GITLAB_SAAS_DUO_PRO_NAMESPACE_IDS_HEADER = "X-Gitlab-Saas-Duo-Pro-Namespace-Ids"
X_GITLAB_FEATURE_ENABLED_BY_NAMESPACE_IDS_HEADER = (
    "X-Gitlab-Feature-Enabled-By-Namespace-Ids"
)
X_GITLAB_FEATURE_ENABLEMENT_TYPE_HEADER = "X-Gitlab-Feature-Enablement-Type"
X_GITLAB_MODEL_GATEWAY_REQUEST_SENT_AT = "X-Gitlab-Rails-Send-Start"
X_GITLAB_LANGUAGE_SERVER_VERSION = "X-Gitlab-Language-Server-Version"
X_GITLAB_MODEL_PROMPT_CACHE_ENABLED = "X-Gitlab-Model-Prompt-Cache-Enabled"
X_GITLAB_ENABLED_FEATURE_FLAGS = "x-gitlab-enabled-feature-flags"
X_GITLAB_CLIENT_TYPE = "X-Gitlab-Client-Type"
X_GITLAB_CLIENT_VERSION = "X-Gitlab-Client-Version"
X_GITLAB_CLIENT_NAME = "X-Gitlab-Client-Name"
X_GITLAB_INTERFACE = "X-Gitlab-Interface"


class BaseGitLabHeaders(BaseModel):
    """Base model for common GitLab headers with 4KiB size limit"""

    model_config = ConfigDict(extra='forbid')
    valid_headers: set[str] = set()
    header_values: dict[str, str] = {}  # Store the actual header values


    @model_validator(mode='after')
    def validate_valid_header_name(self):
        # Determine if the provider headers start with X_GITLAB_* 
        for header_name in self.valid_headers:
            if not header_name.startswith('X-Gitlab'):
                raise ValueError(f"Header '{header_name}' is not a valid GitLab header. Valid headers must start with 'X-Gitlab-*'. ")
        return self

    @model_validator(mode='after')
    def validate_total_size(self):
        # Calculate total size of all headers
        total_size = sum(len(key) + len(str(value)) for key, value in self.header_values.items())
        if total_size > 4 * 1024:  # 4KiB limit
            raise ValueError("Total header size exceeds 4KiB limit")
        return self