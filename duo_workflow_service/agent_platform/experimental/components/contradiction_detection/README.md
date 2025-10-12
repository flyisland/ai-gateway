# Contradiction Detection Component

This component uses **Claude LLM** to intelligently detect contradictions between `title` and `description` attributes in JSON tool responses, **with a focus on security and data integrity issues**.

## Overview

The contradiction detection component leverages Claude's reasoning capabilities to identify logical contradictions in tool responses that could indicate security problems, data corruption, or system integrity issues:

- **Sentiment contradictions**: Title says "success" but description mentions "failure"
- **Action contradictions**: Title says "create" but description mentions "delete"
- **Factual contradictions**: Title and description contain conflicting facts
- **Outcome contradictions**: Title and description describe opposite outcomes
- **Security contradictions**: ⚠️ Contradictions indicating potential security issues:
  - Data integrity problems (corruption or tampering)
  - Authorization failures (contradictory permission states)
  - Security state conflicts (secure vs unsecured)
  - Audit trail inconsistencies
  - API response tampering
  - Input validation bypasses

## How It Works

Instead of simple keyword matching, this component uses Claude (Haiku 4.0 by default) to:

1. Analyze the semantic meaning of both title and description
2. Identify logical contradictions with confidence scoring
3. Provide detailed explanations of detected contradictions
4. Only flag genuine contradictions (confidence ≥ 0.7)

## Usage

### Environment Configuration

The contradiction detection feature is controlled by environment variables:

```bash
# Enable contradiction detection (default: false)
DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION=true

# Model to use for analysis (default: claude-haiku-4.0)
DUO_WORKFLOW_CONTRADICTION_DETECTION_MODEL=claude-haiku-4.0
```

Add this to your `.env` file to enable the feature globally.

### Integration Options

#### Option 1: Automatic Integration (Recommended)

When the environment variable is enabled, contradiction detection is automatically inserted into **all** `AgentComponent` workflows:

```yaml
# No special configuration needed - just use AgentComponent normally
components:
  - name: "my_agent"
    type: AgentComponent
    prompt_id: "assistant"
    toolset:
      - "get_issue"
      - "create_issue"
    # Contradiction detection automatically enabled if env var is set
```

**Flow**: `Agent → Tools → Claude Contradiction Detection → Agent`

#### Option 2: Standalone Component

Use the contradiction detection component independently with custom configuration:

```yaml
components:
  - name: "contradiction_checker"
    type: ContradictionDetectionComponent
    # Optional configuration (shows defaults)
    model_name: "claude-haiku-4.0"  # Claude model to use
    temperature: 0.0  # Temperature for deterministic results
    max_tokens: 1024  # Maximum tokens for LLM response
    confidence_threshold: 0.7  # Minimum confidence to flag contradictions
    inputs:
      - from: "conversation_history"
```

### Available Models

| Model | Speed | Cost | Use Case |
|-------|-------|------|----------|
| `claude-haiku-4.0` | ⚡ Fast | 💰 Low | **Default** - Fast contradiction detection |
| `claude-sonnet-4.0` | 🏃 Medium | 💰💰 Medium | More nuanced analysis |
| `claude-opus-4.0` | 🐢 Slow | 💰💰💰 High | Highest accuracy (rarely needed) |

Configure the model in your YAML config:

```yaml
components:
  - name: "my_contradiction_detector"
    type: ContradictionDetectionComponent
    model_name: "claude-sonnet-4.0"  # Use Sonnet for better accuracy
    confidence_threshold: 0.8  # Require higher confidence
```

## What It Detects

The component analyzes JSON tool responses for fields like:

- **Title fields**: `title`, `name`, `subject`, `heading`
- **Description fields**: `description`, `desc`, `summary`, `content`, `body`

### Example Contradictions

```json
{
  "title": "Task Completed Successfully",
  "description": "The operation failed with multiple errors"
  // ❌ Claude detects sentiment contradiction
}
```

**Claude's Analysis:**
```json
{
  "has_contradiction": true,
  "confidence": 0.95,
  "contradiction_type": "sentiment",
  "explanation": "Title indicates success while description explicitly states failure",
  "title_meaning": "Conveys successful completion",
  "description_meaning": "Describes failure with errors",
  "security_relevance": "medium"
}
```

### Security-Relevant Contradiction Example

```json
{
  "title": "User Authentication Successful",
  "description": "Authorization check failed - access denied"
  // ⚠️ HIGH SECURITY RELEVANCE - Authorization bypass indicator
}
```

