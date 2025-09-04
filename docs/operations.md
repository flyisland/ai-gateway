# Operations

Useful links to the ai-gateway [Runbook](https://gitlab.com/gitlab-com/runbooks/-/blob/master/docs/ai-gateway/README.md)

- [Service Overview](https://gitlab.com/gitlab-com/runbooks/-/blob/master/docs/ai-gateway/README.md#ai-gateway-service)
- [Monitoring and Alerting](https://gitlab.com/gitlab-com/runbooks/-/blob/master/docs/ai-gateway/README.md#monitoringalerting)
- [GCP Quotas usage and request process](https://gitlab.com/gitlab-com/runbooks/-/blob/master/docs/ai-gateway/README.md#gcp-quotas-usage)

## LLM Metrics and Monitoring

The Duo Workflow Service exposes comprehensive metrics for monitoring LLM performance and reliability:

### Key LLM Metrics

- **`duo_workflow_llm_request_seconds`**: Duration of LLM requests with labels:
  - `model`: The LLM model used (e.g., "claude-3-5-sonnet")
  - `request_type`: Type of request (e.g., "completion", "chat")
  - `http_status_code`: HTTP status code from the LLM response
  - `overload_indicator`: "true" if the request encountered overload conditions, "false" otherwise

- **`duo_workflow_llm_response_total`**: Count of LLM responses with labels:
  - `model`: The LLM model used
  - `request_type`: Type of request
  - `stop_reason`: Reason the LLM stopped generating (e.g., "end_turn", "max_tokens")
  - `http_status_code`: HTTP status code from the LLM response
  - `overload_indicator`: "true" if the response indicates overload, "false" otherwise

### Overload Detection

The service automatically detects overload conditions based on:
- HTTP 429 (Too Many Requests) status codes
- Error types indicating overload
- Error messages containing keywords like "overload", "rate limit", "quota", or "throttle"

### Error Filtering

Sentry error tracking is configured to filter out handled errors to reduce monitoring noise:
- Rate limiting errors (429 status codes)
- Overload and throttling errors
- Timeout errors that are automatically retried
- Authentication errors (401 status codes)
- Errors marked with `handled=true` or `expected=true` tags

### Grafana Dashboard

LLM metrics are automatically included in the [Duo Workflow Service Grafana dashboard](https://dashboards.gitlab.net/d/duo-workflow-svc-main/duo-workflow-svc3a-overview) with dashboard definitions maintained in the [runbooks repository](https://gitlab.com/gitlab-com/runbooks/-/blob/master/metrics-catalog/services/duo-workflow-svc.jsonnet).
