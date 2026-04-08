import asyncio
from main import CrawlerEngine
from graph_serializer import serialize_graph_to_disk

async def main():
    print("Testing pilatewave.in...")
    # Instantiate the crawler with a broader page limit if needed
    crawler = CrawlerEngine("https://www.github.com", max_dep=3, max_pages=30)
    graph_data = await crawler.run()
    
    output_path = 'results/user_flow-foreai.json'
    serialize_graph_to_disk(graph_data, output_path)
    print(f"Done! The path visualization is saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(main())
