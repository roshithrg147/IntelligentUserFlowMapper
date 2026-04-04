print("MCP Server starting up...") # Debug line
import json
import asyncio
import base64
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright

# Import your existing crawler components
from main import CrawlerEngine
from crawler_actions import attempt_login
from config import settings

# 1. Initialize FastMCP
mcp = FastMCP("UI-Flow-Mapper-Pro")

@mcp.tool()
async def map_user_flows(url: str, max_depth: int = 3, max_pages: int = 15) -> str:
    """Crawls a web application and maps its UI user flows."""
    print(f"Starting crawl for {url}...")
    crawler = CrawlerEngine(url, max_dep=max_depth, max_pages=max_pages)
    graph_data = await crawler.run()
    return graph_data.model_dump_json()

@mcp.tool()
async def get_ui_snapshot(url: str) -> str:
    """Navigates to a URL and returns a Base64 encoded full-page screenshot (JPEG)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        screenshot_bytes = await page.screenshot(full_page=True, type="jpeg", quality=60)
        await browser.close()
        b64_str = base64.b64encode(screenshot_bytes).decode("utf-8")
        return json.dumps({"url": url, "snapshot_base64": b64_str})

@mcp.tool()
async def extract_form_schema(url: str) -> str:
    """Extracts all forms, input fields, and validation rules from a URL."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
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
        await browser.close()
        return json.dumps({"url": url, "forms": schema})

@mcp.tool()
async def execute_ui_action(url: str, target_element_text: str, action: str = "click", input_text: str = None) -> str:
    """Executes a specific action ('click' or 'fill') on an element containing specific text."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        try:
            if input_text and action == "fill":
                # Find input near the text label
                await page.fill(f"text={target_element_text}", input_text, timeout=5000)
            else:
                await page.click(f"text={target_element_text}", timeout=5000)
            
            await page.wait_for_load_state("networkidle", timeout=5000)
            new_url = page.url
            title = await page.title()
            await browser.close()
            return json.dumps({"status": "success", "new_url": new_url, "new_title": title})
        except Exception as e:
            await browser.close()
            return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
async def test_user_journey(start_url: str, target_button_sequence: list[str]) -> str:
    """Tests a sequence of button clicks to verify a UI journey."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(start_url, wait_until="domcontentloaded")
        history = []
        for btn_text in target_button_sequence:
            try:
                await page.click(f"text={btn_text}", timeout=5000)
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                history.append({"action": btn_text, "status": "success", "resulting_url": page.url})
            except Exception as e:
                history.append({"action": btn_text, "status": "failed", "error": str(e)})
                await browser.close()
                return json.dumps({"journey_status": "failed", "history": history})
                
        await browser.close()
        return json.dumps({"journey_status": "success", "history": history})

@mcp.tool()
async def get_auth_cookies(login_url: str, username: str, password: str) -> str:
    """Automates login and returns the session cookies."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        # Uses your existing attempt_login from crawler_actions.py
        await attempt_login(page, login_url, username, password)
        cookies = await context.cookies()
        await browser.close()
        return json.dumps({"login_url": login_url, "cookies": cookies})

# 2. Wrap in Starlette for SSE transport
app = Starlette(debug=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/", mcp.sse_app())

import os

