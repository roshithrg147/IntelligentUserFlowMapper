from pydantic import BaseModel, Field
from pydantic.types import FailFast
from typing import List, Annotated
from typing_extensions import TypedDict
from function_logger import log_result


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
        self._nodes_dict = {}
        self._edges_set = set()
        
    @log_result
    def add_node(self, node_id, url, title):
        if node_id not in self._nodes_dict:
            node_obj = {"id": node_id, "url": url, "title": title}
            self._nodes_dict[node_id] = node_obj
            self.graph.nodes.append(node_obj)
        
    @log_result
    def add_edge(self, source, target, label, context="content"):
        edge_tuple = (source, target, label, context)
        if edge_tuple not in self._edges_set:
            self._edges_set.add(edge_tuple)
            self.graph.edges.append({"source": source, "target": target, "label": label, "context": context})
            
    @log_result
    def _get_node_by_id(self, node_id):
        return self._nodes_dict.get(node_id)

    @log_result
    def extract_flows(self, start_node_id):
        """Uses priority-based Beam Search to extract linear flows from the graph, handling cycles safely."""
        # Build adjacency list
        adj = {}
        for edge in self.graph.edges:
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