import logging
from logging.handlers import RotatingFileHandler
import os
import inspect
from functools import wraps

LOG_FILE = "results/function_results.log"

# Ensure directory exists
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Configure structured logging
logger = logging.getLogger("CrawlerLogger")
logger.setLevel(logging.INFO)

# RotatingFileHandler: 5MB max, 3 backups
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
formatter = logging.Formatter('{"module": "%(module)s", "function": "%(funcName)s", "message": %(message)s}')
handler.setFormatter(formatter)
logger.addHandler(handler)

def log_result(func):
    """Decorator to log function calls and their results."""
    
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                _log_entry(func.__name__, result)
                return result
            except Exception as e:
                _log_entry(func.__name__, f"Error: {str(e)}")
                raise e
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                _log_entry(func.__name__, result)
                return result
            except Exception as e:
                _log_entry(func.__name__, f"Error: {str(e)}")
                raise e
        return sync_wrapper

def _log_entry(func_name, result):
    import json
    try:
        # Simplified truncation logic
        res_str = str(result)
        if len(res_str) > 2000:
            res_str = res_str[:2000] + "... [truncated]"
        
        # We need to escape double quotes for JSON string if we are using string formatting
        # Actually, let's just use json.dumps for the message part
        message = json.dumps({"result": res_str})
        logger.info(message)
    except Exception as e:
        logger.error(json.dumps({"error": str(e)}))
