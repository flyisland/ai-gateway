import os

import requests
from locust import HttpUser, between, tag, task


class FastAPILoadTest(HttpUser):
    wait_time = between(10, 20)
    host = "http://placeholder"  # Placeholder to satisfy Locust

    def on_start(self):
        """Set host dynamically based on ENV and authenticate if needed."""
        env = os.getenv("ENV", "dev")  # Default to 'dev' if not provided
        env_config = self.get_env_config(env)

        self.environment.host = env_config["aigw_host"]
        print(f"Running tests against: {self.environment.host}")

        # Authenticate only if not in dev environment
        if env != "dev":
            self.authenticate(env_config["auth_host"])

    def get_env_config(self, env):
        """Retrieve environment-specific configuration."""
        env_mapping = {
            "dev": {"aigw_host": "http://127.0.0.1:5052"},
            "staging": {
                "aigw_host": "https://cloud.staging.gitlab.com/ai",
                "auth_host": "https://staging.gitlab.com",
            },
            "prod": {
                "aigw_host": "https://cloud.gitlab.com/ai",
                "auth_host": "https://gitlab.com",
            },
        }

        if env not in env_mapping:
            raise ValueError(
                f"ERROR: Unknown environment '{env}'. Choose from: {list(env_mapping.keys())}"
            )

        return env_mapping[env]

    def authenticate(self, auth_host):
        """Authenticate and store the access token."""
        token = os.getenv("GITLAB_TOKEN")
        if not token:
            raise EnvironmentError("ERROR: GITLAB_TOKEN environment variable not set!")

        auth_url = f"{auth_host}/api/v4/code_suggestions/direct_access"
        headers = {"Authorization": f"Bearer {token}"}

        response = requests.post(auth_url, headers=headers)
        if response.status_code >= 400:
            raise EnvironmentError(
                f"Authentication failed: {response.status_code}, {response.text}"
            )

        # Parse JSON response
        auth_data = response.json()
        self.access_token = auth_data.get("token")
        self.expires_at = auth_data.get("expires_at")
        self.global_user_id = auth_data.get("headers", {}).get(
            "X-Gitlab-Global-User-Id"
        )

        print(f"Authenticated! Token Expires: {self.expires_at}")

    @tag("code_completion")
    @task
    def code_completion_v2(self):
        """Test the code completion endpoint."""
        headers = self.get_headers()
        body = {
            "current_file": {
                "file_name": "test",
                "content_above_cursor": "func hello_world(){\n\t",
                "content_below_cursor": "\n}",
                "stream": False,
            },
            "prompt_version": 1,
            "metadata": {"source": "Gitlab EE", "version": "16.3"},
        }
        # response = requests.post(f"{self.environment.host}/v2/code/completions", headers=headers, json=body)
        # import pdb;pdb.set_trace()
        self.client.post(
            f"{self.environment.host}/v2/code/completions", headers=headers, json=body
        )

    def get_headers(self):
        """Construct request headers for API requests."""
        if os.getenv("ENV", "dev")=="dev":
          return {
            "Content-Type": "application/json",
          }

        gitlab_instance_id = os.getenv(
            "GITLAB_INSTANCE_ID", "ea8bf810-1d6f-4a6a-b4fd-93e8cbd8b57f"
        )
        gitlab_version = os.getenv("GITLAB_VERSION", "17.8.0")

        return {
            "Content-Type": "application/json",
            "X-Gitlab-Authentication-Type": "oidc",
            "Authorization": f"Bearer {self.access_token}",
            "X-Gitlab-Host-Name": "gitlab.com",
            "X-Gitlab-Instance-Id": gitlab_instance_id,
            "X-Gitlab-Realm": "saas",
            "X-Gitlab-Version": gitlab_version,
            "X-Gitlab-Global-User-Id": self.global_user_id,
        }
