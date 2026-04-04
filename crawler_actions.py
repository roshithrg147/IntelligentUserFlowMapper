import asyncio
from urllib.parse import urlparse, urljoin, urldefrag
from utils import get_state_hash
from function_logger import log_result

from contextlib import suppress

@log_result
async def setup_interception(page):
    """Intercepts and aborts unnecessary resource requests using pattern matching."""
    async def intercept(route):
        try:
            match route.request.resource_type:
                case "image" | "font" | "media":
                    await route.abort()
                case _:
                    await route.continue_()
        except Exception as e:
            print(f"Network abort failed: {e}")
    await page.route("**/*", intercept)

@log_result
async def attempt_login(page, start_url, username, password):
    """Attempts to log in if credentials were provided during initialization."""
    if not (username and password):
        return

    try:
        print("Attempting authentication...")
        await page.goto(start_url, wait_until="domcontentloaded", timeout=10000)
        await page.fill("input[type='email'], input[name*='user']", username, timeout=3000)
        await page.fill("input[type='password'], input[name*='pass']", password, timeout=3000)
        await page.click("button[type='submit'], input[type='submit'], [role='button']:has-text('Log in')")
        await page.wait_for_load_state("networkidle", timeout=5000)
        print("Authentication attempt finished.")
    except Exception as e:
        print(f"Authentication failed or no login form found: {e}")

@log_result
async def process_page(engine, page, url, depth, source_id, action, context="content"):
    """Core logic for visiting a single URL, hashing its state, and enqueuing links."""
    try:
        parsed_url = urlparse(url)
        if parsed_url.netloc != engine.base_domain:
            print(f"Blocking external jump to: {url}")
            return
        # Stripping params isn't strict here, but we check ending types.
        match url.lower().split('.')[-1]:
            case "pdf" | "jpg" | "jpeg" | "png" | "docx" | "mp4":
                return
            case _:
                pass
        
        print(f"Exploring: {url}, (Depth:{depth})")
        await page.goto(url, wait_until="domcontentloaded", timeout=6000)
        
        current_state_id = await asyncio.wait_for(get_state_hash(page), timeout=5.0)
        
        if engine.root_state_id is None:
            engine.root_state_id = current_state_id
            
        engine.graph.add_node(current_state_id, url, await page.title())
        
        if source_id is not None:
            engine.graph.add_edge(source_id, current_state_id, action, context)
        
        if current_state_id in engine.visited_states:
            return
        
        engine.visited_states.add(current_state_id)
        
        links_data = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll("a")).map(a => {
                    const isNav = a.closest('nav, header, footer, .header, .footer, .navigation, .menu') !== null;
                    return {
                        href: a.getAttribute("href") || "",
                        text: (a.innerText || "").trim(),
                        ariaLabel: a.getAttribute("aria-label") || "",
                        isNav: isNav
                    };
                });
            }
        """)
        
        for link_data in links_data:
            href = link_data["href"]
            if not href or href.startswith(("#", "javascript", "mailto")):
                continue
            
            abs_url, _ = urldefrag(urljoin(url, href))
            
            if urlparse(abs_url).netloc == engine.base_domain:
                if abs_url not in engine.queued_urls:
                    text = link_data["text"]
                    if not text:
                        text = link_data["ariaLabel"] or "Icon Click"
                    text = text.split('\n')[0].strip()
                    
                    is_nav = link_data.get("isNav", False)
                    next_context = "nav" if is_nav else "content"
                    
                    engine.queued_urls.add(abs_url)
                    await engine.enqueue(abs_url, depth + 1, current_state_id, text, next_context)
                
    except asyncio.TimeoutError:
        print(f"Timeout on {url}, Skipping")
    except Exception as e:
        print(f"Failed to process {url}:{e}")
