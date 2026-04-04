import pytest
import json
from function_logger import redact_secrets
from model import GraphManager, GraphData
from utils import get_state_hash_sync

def test_json_aware_redaction():
    # Test dictionary redaction
    log_data = {
        "user_id": 123,
        "token": "secret_abc123",
        "auth_key": "some_key_here",
        "normal_field": "safe_value"
    }
    redacted_json = redact_secrets(json.dumps(log_data))
    redacted = json.loads(redacted_json)
    
    assert redacted["user_id"] == 123
    assert redacted["token"] == "REDACTED"
    assert redacted["auth_key"] == "REDACTED"
    assert redacted["normal_field"] == "safe_value"

def test_regex_fallback_redaction():
    # Test unstructured text redaction fallback
    log_msg = 'Connecting with Authorization: "Bearer xyz123"'
    redacted = redact_secrets(log_msg)
    assert 'Authorization=REDACTED' in redacted
    assert 'xyz123' not in redacted

@pytest.mark.asyncio
async def test_graph_manager_initialization():
    # Test that aiosqlite integration initializes properly
    import tempfile
    import os
    with tempfile.NamedTemporaryFile() as tmp:
        os.environ["SQLITE_DB_PATH"] = tmp.name
        manager = GraphManager()
        manager.db_path = tmp.name
        await manager.init_db()
        await manager.add_node("node1", "http://test.com", "Test Title")
        
        node = await manager._get_node_by_id("node1")
        assert node is not None
        assert node["title"] == "Test Title"
        assert node["url"] == "http://test.com"

def test_hash_sync():
    hash1 = get_state_hash_sync("http://amazon.in")
    hash2 = get_state_hash_sync("http://amazon.in")
    assert hash1 == hash2
    assert len(hash1) == 64
