import asyncio
import random
from urllib.parse import urlparse, urljoin, urldefrag
from utils import get_state_hash
from function_logger import log_result
from contextlib import suppress
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

from telemetry import logger

@log_result
async def perform_human_action(page):
    """Adds human-like behavior: randomized delay and mouse movements/scroll."""
    await asyncio.sleep(random.uniform(1, 3))
    # Random scroll
    await page.mouse.wheel(0, random.randint(100, 500))
    # Random mouse move
    await page.mouse.move(random.randint(0, 100), random.randint(0, 100))
    await asyncio.sleep(random.uniform(0.5, 1.5))

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
            logger.error("Network abort failed", error=str(e))
    await page.route("**/*", intercept)

@log_result
async def attempt_login(page, start_url, username, password):
    """Attempts to log in if credentials were provided during initialization."""
    if not (username and password):
        return

    try:
        from playwright_stealth import Stealth
        await Stealth().apply_stealth_async(page)
        logger.info("Attempting authentication...", url=start_url)
        await page.goto(start_url, wait_until="domcontentloaded", timeout=10000)
        await perform_human_action(page)
        await page.fill("input[type='email'], input[name*='user']", username, timeout=3000)
        await page.fill("input[type='password'], input[name*='pass']", password, timeout=3000)
        await page.click("button[type='submit'], input[type='submit'], [role='button']:has-text('Log in')")
        await page.wait_for_load_state("networkidle", timeout=5000)
        logger.info("Authentication attempt finished")
    except Exception as e:
        logger.error("Authentication failed or no login form found", error=str(e))

@log_result
async def process_page(engine, page, url, depth, source_id, action, context="content"):
    """Core logic for visiting a single URL, hashing its state, and enqueuing links."""
    try:
        # Import stealth here to handle potential import errors in headless environments
        with suppress(ImportError):
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)
            
        parsed_url = urlparse(url)
        if parsed_url.netloc != engine.base_domain:
            logger.info("Blocking external jump", url=url)
            return
        # Stripping params isn't strict here, but we check ending types.
        match url.lower().split('.')[-1]:
            case "pdf" | "jpg" | "jpeg" | "png" | "docx" | "mp4":
                return
            case _:
                pass
        
        logger.debug("Exploring page", url=url, depth=depth, session_id=engine.session_id)
        response = await page.goto(url, wait_until="domcontentloaded", timeout=6000)
        if response and response.status in [403, 429]:
            raise Exception(f"RateLimitException: {response.status}")
        
        # Check for CAPTCHA
        content = await page.content()
        if "captcha" in content.lower():
            raise Exception("RateLimitException: CAPTCHA detected")

        await perform_human_action(page)
        
        current_state_id = await asyncio.wait_for(get_state_hash(page), timeout=5.0)
        
        if engine.root_state_id is None:
            engine.root_state_id = current_state_id
            
        await engine.graph.add_node(current_state_id, url, await page.title())
        
        if source_id is not None:
            await engine.graph.add_edge(source_id, current_state_id, action, context)
        
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
        logger.warning("Timeout skipping", url=url, session_id=engine.session_id)
    except PlaywrightTimeoutError:
        logger.warning("Playwright timeout skipping", url=url, session_id=engine.session_id)
    except PlaywrightError as pe:
        logger.error("Playwright Engine Error", url=url, error=str(pe), session_id=engine.session_id)
    except Exception as e:
        logger.error("Failed to process page", url=url, error=str(e), session_id=engine.session_id)
