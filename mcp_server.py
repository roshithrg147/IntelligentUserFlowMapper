import os
import json
import asyncio
import base64
import uvicorn
import logging
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from contextlib import suppress

# Import your existing crawler components
from main import CrawlerEngine
from crawler_actions import attempt_login
from config import settings

logger = logging.getLogger("CrawlerLogger")

# Global browser state for connection pooling
browser_state = {
    "playwright": None,
    "browser": None
}

@asynccontextmanager
async def lifespan(app: Starlette):
    """Manage the Playwright browser lifecycle globally to avoid resource exhaustion."""
    logger.info("Initializing global browser instance...")
    browser_state["playwright"] = await async_playwright().start()
    browser_state["browser"] = await browser_state["playwright"].chromium.launch(headless=True)
    yield
    logger.info("Shutting down global browser instance...")
    if browser_state["browser"]:
        await browser_state["browser"].close()
    if browser_state["playwright"]:
        await browser_state["playwright"].stop()

# 1. Initialize FastMCP
mcp = FastMCP("UI-Flow-Mapper-Pro")

async def get_browser():
    browser = browser_state["browser"]
    if not browser or not browser.is_connected():
        logger.warning("Browser disconnected. Rebooting Playwright instance...")
        if browser_state["browser"]:
            try:
                await browser_state["browser"].close()
            except Exception: pass
        if browser_state["playwright"]:
            try:
                await browser_state["playwright"].stop()
            except Exception: pass
        browser_state["playwright"] = await async_playwright().start()
        browser_state["browser"] = await browser_state["playwright"].chromium.launch(headless=True)
    return browser_state["browser"]

@mcp.tool()
async def map_user_flows(url: str, max_depth: int = 3, max_pages: int = 15) -> str:
    """Crawls a web application and maps its UI user flows."""
    import uuid
    session_id = str(uuid.uuid4())
    print(f"Starting crawl for {url} with session {session_id}...")
    crawler = CrawlerEngine(url, max_dep=max_depth, max_pages=max_pages, session_id=session_id)
    graph_data = await crawler.run()
    return graph_data.model_dump_json()

@mcp.tool()
async def get_ui_snapshot(url: str) -> str:
    """Navigates to a URL and returns a Base64 encoded full-page screenshot (JPEG)."""
    browser = await get_browser()
    context = await browser.new_context()
    page = await context.new_page()
    with suppress(ImportError):
        from playwright_stealth import stealth
        await stealth(page)
    try:
        await page.goto(url, wait_until="networkidle")
        screenshot_bytes = await page.screenshot(full_page=True, type="jpeg", quality=60)
        b64_str = base64.b64encode(screenshot_bytes).decode("utf-8")
        return json.dumps({"url": url, "snapshot_base64": b64_str})
    finally:
        await context.close()

@mcp.tool()
async def extract_form_schema(url: str) -> str:
    """Extracts all forms, input fields, and validation rules from a URL."""
    browser = await get_browser()
    context = await browser.new_context()
    page = await context.new_page()
    with suppress(ImportError):
        from playwright_stealth import stealth
        await stealth(page)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        schema = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('form')).map((f, i) => {
                const inputs = Array.from(f.querySelectorAll('input, select, textarea, button')).map(el => ({
                    name: el.name || el.id || 'unnamed',
                    type: el.type || el.tagName.toLowerCase(),
                    required: el.required || false,
                    placeholder: el.placeholder || '',
                    text: el.innerText || el.value || ''
                }));
                return { form_index: i, action: f.action, method: f.method, inputs };
            });
        }''')
        return json.dumps({"url": url, "forms": schema})
    finally:
        await context.close()

@mcp.tool()
async def execute_ui_action(url: str, target_element_text: str, action: str = "click", input_text: str = None) -> str:
    """Executes a specific action ('click' or 'fill') on an element containing specific text."""
    browser = await get_browser()
    context = await browser.new_context()
    page = await context.new_page()
    with suppress(ImportError):
        from playwright_stealth import stealth
        await stealth(page)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        if input_text and action == "fill":
            await page.fill(f"text={target_element_text}", input_text, timeout=5000)
        else:
            await page.click(f"text={target_element_text}", timeout=5000)
        
        await page.wait_for_load_state("networkidle", timeout=5000)
        new_url = page.url
        title = await page.title()
        return json.dumps({"status": "success", "new_url": new_url, "new_title": title})
    except Exception as e:
        logger.exception("Error executing UI action")
        return json.dumps({"status": "error", "message": str(e)})
    finally:
        await context.close()

@mcp.tool()
async def test_user_journey(start_url: str, target_button_sequence: list[str]) -> str:
    """Tests a sequence of button clicks to verify a UI journey."""
    browser = await get_browser()
    context = await browser.new_context()
    page = await context.new_page()
    with suppress(ImportError):
        from playwright_stealth import stealth
        await stealth(page)
    try:
        await page.goto(start_url, wait_until="domcontentloaded")
        history = []
        for btn_text in target_button_sequence:
            try:
                await page.click(f"text={btn_text}", timeout=5000)
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                history.append({"action": btn_text, "status": "success", "resulting_url": page.url})
            except Exception as e:
                history.append({"action": btn_text, "status": "failed", "error": str(e)})
                return json.dumps({"journey_status": "failed", "history": history})
                
        return json.dumps({"journey_status": "success", "history": history})
    finally:
        await context.close()

@mcp.tool()
async def get_auth_cookies(login_url: str, username: str, password: str) -> str:
    """Automates login and returns the session cookies."""
    browser = await get_browser()
    context = await browser.new_context()
    page = await context.new_page()
    with suppress(ImportError):
        from playwright_stealth import stealth
        await stealth(page)
    try:
        await attempt_login(page, login_url, username, password)
        cookies = await context.cookies()
        return json.dumps({"login_url": login_url, "cookies": cookies})
    finally:
        await context.close()

# 2. Wrap in Starlette for SSE transport
app = Starlette(debug=True, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/", mcp.sse_app())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
