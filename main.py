import os
import json
import asyncio
from collections import deque
from playwright.async_api import async_playwright
from urllib.parse import urlparse
import redis.asyncio as redis

from config import settings
from utils import get_state_hash, save_result
from model import GraphManager
from crawler_actions import setup_interception, attempt_login, process_page
from graph_serializer import serialize_graph_to_disk

class CrawlerEngine:
    def __init__(self, start_url, max_dep=3, max_pages=50, username=None, password=None):
        self.start_url = start_url
        self.max_dep = max_dep
        self.max_pages = max_pages
        self.username = username or settings.crawler_username
        self.password = password or settings.crawler_password
        self.base_domain = urlparse(start_url).netloc
        
        self.graph = GraphManager()
        
        self.redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        self.queue_key = f"crawler_queue:{get_state_hash(start_url)}"
        
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
            
            # If we are throttled, only worker_id 0 should proceed
            if self.max_workers == 1 and worker_id != 0:
                await asyncio.sleep(60) # Wait out the throttle
                continue

            item = await self.redis_client.lpop(self.queue_key)
            if not item:
                await asyncio.sleep(0.5)
                continue
                
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
                
                q_size = await self.redis_client.llen(self.queue_key)
                print(f"----Progress: [Queue: {q_size}] | States Mapped: {v_size}----")
                if depth > self.max_dep:
                    continue
                    
                await process_page(self, page, url, depth, source_id, action, context_tag)
            except Exception as e:
                print(f"Worker error processing {url}: {e}")
                if "RateLimitException" in str(e):
                    print("Rate limit detected! Pausing workers for 60 seconds.")
                    self.max_workers = 1
                    self.paused.clear()
                    await asyncio.sleep(60)
                    self.max_workers = 4
                    self.paused.set()


    async def enqueue(self, url, depth, source_id, action, context_tag):
        data = json.dumps({
            "url": url,
            "depth": depth,
            "source_id": source_id,
            "action": action,
            "context_tag": context_tag
        })
        await self.redis_client.rpush(self.queue_key, data)

    async def run(self):
        """Main orchestrator for the crawling process."""
        # Initialize queue
        await self.redis_client.delete(self.queue_key)
        await self.enqueue(self.start_url, 0, None, "Start", "content")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
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
            while True:
                q_size = await self.redis_client.llen(self.queue_key)
                # Since we don't have task_done for redis, a simple heuristic:
                if q_size == 0 and len(self.processing_urls) >= len(self.visited_states) and len(self.visited_states) > 0:
                    await asyncio.sleep(2)
                    if await self.redis_client.llen(self.queue_key) == 0:
                        break
                elif len(self.visited_states) >= self.max_pages:
                    break
                await asyncio.sleep(1)
            
            for w in workers:
                w.cancel()
                
            await browser.close()
            
        print("Skipping global navigation pruning to rely on context-based pathfinding edges.")
            
        if self.root_state_id:
            print("Extracting linear user flows...")
            self.graph.extract_flows(self.root_state_id)
            
        self.graph.prepare_serialization()
        return self.graph.graph
       
if __name__ == "__main__":
    crawler = CrawlerEngine("http://books.toscrape.com/", max_dep=3, max_pages=15) # Reduced pages for quick test
    graph_data = asyncio.run(crawler.run())
    serialize_graph_to_disk(graph_data, 'results/user_flow-books-toscrape.json')