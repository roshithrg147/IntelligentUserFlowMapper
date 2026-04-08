# Intelligent User Flow Mapper (Enterprise Edition)

[![CI/CD Pipeline](https://github.com/roshithrg147/IntelligentUserFlowMapper/actions/workflows/ci.yml/badge.svg)](https://github.com/roshithrg147/IntelligentUserFlowMapper/actions)
[![Production Status](https://img.shields.io/badge/Status-Production--Ready-brightgreen)](https://user-flow-mapper-692503525427.us-central1.run.app/health/ready)

**Intelligent User Flow Mapper** is a production-grade, asynchronous UI discovery engine. It intelligently explores web applications, bypasses navigation noise, and extracts meaningful user journeys into structured, AI-ready graph data.

---

## 🚀 Key Enterprise Features

- **Model Context Protocol (MCP) Support**: Seamlessly integrates with AI agents (Claude, GPT-4) as a high-fidelity web exploration tool.
- **Production-Grade Concurrency**: Reuses global browser processes with isolated contexts to maximize throughput while minimizing resource overhead.
- **Enterprise Security**:
    - **API Key Authentication**: Protects endpoints with `X-API-KEY` header validation.
    - **Configurable CORS**: Restricted to trusted origins for secure browser-based interactions.
    - **Secret Redaction**: Automatic masking of passwords, tokens, and keys in logs.
- **Deep Observability**:
    - **Structured JSON Logging**: Powered by `structlog` for easy ingestion into ELK, CloudWatch, or Google Cloud Logging.
    - **Prometheus Metrics**: Real-time tracking of active contexts, crawl duration, and failure rates via `/metrics`.
    - **Health Monitoring**: Native `/health/live` and `/health/ready` endpoints for container orchestration.
- **Cloud-Native Deployment**: Optimized Docker multi-stage builds and ready-to-use Cloud Run configurations.
- **Automated Lifecycle Management**: Background workers handle the cleanup of session-specific SQLite state databases to prevent disk exhaustion.

---

## 🛠️ Architecture & Core Modules

The system is built on a non-blocking `asyncio` worker-pool architecture:

- **`mcp_server.py`**: The high-performance entry point. Manages the global Playwright lifecycle, SSE transport, and security middleware.
- **`main.py`**: The `CrawlerEngine` orchestrator. Manages worker tasks, state discovery, and session-specific graph isolation.
- **`crawler_actions.py`**: Handles complex page interactions, stealth navigation, human-like behavior, and network resource interception.
- **`model.py`**: High-performance graph management using `aiosqlite` for persistent state and **Priority-Weighted Beam Search** for flow extraction.
- **`telemetry.py`**: Centralized hub for structured logging and Prometheus metrics.

---

## 📦 Installation & Deployment

### Local Development

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Run Local Server**:
   ```bash
   export API_KEY="your-secret-key"
   python mcp_server.py
   ```

### Production Deployment (Google Cloud Run)

The application is optimized for Google Cloud Run. Deployment is automated via GitHub Actions, but can be done manually:

```bash
gcloud run deploy user-flow-mapper \
  --image us-central1-docker.pkg.dev/[PROJECT_ID]/user-flow-mapper/user-flow-mapper:latest \
  --memory 2Gi \
  --set-env-vars API_KEY="your-secret",ALLOWED_ORIGINS="https://your-ui.com"
```

---

## 🤖 Available MCP Tools

When connected as an MCP server, the following tools are available to AI agents:

- `map_user_flows`: Recursively maps UI flows for any URL.
- `get_ui_snapshot`: Returns a high-quality Base64 full-page screenshot.
- `extract_form_schema`: Discovers forms, inputs, and validation rules.
- `execute_ui_action`: Performs clicks or text input on specific UI elements.
- `test_user_journey`: Verifies a sequence of actions (e.g., checkout flow).
- `get_auth_cookies`: Automates login and retrieves session state.

---

## 📊 Monitoring & Health

- **Live Probe**: `GET /health/live` (Returns 200 if the process is running)
- **Ready Probe**: `GET /health/ready` (Returns 200 if the browser instance is connected)
- **Metrics**: `GET /metrics` (Prometheus format)

---

## 🛡️ Security Configuration

The server expects the following environment variables:
- `API_KEY`: A secret string for authenticating tool requests.
- `ALLOWED_ORIGINS`: Comma-separated list of allowed CORS origins.
- `CRAWLER_USERNAME` / `CRAWLER_PASSWORD`: Default credentials for authenticated crawls.

---

## 📝 Output Format

Results are generated in a UI-ready JSON format, including a list of extracted **Flows**, the full **Node** map, and interactive **Edges**.

```json
{
  "start_url": "https://example.com",
  "flows": [
    { "name": "Flow 1", "steps": ["Home", "Products", "Checkout"] }
  ],
  "nodes": [...],
  "edges": [...]
}
```
