# CostSentinel - Product Requirements Document (PRD)

> **The first real-time GenAI cost governance framework** — intercepts every LLM API call, enforces budget policies at the infrastructure level, auto-downgrades models when approaching limits, detects anomalous spending, and generates chargeback reports per team/user/endpoint.

---

## 1. Problem Statement

GenAI costs are unpredictable and explode without warning. Current approaches are inadequate:

| Current Approach | Problem |
|---|---|
| AWS Cost Explorer | After-the-fact — you see the damage days later |
| Helicone / LangSmith | Tracks costs but doesn't enforce limits |
| Manual budget alerts | CloudWatch alarms fire too late, no automatic action |
| Per-team AWS accounts | Over-engineered, doesn't solve per-endpoint or per-user limits |
| No governance at all | Costs spiral from prompt injection, runaway agents, or dev mistakes |
| Hardcoded model selection | No dynamic routing based on budget state |

**The gap:** Tools exist to *observe* GenAI costs. Nobody has built a framework that *governs* costs in real-time with automatic enforcement at the infrastructure level — intercepting calls before they happen, routing to cheaper models when budgets are tight, and killing runaway sessions before they drain accounts.

### Who Needs This

- **Platform Teams:** Enforce GenAI budgets across all teams without trusting developers to self-police
- **Finance/FinOps:** Real-time cost attribution and chargeback reports per business unit
- **Enterprise Teams:** Compliance requirement for cost controls on AI spending
- **Startups:** Prevent a single bad prompt or agent loop from burning through runway
- **Consultants:** Demonstrate cost governance as part of production GenAI deployments

---

## 2. Vision and Positioning

> **CostSentinel is to GenAI spending what AWS IAM is to permissions** — a policy-based enforcement layer that sits between your application and LLM providers, ensuring every call respects budgets, quotas, and routing rules.

### The Key Insight

Every GenAI cost governance system needs the same components:

```
Intercept Call → Check Budget → Route Model → Execute → Track Cost → Enforce Limits → Report
```

CostSentinel provides this entire stack as a drop-in middleware layer. You define policies; it handles enforcement.

### Design Principles (Applied)

| Principle | How CostSentinel Implements It |
|---|---|
| Convention Over Configuration | Default $100/day budget, alert at 80%, block at 100% — works immediately |
| Inversion of Control | Framework intercepts all LLM calls; user writes business logic only |
| Plugin Architecture | Custom cost models, alert channels, routing strategies as plugins |
| Declarative Over Imperative | YAML policies define budgets, quotas, routing rules |
| Observable by Default | Every call logged with cost, model, tokens, latency, attribution |
| Infrastructure as Byproduct | `costsentinel deploy` provisions DynamoDB (state) + Lambda (middleware) + CloudWatch (metrics) |
| Escape Hatches | Bypass mode for emergencies; eject to raw middleware code |

---

## 3. Core Architecture

```
+------------------------------------------------------------------+
|                      CostSentinel Framework                       |
+------------------------------------------------------------------+
|                                                                    |
|  +------------------+  +------------------+  +-----------------+  |
|  |   CLI Tool       |  |  Middleware      |  |  Infra Gen      |  |
|  |  (init/deploy/   |  |  Engine          |  |  (CDK/SAM,      |  |
|  |   report/alert)  |  |  (interceptor,   |  |   Lambda,       |  |
|  |                  |  |   enforcer,      |  |   DynamoDB)     |  |
|  |                  |  |   router)        |  |                 |  |
|  +--------+---------+  +--------+---------+  +--------+--------+  |
|           |                      |                     |           |
+-----------+----------------------+---------------------+-----------+
|                      PLUGIN LAYER                                  |
|  +---------------------------------------------------------------+|
|  | Cost Models | Alert Channels | Routing Strategies | Reporters ||
|  +---------------------------------------------------------------+|
|                                                                    |
+--------------------------------------------------------------------+
|                     AWS SERVICES LAYER                              |
|  +--------+ +----------+ +--------+ +-----+ +----------+ +-----+ |
|  | Lambda | | DynamoDB | |  SNS   | | CW  | | Bedrock  | | S3  | |
|  +--------+ +----------+ +--------+ +-----+ +----------+ +-----+ |
|  +--------+ +----------+ +--------+                               |
|  |EventBr | | API GW   | |  SQS   |                               |
|  +--------+ +----------+ +--------+                               |
+--------------------------------------------------------------------+
```

