from pydantic import BaseModel, Field
from pydantic.types import FailFast
from typing import List, Annotated
from typing_extensions import TypedDict
from function_logger import log_result


import aiosqlite
import json
import os
import asyncio
from config import settings

class Node(TypedDict):
    id: str
    url: str
    title: str
    
class Edge(TypedDict):
    source: str
    target: str
    label: str
    context: str

class Flow(BaseModel):
    name: str
    steps: List[str]

class GraphData(BaseModel):
    start_url: str = ""
    flows: Annotated[List[Flow], FailFast()] = Field(default_factory=list)
    nodes: Annotated[List[Node], FailFast()] = Field(default_factory=list)
    edges: Annotated[List[Edge], FailFast()] = Field(default_factory=list)

class GraphManager:
    def __init__(self):
        self.graph = GraphData()
        self.db_path = settings.sqlite_db_path
        self._edges_set = set()
        
    async def init_db(self):
        # Create results directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('''CREATE TABLE IF NOT EXISTS nodes
                            (id TEXT PRIMARY KEY, data TEXT)''')
            await conn.execute('''CREATE TABLE IF NOT EXISTS edges
                            (source TEXT, target TEXT, label TEXT, context TEXT, PRIMARY KEY (source, target, label, context))''')
            await conn.commit()
        
    async def get_all_nodes(self):
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT data FROM nodes") as cur:
                rows = await cur.fetchall()
                return [json.loads(row[0]) for row in rows]

    async def get_all_edges(self):
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT source, target, label, context FROM edges") as cur:
                rows = await cur.fetchall()
                return [{"source": row[0], "target": row[1], "label": row[2], "context": row[3]} for row in rows]

    async def prepare_serialization(self):
        self.graph.nodes = await self.get_all_nodes()
        self.graph.edges = await self.get_all_edges()

    @log_result
    async def add_node(self, node_id, url, title):
        node_obj = {"id": node_id, "url": url, "title": title}
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("INSERT OR IGNORE INTO nodes (id, data) VALUES (?, ?)", (node_id, json.dumps(node_obj)))
            await conn.commit()
        
    @log_result
    async def add_edge(self, source, target, label, context="content"):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("INSERT OR IGNORE INTO edges (source, target, label, context) VALUES (?, ?, ?, ?)", (source, target, label, context))
            await conn.commit()
            
    @log_result
    async def _get_node_by_id(self, node_id):
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT data FROM nodes WHERE id = ?", (node_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    return json.loads(row[0])
        return None

    @log_result
    async def extract_flows(self, start_node_id):
        """Uses priority-based Beam Search to extract linear flows from the graph, handling cycles safely."""
        # Build adjacency list
        adj = {}
        edges = await self.get_all_edges()
        for edge in edges:
            adj.setdefault(edge["source"], []).append(edge)

        def edge_weight(label, context):
            if context == "nav":
                return 10
            
            l = label.lower()
            if any(word in l for word in ["submit", "login", "register", "buy", "checkout", "add", "save", "next"]):
                return 1
            if any(word in l for word in ["click", "button"]):
                return 2
            return 5

        beam_width = 20
        start_node = await self._get_node_by_id(start_node_id)
        if not start_node:
            return
            
        beam = [(0, [start_node_id], [start_node["title"]], {start_node_id})]
        completed_paths = []
        
        while beam and len(completed_paths) < 100:
            next_beam = []
            for weight, path_ids, path_titles, visited in beam:
                current_id = path_ids[-1]
                
                if current_id not in adj:
                    if len(path_titles) > 1:
                        completed_paths.append((weight, path_titles))
                    continue
                
                for edge in adj[current_id]:
                    target = edge["target"]
                    label = edge["label"]
                    
                    if target in visited:
                        if len(path_titles) > 1:
                            completed_paths.append((weight, path_titles))
                        continue
                        
                    target_node = await self._get_node_by_id(target)
                    if not target_node:
                        continue
                        
                    new_weight = weight + edge_weight(label, edge.get("context", "content"))
                    new_visited = visited.copy()
                    new_visited.add(target)
                    new_path_ids = path_ids + [target]
                    new_path_titles = path_titles + [target_node["title"]]
                    
                    next_beam.append((new_weight, new_path_ids, new_path_titles, new_visited))
            
            next_beam.sort(key=lambda x: x[0])
            beam = next_beam[:beam_width]

        for weight, path_ids, path_titles, visited in beam:
             if len(path_titles) > 1:
                 completed_paths.append((weight, path_titles))

        unique_paths = []
        seen = set()
        completed_paths.sort(key=lambda x: x[0])
        
        for weight, p in completed_paths:
            p_tuple = tuple(p)
            if p_tuple not in seen:
                seen.add(p_tuple)
                unique_paths.append(p)
                
        top_paths = unique_paths[:10]

        self.graph.flows = [
            Flow(name=f"Flow {i+1}", steps=path)
            for i, path in enumerate(top_paths)
        ]