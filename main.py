import os
import json
import asyncio
from collections import deque
from playwright.async_api import async_playwright
from urllib.parse import urlparse

from utils import get_state_hash, save_result
from model import GraphManager
from crawler_actions import setup_interception, attempt_login, process_page
from graph_serializer import serialize_graph_to_disk

class CrawlerEngine:
    def __init__(self, start_url, max_dep=3, max_pages=50, username=None, password=None):
        self.start_url = start_url
        self.max_dep = max_dep
        self.max_pages = max_pages
        self.username = username
        self.password = password
        self.base_domain = urlparse(start_url).netloc
        
        self.graph = GraphManager()
        
        self.queue = asyncio.Queue()
        self.queue.put_nowait((start_url, 0, None, "Start", "content"))
        self.visited_states = set()
        self.queued_urls = set()
        self.queued_urls.add(self.start_url)
        self.processing_urls = set()
        
        # Ensure the graph knows the root URL for the UI format
        self.graph.graph.start_url = self.start_url
        
        # Special tracking for the very first node to initiate flow extraction later
        self.root_state_id = None
        
        
    async def worker(self, queue, browser_context):
        page = await browser_context.new_page()
        await setup_interception(page)
        while True:
            url, depth, source_id, action, context_tag = await queue.get()
            
            if url in self.processing_urls:
                queue.task_done()
                continue
                
            self.processing_urls.add(url)
            
            try:
                v_size = len(self.visited_states)
                if v_size >= self.max_pages:
                    continue
                
                q_size = queue.qsize()
                print(f"----Progress: [Queue: {q_size}] | States Mapped: {v_size}----")
                if depth > self.max_dep:
                    continue
                    
                await process_page(self, page, url, depth, source_id, action, context_tag)
            except Exception as e:
                print(f"Worker error processing {url}: {e}")
            finally:
                queue.task_done()

    async def run(self):
        """Main orchestrator for the crawling process."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width':1280, 'height': 720})
            page = await context.new_page()
            
            await setup_interception(page)
            await attempt_login(page, self.start_url, self.username, self.password)
            await page.close()
            
            workers = []
            for _ in range(4): # Spawn 4 worker tasks
                task = asyncio.create_task(self.worker(self.queue, context))
                workers.append(task)
                
            await self.queue.join()
            
            for w in workers:
                w.cancel()
                
            await browser.close()
            
        print("Skipping global navigation pruning to rely on context-based pathfinding edges.")
            
        if self.root_state_id:
            print("Extracting linear user flows...")
            self.graph.extract_flows(self.root_state_id)
            
        return self.graph.graph
       
if __name__ == "__main__":
    crawler = CrawlerEngine("http://books.toscrape.com/", max_dep=3, max_pages=15) # Reduced pages for quick test
    graph_data = asyncio.run(crawler.run())
    serialize_graph_to_disk(graph_data, 'results/user_flow-books-toscrape.json')