### Request Lifecycle (Middleware Interception)

```
Application Code
    |
    v
[CostSentinel Middleware Intercept]
    |
    ├── [1. Budget Check] → Is caller within budget?
    │       ├── YES → continue
    │       └── NO → action (block | downgrade | alert)
    |
    ├── [2. Model Router] → Select optimal model for budget state
    │       ├── Budget > 80% remaining → use configured model
    │       ├── Budget 20-80% remaining → use configured model
    │       └── Budget < 20% remaining → downgrade to cheaper model
    |
    ├── [3. Execute LLM Call] → Forward to provider (Bedrock/OpenAI/etc)
    |
    ├── [4. Cost Calculation] → tokens × price_per_token
    |
    ├── [5. Record & Attribute] → Store in DynamoDB
    │       ├── Per-user cost
    │       ├── Per-team cost
    │       ├── Per-endpoint cost
    │       └── Per-model cost
    |
    ├── [6. Emit Metrics] → CloudWatch custom metrics
    |
    └── [7. Check Alerts] → Threshold breached?
            ├── 80% → warning notification
            └── 100% → critical notification + enforcement action
```

---

## 4. Feature Breakdown by Phase

### Phase 1: Core Middleware Engine (MVP - Weeks 1-4)

**Goal:** Drop-in middleware that tracks and enforces GenAI costs for any Lambda-based application.

| Feature | Description | Priority |
|---|---|---|
| Call interceptor | Middleware that wraps LLM provider calls (Bedrock, OpenAI) | P0 |
| Token counting | Accurate token counting for input/output per call | P0 |
| Cost calculation | Real-time cost computation using configurable pricing tables | P0 |
| Budget enforcement | Per-endpoint daily/monthly budgets with block/downgrade/alert actions | P0 |
| Cost attribution | Tag every call with user_id, team_id, endpoint, model | P0 |
| DynamoDB state | Store running cost totals with atomic increments | P0 |
| CLI: init | `costsentinel init` scaffolds project with default policies | P0 |
| CLI: report | `costsentinel report` shows cost breakdown | P0 |

**MVP Code Example:**

```python
from costsentinel import CostMiddleware, Budget, Policy

# Define budget policy
policy = Policy(
    name="production-api",
    budgets=[
        Budget(scope="endpoint", limit_daily=50.00, limit_monthly=1000.00),
        Budget(scope="user", limit_daily=5.00),
        Budget(scope="team", limit_daily=100.00),
    ],
    on_exceed="downgrade",  # block | downgrade | alert
)

# Wrap your Bedrock client
middleware = CostMiddleware(policy=policy)

@middleware.intercept
def call_llm(prompt: str, model: str = "claude-3-sonnet"):
    """Your normal LLM call — CostSentinel handles the rest."""
    response = bedrock.invoke_model(modelId=model, body=prompt)
    return response

# Or use as Lambda middleware layer
from costsentinel.lambda_layer import cost_sentinel_handler

@cost_sentinel_handler(policy="costsentinel.yaml")
def lambda_handler(event, context):
    # All Bedrock calls within this handler are automatically tracked
    result = bedrock.invoke_model(...)
    return result
```

---

### Phase 2: Smart Model Routing & Throttling (Weeks 5-8)

**Goal:** Automatically route to cheaper models when approaching budget limits.

| Feature | Description | Priority |
|---|---|---|
| Model routing engine | Auto-select model based on budget state + query complexity | P0 |
| Complexity estimator | Classify queries as simple/medium/complex for routing decisions | P0 |
| Gradual degradation | Progressive downgrade: Opus → Sonnet → Haiku as budget depletes | P0 |
| Rate limiting | Per-user, per-team requests/minute with configurable limits | P0 |
| Token quotas | Per-user daily token limits (separate from cost budgets) | P1 |
| Priority queuing | High-priority requests bypass throttling; low-priority queued | P1 |
| Warm-up detection | Detect and block prompt injection attacks that spike costs | P1 |
| Circuit breaker | Kill sessions exceeding per-request cost threshold | P0 |

**Routing Config:**

