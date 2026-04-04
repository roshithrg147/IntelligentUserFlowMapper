from pydantic import BaseModel, Field
from pydantic.types import FailFast
from typing import List, Annotated
from typing_extensions import TypedDict
from function_logger import log_result


import sqlite3
import json
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
        self._init_db()
        self._edges_set = set()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS nodes
                            (id TEXT PRIMARY KEY, data TEXT)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS edges
                            (source TEXT, target TEXT, label TEXT, context TEXT, PRIMARY KEY (source, target, label, context))''')
        
    def get_all_nodes(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT data FROM nodes")
            return [json.loads(row[0]) for row in cur.fetchall()]

    def get_all_edges(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT source, target, label, context FROM edges")
            return [{"source": row[0], "target": row[1], "label": row[2], "context": row[3]} for row in cur.fetchall()]

    def prepare_serialization(self):
        self.graph.nodes = self.get_all_nodes()
        self.graph.edges = self.get_all_edges()

    @log_result
    def add_node(self, node_id, url, title):
        node_obj = {"id": node_id, "url": url, "title": title}
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO nodes (id, data) VALUES (?, ?)", (node_id, json.dumps(node_obj)))
        
    @log_result
    def add_edge(self, source, target, label, context="content"):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO edges (source, target, label, context) VALUES (?, ?, ?, ?)", (source, target, label, context))
            
    @log_result
    def _get_node_by_id(self, node_id):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT data FROM nodes WHERE id = ?", (node_id,))
            row = cur.fetchone()
            if row:
                return json.loads(row[0])
        return None

    @log_result
    def extract_flows(self, start_node_id):
        """Uses priority-based Beam Search to extract linear flows from the graph, handling cycles safely."""
        # Build adjacency list
        adj = {}
        for edge in self.get_all_edges():
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
        start_node = self._get_node_by_id(start_node_id)
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
                        
                    target_node = self._get_node_by_id(target)
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