import os
import json
import asyncio

from playwright.async_api import async_playwright
from urllib.parse import urlparse
# import redis.asyncio as redis

from config import settings
from utils import get_state_hash, get_state_hash_sync, save_result
from model import GraphManager
from crawler_actions import setup_interception, attempt_login, process_page
from graph_serializer import serialize_graph_to_disk
from telemetry import logger, ACTIVE_BROWSER_CONTEXTS, FAILURE_RATE

class CrawlerEngine:
    def __init__(self, start_url, max_dep=3, max_pages=50, username=None, password=None, session_id=None, browser=None):
        self.start_url = start_url
        self.max_dep = max_dep
        self.max_pages = max_pages
        # Convert SecretStr to string safely if provided, otherwise fallback to settings
        self.username = username or (settings.crawler_username.get_secret_value() if settings.crawler_username else None)
        self.password = password or (settings.crawler_password.get_secret_value() if settings.crawler_password else None)
        self.base_domain = urlparse(start_url).netloc
        self.shared_browser = browser
        self.session_id = session_id or "local_test"
        
        self.graph = GraphManager(session_id=session_id)
        
        self.queue = asyncio.Queue()
        self.queue_key = f"crawler_queue:{get_state_hash_sync(start_url)}"
        
        self.visited_states = set()
        self.queued_urls = set()
        self.queued_urls.add(self.start_url)
        self.processing_urls = set()
        
        # Ensure the graph knows the root URL for the UI format
        self.graph.graph.start_url = self.start_url
        
        # Special tracking for the very first node to initiate flow extraction later
        self.root_state_id = None
        self.paused = asyncio.Event()
        self.paused.set()
        self.max_workers = 4
        
    async def worker(self, browser_context, worker_id):
        page = await browser_context.new_page()
        await setup_interception(page)
        while True:
            await self.paused.wait()
            
            try:
                item = await self.queue.get()
            except asyncio.CancelledError:
                break
                
            try:
                data = json.loads(item)
                url = data['url']
                depth = data['depth']
                source_id = data['source_id']
                action = data['action']
                context_tag = data['context_tag']
            except Exception:
                continue
            
            if url in self.processing_urls:
                continue
                
            self.processing_urls.add(url)
            
            try:
                v_size = len(self.visited_states)
                if v_size >= self.max_pages:
                    continue
                
                q_size = self.queue.qsize()
                logger.info("Worker mapping progress", queue=q_size, states_mapped=v_size, session_id=self.session_id)
                if depth > self.max_dep:
                    continue
                    
                await process_page(self, page, url, depth, source_id, action, context_tag)
            except Exception as e:
                logger.error("Worker error processing", url=url, session_id=self.session_id, exc_info=True)
                FAILURE_RATE.labels(domain=self.base_domain, error_type=type(e).__name__).inc()
                if "RateLimitException" in str(e):
                    logger.warning("Rate limit detected! Delaying worker.", session_id=self.session_id)
                    await asyncio.sleep(60)
            finally:
                self.queue.task_done()


    async def enqueue(self, url, depth, source_id, action, context_tag):
        data = json.dumps({
            "url": url,
            "depth": depth,
            "source_id": source_id,
            "action": action,
            "context_tag": context_tag
        })
        await self.queue.put(data)

    async def run(self):
        """Main orchestrator for the crawling process."""
        await self.graph.init_db()
        try:
            while not self.queue.empty():
                self.queue.get_nowait()
                self.queue.task_done()
            await self.enqueue(self.start_url, 0, None, "Start", "content")
            
            if self.shared_browser:
                browser = self.shared_browser
                p = None
                own_browser = False
            else:
                p = await async_playwright().start()
                browser = await p.chromium.launch(headless=True)
                own_browser = True

            try:
                ACTIVE_BROWSER_CONTEXTS.inc()
                context = await browser.new_context(viewport={'width':1280, 'height': 720})
                page = await context.new_page()
                
                await setup_interception(page)
                await attempt_login(page, self.start_url, self.username, self.password)
                await page.close()
                
                workers = []
                for i in range(4): # Spawn 4 worker tasks
                    task = asyncio.create_task(self.worker(context, i))
                    workers.append(task)
                    
                # Wait for queue to be empty and processing to finish
                await self.queue.join()
                
                for w in workers:
                    w.cancel()
                    
            finally:
                if own_browser:
                    await browser.close()
                    await p.stop()
                ACTIVE_BROWSER_CONTEXTS.dec()
                
            logger.info("Skipping global navigation pruning to rely on context-based pathfinding edges.", session_id=self.session_id)
                
            if self.root_state_id:
                logger.info("Extracting linear user flows...", session_id=self.session_id)
                await self.graph.extract_flows(self.root_state_id)
                
            await self.graph.prepare_serialization()
            if self.graph.conn:
                await self.graph.conn.commit()
            return self.graph.graph
        finally:
            await self.graph.close()
       
if __name__ == "__main__":
    crawler = CrawlerEngine("http://books.toscrape.com/", max_dep=3, max_pages=15) # Reduced pages for quick test
    graph_data = asyncio.run(crawler.run())
    serialize_graph_to_disk(graph_data, 'IntelligentUserFlowMapper_Dev/results/user_flow-books-toscrape.json')