```yaml
routing:
  strategy: budget-aware  # budget-aware | quality-first | cost-optimized

  models:
    tier_1:  # Premium (budget > 50% remaining)
      model: bedrock/claude-3-5-sonnet
      cost_per_1k_input: 0.003
      cost_per_1k_output: 0.015
    tier_2:  # Standard (budget 20-50% remaining)
      model: bedrock/claude-3-sonnet
      cost_per_1k_input: 0.003
      cost_per_1k_output: 0.015
    tier_3:  # Economy (budget < 20% remaining)
      model: bedrock/claude-3-haiku
      cost_per_1k_input: 0.00025
      cost_per_1k_output: 0.00125

  thresholds:
    downgrade_at: 0.80  # Switch to cheaper model at 80% budget consumed
    block_at: 1.00      # Hard block at 100%

  circuit_breaker:
    max_cost_per_request: 0.50   # Kill any single request costing > $0.50
    max_cost_per_session: 5.00   # Kill session if cumulative cost > $5
    max_tokens_per_request: 8000 # Reject requests with > 8K input tokens
```

---

### Phase 3: Anomaly Detection & Alerts (Weeks 9-12)

**Goal:** Detect unusual spending patterns and alert before damage is done.

| Feature | Description | Priority |
|---|---|---|
| Baseline learning | Establish normal spending patterns per endpoint/user/team | P0 |
| Spike detection | Alert when spending rate exceeds 3x baseline | P0 |
| Prompt injection detection | Detect cost-amplification attacks (repeated long outputs) | P0 |
| Runaway agent detection | Detect agent loops that accumulate cost without progress | P0 |
| Multi-channel alerts | SNS, Slack, PagerDuty, email notifications | P0 |
| Alert policies | Configurable severity levels and escalation paths | P1 |
| Auto-remediation | Automatic actions on anomaly: throttle, block, kill session | P1 |
| Anomaly dashboard | Real-time anomaly visualization in CloudWatch | P1 |

**Anomaly Detection Config:**

```yaml
anomaly_detection:
  enabled: true
  baseline_window: 7d  # Learn from last 7 days

  rules:
    - name: cost-spike
      condition: "current_rate > baseline_rate * 3"
      severity: critical
      action: throttle
      notify: [ops-team]

    - name: runaway-agent
      condition: "session_cost > 2.00 AND session_duration > 300s"
      severity: warning
      action: alert
      notify: [dev-team]

    - name: prompt-injection-cost
      condition: "output_tokens > input_tokens * 10 AND cost_per_request > 0.10"
      severity: critical
      action: block
      notify: [security-team]

    - name: unusual-model-usage
      condition: "model_tier == 'tier_1' AND time.hour > 22"
      severity: info
      action: alert
      notify: [ops-team]

  alerts:
    channels:
      - type: sns
        topic_arn: "arn:aws:sns:us-east-1:123:cost-alerts"
        severity: [critical, warning]
      - type: slack
        webhook: "${SLACK_WEBHOOK_URL}"
        severity: [critical]
```

---

### Phase 4: Chargeback & Reporting (Weeks 13-16)

**Goal:** Auto-generate cost allocation reports for finance teams and business units.

| Feature | Description | Priority |
|---|---|---|
| Chargeback reports | Per-team, per-project, per-user cost allocation | P0 |
| Report scheduling | Daily/weekly/monthly automated report generation | P0 |
| Export formats | CSV, JSON, PDF report generation | P0 |
| Cost forecasting | Predict monthly spend based on current trajectory | P0 |
| Budget vs actual | Compare budgeted vs actual spend with variance analysis | P1 |
| Optimization suggestions | Identify prompts/endpoints wasting tokens | P1 |
| Showback dashboards | Self-service cost visibility per team | P1 |
| API for billing integration | REST API for integrating with internal billing systems | P2 |

**Report Config:**

```yaml
reporting:
  schedule:
    daily:
      time: "08:00"
      recipients: [ops-team@company.com]
      format: csv
    weekly:
      day: monday
      recipients: [finance@company.com, engineering-leads@company.com]
      format: pdf
    monthly:
      day: 1
      recipients: [cfo@company.com, vp-engineering@company.com]
      format: pdf

  chargeback:
    dimensions:
      - team
      - project
      - endpoint
      - model
    include_metadata: true
    currency: USD

  forecasting:
    method: linear_regression  # linear_regression | exponential_smoothing | moving_average
    horizon_days: 30
    confidence_interval: 0.95
```

---

### Phase 5: Deployment & Enterprise Features (Weeks 17-20)

