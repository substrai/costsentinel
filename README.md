# CostSentinel

**AI cost governance middleware** — budget enforcement, attribution, and reporting for LLM API calls.

CostSentinel sits between your application and LLM providers, tracking every token spent, enforcing budget policies, and attributing costs to teams, users, and endpoints. Zero external dependencies beyond PyYAML.

## Features

- **Token Cost Tracking** — Automatic cost calculation for Claude, Titan, and custom models
- **Budget Enforcement** — Daily/monthly limits with configurable actions (block, downgrade, alert)
- **Cost Attribution** — Track spending by team, user, endpoint, and model
- **Middleware Pattern** — Decorator-based interception or manual tracking
- **Reporting** — CLI and programmatic cost breakdowns
- **Zero Infrastructure** — JSON file storage for development; DynamoDB-ready for production

## Installation

```bash
pip install substrai-costsentinel
```

For AWS integration (DynamoDB state backend):
```bash
pip install substrai-costsentinel[aws]
```

For development:
```bash
pip install substrai-costsentinel[dev]
```

## Quickstart

### 1. Initialize Configuration

```bash
costsentinel init
```

This creates `costsentinel.yaml` with default policies:

```yaml
project_name: my-project

pricing:
  claude-3.5-sonnet:
    input: 0.003
    output: 0.015
  claude-3-haiku:
    input: 0.00025
    output: 0.00125

policies:
  global:
    limit_daily: 100.0
    limit_monthly: 2000.0
    on_exceed: block
  team:
    limit_daily: 25.0
    on_exceed: downgrade
  user:
    limit_daily: 5.0
    on_exceed: block
    max_cost_per_request: 0.50
```

### 2. Add Middleware to Your Code

```python
from costsentinel import CostMiddleware

middleware = CostMiddleware("costsentinel.yaml")

@middleware.intercept(model="claude-3-haiku", user_id="user-1", team_id="engineering")
def call_llm(prompt):
    # Your LLM call here
    response = my_llm_client.complete(prompt)
    return response.text, response.input_tokens, response.output_tokens

# Returns CallResult with cost info
result = call_llm("Summarize this document...")
print(f"Cost: ${result.cost:.4f}, Remaining: ${result.budget_remaining:.2f}")
```

### 3. Manual Tracking

```python
from costsentinel import CostMiddleware

middleware = CostMiddleware("costsentinel.yaml")

# After an LLM call completes
result = middleware.track_call(
    model="claude-3.5-sonnet",
    input_tokens=1500,
    output_tokens=800,
    metadata={"user_id": "user-1", "team_id": "engineering", "endpoint": "/api/chat"}
)
```

### 4. Check Reports

```bash
costsentinel report --today
costsentinel budget status
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Your Application                │
├─────────────────────────────────────────────────┤
│              CostSentinel Middleware             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Pricing  │  │  Budget  │  │ Attribution  │  │
│  │ Engine   │  │ Enforcer │  │    Store     │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│  ┌──────────────────────────────────────────┐   │
│  │            State Management              │   │
│  │     (JSON file / DynamoDB backend)       │   │
│  └──────────────────────────────────────────┘   │
├─────────────────────────────────────────────────┤
│              LLM Provider (Bedrock)              │
└─────────────────────────────────────────────────┘
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `costsentinel init` | Create default configuration |
| `costsentinel report --today` | Show today's cost breakdown |
| `costsentinel budget status` | Display budget utilization |
| `costsentinel budget reset --scope user --id user-1` | Reset a budget counter |
| `costsentinel validate` | Validate configuration file |
| `costsentinel status` | Show overall status |

## Budget Policies

Policies are evaluated from most specific to least specific:

1. **User** — Per-user daily/monthly limits
2. **Endpoint** — Per-API-endpoint limits
3. **Team** — Per-team limits
4. **Global** — Organization-wide limits

Actions when budget is exceeded:
- `block` — Reject the request with `BudgetExceededError`
- `downgrade` — Signal to use a cheaper model
- `alert` — Allow but emit a warning

## Development

```bash
git clone https://github.com/substrai/costsentinel.git
cd costsentinel
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT — Copyright (c) 2024 Gaurav Kumar Sinha