**Claude's Security-Focused Analysis:**
```json
{
  "has_contradiction": true,
  "confidence": 0.98,
  "contradiction_type": "security",
  "explanation": "Title claims successful authentication but description indicates authorization failure - potential security bypass",
  "title_meaning": "User successfully authenticated",
  "description_meaning": "User authorization failed",
  "security_relevance": "high"
}
```

## Output Format

Analysis results are stored in the workflow context with detailed explanations:

```python
{
  "context": {
    "component_name": {
      "contradiction_analysis": {
        "contradictions_found": [
          {
            "tool_call_id": "call_123",
            "path": "results[0]",
            "title": "Task Completed Successfully",
            "description": "The operation failed with multiple errors",
            "contradiction_type": "sentiment",
            "confidence": 0.95,
            "explanation": "Title indicates success while description explicitly states failure",
            "title_meaning": "Conveys successful completion",
            "description_meaning": "Describes failure with errors",
            "security_relevance": "medium"
          }
        ],
        "total_responses_analyzed": 3,
        "has_contradictions": true,
        "security_relevant_contradictions": 1
      }
    }
  }
}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DUO_WORKFLOW_ENABLE_CONTRADICTION_DETECTION` | `false` | Enable/disable automatic contradiction detection in AgentComponent |
| `DUO_WORKFLOW_CONTRADICTION_DETECTION_MODEL` | `claude-haiku-4.0` | Model for automatic AgentComponent integration (standalone components use YAML config) |

### Component Configuration (YAML)

When using the standalone `ContradictionDetectionComponent`, configure it in your flow YAML:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | string | `claude-haiku-4.0` | Claude model to use |
| `temperature` | float | `0.0` | LLM temperature (0.0 for deterministic) |
| `max_tokens` | int | `1024` | Maximum tokens for LLM response |
| `confidence_threshold` | float | `0.7` | Minimum confidence to flag contradictions (0.0-1.0) |

### System Prompt

The component uses a carefully crafted system prompt to ensure Claude:
- Only flags CLEAR contradictions
- Provides confidence scores
- Gives detailed explanations
- Avoids false positives from complementary information

### Logging

Detected contradictions are logged with different severity levels based on security relevance:

**Security-Relevant Contradictions (ERROR level):**
Logs contradictions with `security_relevance` of "critical", "high", or "medium":
```
2024-01-01 [error] Found 2 SECURITY-RELEVANT contradictions in tool responses
security_contradictions=[
  {
    "title": "User Authentication Successful",
    "description": "Authorization check failed",
    "confidence": 0.98,
    "contradiction_type": "prompt_injection",
    "security_relevance": "critical",
    "explanation": "Potential authorization bypass through prompt injection"
  }
]
total_contradictions=3
```

**General Contradictions (WARNING level):**
Logs contradictions with `security_relevance` of "low" or null:
```
2024-01-01 [warning] Found 2 contradictions in tool responses
contradictions=[
  {
    "title": "Task Successful",
    "description": "Task failed",
    "confidence": 0.95,
    "security_relevance": "low"
  }
]
```

## Performance

- **Haiku 4.0**: ~200-500ms per contradiction check
- **Confidence threshold**: 0.7 (only flags high-confidence contradictions)
- **LLM caching**: Instance-level caching for efficiency
- **Temperature**: 0.0 for deterministic results

## Development

### Running Tests

```bash
poetry run python -m pytest tests/duo_workflow_service/agent_platform/experimental/components/contradiction_detection/
```

### Modifying the System Prompt

To adjust contradiction detection behavior, edit `CONTRADICTION_DETECTION_SYSTEM_PROMPT` in `node.py`:

```python
CONTRADICTION_DETECTION_SYSTEM_PROMPT = """You are a contradiction detection expert...
```

### Adjusting Confidence Threshold

Change the confidence threshold in `node.py:289`:

```python
if result.get("has_contradiction") and result.get("confidence", 0) >= 0.7:
    return result
```

## Benefits of LLM-Based Detection

✅ **Semantic Understanding**: Understands meaning, not just keywords
✅ **Context Aware**: Considers full context of both title and description
✅ **Fewer False Positives**: Distinguishes contradictions from complementary info
✅ **Explainable**: Provides clear explanations for each detection
✅ **Configurable**: Easily adjust confidence thresholds and prompts

## Cost Considerations

With Haiku 4.0 (default):
- ~150 tokens per analysis
- Cost: ~$0.000015 per contradiction check
- For 1000 tool responses/day: ~$0.015/day (~$5.50/year)