| Feature | Description | Priority |
|---|---|---|
| Lambda Layer deployment | Deploy as Lambda Layer for zero-code integration | P0 |
| API Gateway integration | Cost tracking at API Gateway level (request authorizer) | P0 |
| Multi-account support | Aggregate costs across AWS accounts | P1 |
| SSO integration | Map costs to corporate identity (Cognito/SAML) | P1 |
| Compliance mode | Audit-ready logging with tamper-proof records | P1 |
| Terraform/CDK module | Infrastructure-as-code for CostSentinel deployment | P0 |
| CLI: deploy | One-command deployment of entire governance stack | P0 |
| Eject | Export raw infrastructure templates | P1 |

---

## 5. Configuration Schema (costsentinel.yaml)

```yaml
project:
  name: "my-genai-platform"
  version: "1.0.0"

# Pricing table for cost calculation
pricing:
  bedrock:
    claude-3-5-sonnet:
      input_per_1k: 0.003
      output_per_1k: 0.015
    claude-3-sonnet:
      input_per_1k: 0.003
      output_per_1k: 0.015
    claude-3-haiku:
      input_per_1k: 0.00025
      output_per_1k: 0.00125
    titan-embed-v2:
      input_per_1k: 0.0001

# Budget policies
policies:
  global:
    daily_limit: 500.00
    monthly_limit: 10000.00
    on_exceed: alert

  per_team:
    engineering:
      daily_limit: 200.00
      monthly_limit: 4000.00
      on_exceed: downgrade
    data-science:
      daily_limit: 300.00
      monthly_limit: 6000.00
      on_exceed: alert

  per_endpoint:
    /api/chat:
      daily_limit: 100.00
      on_exceed: downgrade
      max_cost_per_request: 0.25
    /api/analyze:
      daily_limit: 200.00
      on_exceed: alert
      max_cost_per_request: 1.00

  per_user:
    default:
      daily_limit: 10.00
      on_exceed: block

# Model routing
routing:
  strategy: budget-aware
  downgrade_at: 0.80
  models:
    premium: bedrock/claude-3-5-sonnet
    standard: bedrock/claude-3-sonnet
    economy: bedrock/claude-3-haiku

# Rate limiting
rate_limits:
  global: 1000/min
  per_user: 30/min
  per_team: 200/min

# Anomaly detection
anomaly_detection:
  enabled: true
  baseline_window: 7d
  spike_multiplier: 3.0
  circuit_breaker:
    max_cost_per_request: 0.50
    max_cost_per_session: 5.00

# Alerting
alerts:
  channels:
    - type: sns
      topic_arn: "arn:aws:sns:us-east-1:123:cost-alerts"
    - type: slack
      webhook: "${SLACK_WEBHOOK_URL}"

# Reporting
reporting:
  chargeback:
    enabled: true
    dimensions: [team, project, endpoint, model]
    schedule: weekly

# Observability
observability:
  metrics: cloudwatch
  namespace: "CostSentinel"
  dashboard: true

# Deployment
deployment:
  state_store: dynamodb
  table_name: "costsentinel-state"
  lambda_layer: true

environments:
  dev:
    policies.global.daily_limit: 50.00
    anomaly_detection.enabled: false
  staging:
    policies.global.daily_limit: 200.00
  prod:
    policies.global.daily_limit: 500.00
    anomaly_detection.enabled: true
```

---

## 6. Project Structure (Generated by `costsentinel init`)

```
my-cost-governance/
├── costsentinel.yaml           # Policy configuration
├── middleware/
│   ├── __init__.py
│   ├── interceptor.py         # Call interception logic
│   └── lambda_layer.py        # Lambda Layer integration
├── policies/
│   ├── __init__.py
│   ├── budget.py              # Budget enforcement
│   ├── routing.py             # Model routing rules
│   └── rate_limit.py          # Rate limiting
├── detection/
│   ├── __init__.py
│   ├── anomaly.py             # Anomaly detection engine
│   └── baseline.py            # Baseline learning
├── reporting/
│   ├── __init__.py
│   ├── chargeback.py          # Chargeback report generation
│   └── forecast.py            # Cost forecasting
├── alerts/
│   ├── __init__.py
│   ├── sns.py                 # SNS notifications
│   └── slack.py               # Slack notifications
├── infrastructure/            # Auto-generated
│   └── template.yaml
├── tests/
│   ├── test_interceptor.py
│   ├── test_budget.py
│   ├── test_routing.py
│   └── test_anomaly.py
└── README.md
```

