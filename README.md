# Intelligent User Flow Mapper

## 1. Project Overview & Features

**Overview**: The Intelligent User Flow Mapper is a smart, asynchronous backend crawler designed to dynamically explore and produce structural representations of web applications. It maps a website's layout, intelligently filters out global navigation noise, and extracts the most meaningful, human-like linear user journeys into a UI-ready JSON format.

**Key Features**:

- **High-Performance Concurrency**: Built on `asyncio` and Playwright, utilizing an asynchronous worker-pool to process pages concurrently without blocking the event loop.
- **Structural DOM-Aware Noise Reduction**: Intelligently differentiates between structural noise (links in `<nav>`, `<header>`, `<footer>`) and meaningful content interactions (`<main>`, `<body>`).
- **Robust State Deduplication**: Eliminates redundancies by using robust DOM-element hashing (SHA-256) instead of naive URL matching, securely identifying unique application states like modals or SPAs.
- **Priority-Weighted Beam Search**: Extracts human-readable user flows by assigning weighted traversal priorities, prioritizing actionable pathways over generic interlinking.

---

## 2. Installation & Quick Start

### Prerequisites

- Python 3.9+
- Node.js (Optional, depending on Playwright system dependencies)

### Setup Instructions

1. **Create and activate a virtual environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

2. **Install project requirements**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers**:
   This crawler requires Chromium to be installed via Playwright for headless execution. Execute this strictly _after_ `pip install -r requirements.txt` has successfully installed the Playwright Python package.

   ```bash
   playwright install chromium
   ```

4. **Run the Crawler**:
   ```bash
   python main.py
   ```
   The crawler will execute and output the final graph topology to `results/user_flow.json`.

---

## 3. Core Architectural Modules (How It Works)

The architecture strictly adheres to the **Single Responsibility Principle (SRP)**, decoupling orchestration, execution, state management, and serialization.

- **`main.py`**: The central orchestrator. It manages the async event loop, initializes the `asyncio.Queue`, and controls the concurrency worker pool. It guarantees bounded concurrency and safe shutdown sequences. The `asyncio.Queue` dynamically feeds dedicated Playwright worker contexts to enforce a purely non-blocking I/O model.

  _[Insert Diagram: Asynchronous Worker Pool Architecture here]_

- **`crawler_actions.py`**: Handles all Playwright page interactions. This module intercepts network requests (aborting massive assets like images/media for speed), structurally assesses the DOM (tracing element ancestry), and enqueues newly discovered URL targets.
- **`model.py`**: Manages the application graph topology (`GraphManager`). Uses $O(1)$ hash maps (`_nodes_dict`) and sets (`_edges_set`) to prevent $O(N^2)$ scaling bottlenecks during deduplication. Also houses the complex Beam Search algorithm responsible for flow extraction.
- **`utils.py`**: Contains the highly resilient `get_state_hash` algorithm responsible for fingerprinting SPA layouts.
- **`function_logger.py`**: A custom asynchronous logging decorator ensuring safe, metadata-aware telemetry execution logging without risking JSON/OOM stringification corruptions.
- **`graph_serializer.py`**: Explicitly isolates Pydantic V2 JSON serialization to format the final graph into strict, UI-compliant JSON outputs.

---

## 4. Key Engineering Decisions

### State Identification vs. URL Matching

**Problem**: Modern Web Apps (SPAs) and complex sites often change their visual state without changing their URL (e.g., opening a modal, manipulating a React component). Conversely, they might change URLs with trailing generic tracking parameters while keeping the visual state identical.
**Solution**: We utilize a `get_state_hash` approach over raw URL mapping. We inject JavaScript into the Playwright context to extract the tags, IDs, attributes, and text of strictly interactive elements (`<button>`, `<a>`, `<input>`). We sort this data structure to ensure deterministic output, then generate a SHA-256 hash. This groups fundamentally identical layout states together, regardless of URL parameter drift.

### Noise Reduction: Structural Awareness over Statistical Guessing

**Problem**: Traditional heuristic crawlers detect "Global Navigation" by statistical frequency (identifying a link as noise if it appears on >80% of pages). On highly dense corporate sites with "Mega-Menus", this aggressive heuristic systematically destroys completely valid content links.
**Solution**: We employ **DOM Ancestry Mapping**. When `crawler_actions.py` evaluates the DOM, it uses JavaScript's `element.closest('nav, header, footer, .navigation, .menu')` to geometrically map a link.
Instead of discarding navigation links, we tag the edge with a schema context of `"nav"` or `"content"`. We maintain the complete connectivity graph but classify it appropriately for delayed pruning algorithms.

### Smart Flow Extraction (Beam Search)

**Problem**: Using a Naive Depth-First Search (DFS) on highly interconnected, non-trivial enterprise websites inevitably leads to an exponential path explosion and cyclic stack overflows.
**Solution**: We programmed a **Priority-Based Bounded Beam Search** inside `model.py`. The algorithm extracts "human-like" linear user flows by dynamically assigning traversal weights:

- Interacting with a `"nav"` context gets a heavy penalty (`weight = 10`).
- Interacting with standard `"content"` gets a standard priority (`weight = 5`).
- Actionable, structural progression labels (e.g., `"submit"`, `"login"`, `"checkout"`, `"register"`) are highly prioritized (`weight = 1` or `2`).

This guarantees that the Beam Search naturally gravitates towards and surfaces the most meaningful interactive user journeys (e.g., `Home Page -> Product Listing -> Add to Cart -> Checkout`) rather than tracing a route directly into a generic footer directory.

---

## 5. Output Format

The `graph_serializer.py` strictly complies with frontend UI requirements, cleanly projecting the `flows` array at the top level of the JSON body.

**Sample Output Structure (`results/user_flow.json`)**:

```json
{
  "start_url": "https://example.com",
  "flows": [
    {
      "name": "Flow 1",
      "steps": [
        "Home Page",
        "Product Catalog",
        "Add to Cart",
        "Secure Checkout"
      ]
    },
    {
      "name": "Flow 2",
      "steps": ["Home Page", "Login Portal"]
    }
  ],
  "nodes": [
    {
      "id": "8e81f824e...",
      "url": "https://example.com",
      "title": "Home Page"
    }
  ],
  "edges": [
    {
      "source": "8e81f824e...",
      "target": "362057311...",
      "label": "Login",
      "context": "nav"
    }
  ]
}
```

## 🤖 MCP Server & Agentic UI Tools

This crawler can now be run as a **Model Context Protocol (MCP)** Server! By running the server, you can give any AI agent (like Claude Desktop or custom UIs) direct access to crawl, map, and interact with web applications autonomously.

### Available MCP Tools
1. `map_user_flows`: Crawls a web app and maps UI flows.
2. `get_ui_snapshot`: Takes a full-page screenshot and returns Base64.
3. `extract_form_schema`: Maps all forms and input fields.
4. `execute_ui_action`: Clicks or fills specific UI elements.
5. `test_user_journey`: Tests a sequence of UI actions.
6. `get_auth_cookies`: Automates login and harvests cookies.

### Running the Server
```bash
pip install -r requirements.txt mcp starlette uvicorn httpx playwright
playwright install
python mcp_server.py
```
The server will start on `http://0.0.0.0:8000/sse`.
