# Flow Filtering Documentation

This document describes the filtering functionality for the `ListFlows` gRPC endpoint, which allows clients to filter flows by various criteria.

## Overview

The `ListFlows` endpoint supports filtering flows by:
- **Name**: Filter by specific flow names
- **Environment**: Filter by deployment environment (e.g., "remote", "chat-partial")
- **Version**: Filter by flow version (e.g., "experimental", "v1")

## Protocol Buffer Definitions

### ListFlowsRequest

```protobuf
message ListFlowsRequest {
    ListFlowsRequestFilter filters = 1;
}
```

### ListFlowsRequestFilter

```protobuf
message ListFlowsRequestFilter {
    repeated string name = 1;        // Filter by flow names
    repeated string environment = 2; // Filter by environments
    repeated string version = 3;     // Filter by versions
}
```

## Filtering Logic

- **Within a field**: OR logic (e.g., multiple names are combined with OR)
- **Between fields**: AND logic (e.g., name AND environment filters must both match)
- **Empty filters**: If no filters are provided, all flows are returned
- **Empty arrays**: If a filter field is an empty array, it's ignored

## Examples

### List All Flows

```json
{}
```

### Filter by Environment

Filter for foundational agents (chat-partial environment):

```json
{
  "filters": {
    "environment": ["chat-partial"]
  }
}
```

### Filter by Multiple Environments

```json
{
  "filters": {
    "environment": ["remote", "chat-partial"]
  }
}
```

### Filter by Version

```json
{
  "filters": {
    "version": ["v1"]
  }
}
```

### Filter by Name

```json
{
  "filters": {
    "name": ["foundational_agent_example", "code_assistant_foundational_agent"]
  }
}
```

### Combined Filters

Filter for foundational agents with version v1:

```json
{
  "filters": {
    "environment": ["chat-partial"],
    "version": ["v1"]
  }
}
```

## Use Cases

### Foundational Agents

Foundational agents are flows designed for the AI Catalog that use the "chat-partial" environment. To retrieve all foundational agents:

```json
{
  "filters": {
    "environment": ["chat-partial"],
    "version": ["v1"]
  }
}
```

### Development vs Production Flows

Filter flows by environment to separate development and production configurations:

```json
{
  "filters": {
    "environment": ["remote"]
  }
}
```

### Version-Specific Flows

Get flows for a specific version:

```json
{
  "filters": {
    "version": ["experimental"]
  }
}
```

## Implementation Notes

- Filtering is case-sensitive
- All filter arrays support multiple values
- Filters are applied server-side for efficiency
- The response format remains the same as the unfiltered `ListFlows` response

## Error Handling

- Invalid filter values are ignored (no error is returned)
- If no flows match the filter criteria, an empty response is returned
- Malformed filter requests return a gRPC error