---

## 7. CLI Commands

```bash
# Project scaffolding
costsentinel init [project-name]
costsentinel init --template enterprise    # Full enterprise config

# Policy management
costsentinel validate                       # Validate policy config
costsentinel policies list                  # Show active policies
costsentinel policies test --simulate       # Dry-run policy enforcement

# Cost monitoring
costsentinel report --today                 # Today's cost breakdown
costsentinel report --last 7d              # Last 7 days
costsentinel report --team engineering     # Per-team report
costsentinel report --format csv --output costs.csv

# Budget management
costsentinel budget status                  # Show all budget states
costsentinel budget reset --scope user --id user123  # Reset user budget
costsentinel budget adjust --team engineering --daily 300.00

# Anomaly detection
costsentinel anomalies --last 24h          # Show detected anomalies
costsentinel baseline refresh              # Recalculate baselines

# Deployment
costsentinel deploy --env dev
costsentinel deploy --env prod --approve
costsentinel status                         # Show deployment status

# Maintenance
costsentinel eject                          # Export raw infrastructure
costsentinel upgrade                        # Upgrade framework version
```

---

## 8. Integration with Substrai Ecosystem

CostSentinel integrates as a middleware layer for all other SubstrAI frameworks:

```yaml
# lambdallm.yaml
integrations:
  costsentinel:
    enabled: true
    policy: ./costsentinel.yaml
    # All LambdaLLM model calls automatically governed

# agentdeploy.yaml
integrations:
  costsentinel:
    enabled: true
    per_tenant_budgets: true
    circuit_breaker: true

# ragforge.yaml
integrations:
  costsentinel:
    enabled: true
    track_embedding_costs: true
    track_retrieval_costs: true
```

```python
# Programmatic integration
from costsentinel import CostMiddleware
from lambdallm import handler, Model

middleware = CostMiddleware.from_config("costsentinel.yaml")

@handler(model=Model.CLAUDE_3_SONNET, middleware=[middleware])
def lambda_handler(event, context):
    # CostSentinel automatically:
    # 1. Checks budget before model call
    # 2. Routes to cheaper model if budget is tight
    # 3. Records cost after call
    # 4. Alerts if thresholds breached
    result = context.invoke(prompt=event["body"]["prompt"])
    return {"statusCode": 200, "body": result}
```

---

## 9. Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python (primary), TypeScript (secondary) | Matches Lambda ecosystem |
| State store | DynamoDB | Atomic counters for concurrent budget tracking, serverless |
| Cost tracking granularity | Per-request | Enables per-user, per-team, per-endpoint attribution |
| Middleware pattern | Decorator + Lambda Layer | Zero-code integration for existing apps |
| Pricing updates | Configurable YAML + auto-fetch from AWS | Prices change; config must be updatable |
| Rate limiting | Token bucket (DynamoDB-backed) | Distributed, serverless-compatible |
| Anomaly detection | Statistical (z-score) + rule-based | No ML dependencies, fast, explainable |
| Alerting | SNS (primary) + webhook (Slack/PagerDuty) | Native AWS + universal webhook support |
| Reporting | S3 (storage) + Lambda (generation) | Serverless report generation on schedule |
| Package size | <3MB core | Minimal cold start as Lambda Layer |
| Config format | YAML (costsentinel.yaml) | Consistent with Substrai ecosystem |

---

## 10. Differentiation from Existing Tools

| Capability | AWS Cost Explorer | Helicone | LangSmith | Infracost | CostSentinel |
|---|---|---|---|---|---|
| Real-time enforcement | ❌ After-the-fact | ❌ Observe only | ❌ Observe only | ❌ IaC only | **✅ Pre-call enforcement** |
| Auto model downgrade | ❌ | ❌ | ❌ | ❌ | **✅ Budget-aware routing** |
| Per-user budgets | ❌ | ❌ | Basic | ❌ | **✅ User/team/endpoint** |
| Anomaly detection | Basic | ❌ | ❌ | ❌ | **✅ Statistical + rules** |
| Circuit breakers | ❌ | ❌ | ❌ | ❌ | **✅ Per-request + session** |
| Chargeback reports | ❌ | Basic | Basic | ❌ | **✅ Multi-dimension** |
| Rate limiting | ❌ | ❌ | ❌ | ❌ | **✅ Token bucket** |
| Lambda-native | ❌ | ❌ | ❌ | ❌ | **✅ Layer + middleware** |
| Provider agnostic | ❌ AWS only | ✅ | Partial | ❌ | **✅ Any LLM provider** |
| Open source | ❌ | ❌ | ❌ | ✅ | **✅ MIT** |
| Serverless deployment | ❌ | ❌ | ❌ | ❌ | **✅ One-command deploy** |

