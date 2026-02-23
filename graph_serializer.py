import json
from model import GraphData

def serialize_graph_to_disk(graph_data: GraphData, file_path: str):
    """
    Handles exclusively the presentation / serialization of GraphData.
    Separates the storage logic from the core GraphManager to maintain SRP.
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        # Pydantic V2 native json dumping or fallback to dict
        graph_dict = graph_data.model_dump()
        output = {
            "start_url": graph_dict["start_url"],
            "flows": graph_dict["flows"],
            "nodes": graph_dict["nodes"],
            "edges": graph_dict["edges"]
        }
        json.dump(output, f, indent=4)
        
    print(f"Graph serialized to {file_path}")