---

## 11. Success Metrics

| Metric | Target (6 months) | Target (12 months) |
|---|---|---|
| GitHub stars | 400+ | 2,000+ |
| PyPI weekly downloads | 800+ | 8,000+ |
| Enterprise adopters | 5+ | 20+ |
| Cost savings demonstrated | $50K+ across adopters | $500K+ |
| Conference talks | 2+ | 5+ |
| Integration time | <30 minutes | <10 minutes |
| False positive rate (anomalies) | <10% | <5% |
| Latency overhead per call | <5ms | <2ms |

---

## 12. EB1A Evidence This Generates

- **Original contribution of major significance:** First real-time GenAI cost governance framework — creates a new category of FinOps tooling specific to AI workloads
- **Published material:** "Real-Time GenAI Cost Governance: From Observation to Enforcement" — arXiv, FinOps community talks, AWS blog features
- **Judging:** Invited to review GenAI cost management standards, FinOps Foundation panels
- **Leading role:** Organizations depend on framework to prevent uncontrolled AI spending
- **High remuneration:** GenAI FinOps consulting commands premium ($300-500/hr)

### The EB1A Narrative

> "I developed CostSentinel, the first framework that enforces GenAI cost governance in real-time at the infrastructure level. Unlike observability tools that report costs after the fact, CostSentinel intercepts every LLM call, enforces per-user and per-team budgets, automatically routes to cheaper models when limits approach, and detects cost-amplification attacks. The framework has prevented an average of $X/month in uncontrolled GenAI spending across Y enterprise deployments, establishing a new standard for AI cost governance."

---

## 13. Go-to-Market Timeline

| Month | Action | Milestone |
|---|---|---|
| Month 1-2 | Build core middleware + budget enforcement + cost tracking | MVP: drop-in cost governance |
| Month 2-3 | Smart model routing + rate limiting + circuit breakers | Budget-aware auto-downgrade |
| Month 3-4 | Anomaly detection + multi-channel alerts | Proactive cost protection |
| Month 4-5 | Chargeback reports + forecasting + dashboards | Enterprise FinOps ready |
| Month 5-6 | Blog: "Why Your GenAI Costs Will Explode (And How to Prevent It)" | Published material |
| Month 6-7 | arXiv paper on real-time AI cost governance patterns | Academic credibility |
| Month 7-8 | Conference talk: "From $10K Surprise Bills to Predictable AI Costs" | Speaking evidence |
| Month 8-9 | Enterprise pilot (3-5 organizations) | Adoption evidence |

---

## 14. Getting Started (Day 1 Action Plan)

```bash
# 1. Create the repository
gh repo create substrai/costsentinel --public \
  --description "Real-time GenAI cost governance framework"

# 2. Set up Python project
mkdir -p src/costsentinel/{core,middleware,policies,detection,reporting,alerts,cli}
touch src/costsentinel/__init__.py

# 3. Start with these files (the heart of the framework):
# src/costsentinel/core/config.py          — Policy config parser
# src/costsentinel/core/pricing.py         — Token pricing engine
# src/costsentinel/middleware/interceptor.py — Call interception decorator
# src/costsentinel/policies/budget.py      — Budget enforcement logic
# src/costsentinel/policies/routing.py     — Model routing engine
# src/costsentinel/policies/rate_limit.py  — Rate limiting (token bucket)
# src/costsentinel/detection/anomaly.py    — Anomaly detection engine
# src/costsentinel/reporting/chargeback.py — Report generation
# src/costsentinel/alerts/notifier.py      — Multi-channel notifications
# src/costsentinel/cli/main.py             — CLI entry point

# 4. Write first test
mkdir tests && touch tests/test_interceptor.py
```

**First file to write:** `src/costsentinel/middleware/interceptor.py` — the call interception decorator that wraps LLM provider calls with cost tracking and budget enforcement.

---

*This PRD is a living document. Update it as you build, learn, and get community feedback.*
