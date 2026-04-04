import logging
import re
import json
from logging.handlers import RotatingFileHandler
import os
import inspect
from functools import wraps
import sys # Import sys for StreamHandler

LOG_FILE = "results/function_results.log"

# Ensure directory exists
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Configure structured logging
logger = logging.getLogger("CrawlerLogger")
logger.setLevel(logging.DEBUG) # Set to DEBUG for maximum verbosity

# Redaction helper
def redact_secrets(text):
    if not isinstance(text, str):
        return text
    
    # Simple JSON parsing to redact structured logs
    try:
        data = json.loads(text)
        def _mask_dict(d):
            if isinstance(d, dict):
                for k, v in d.items():
                    if any(s in k.lower() for s in ["password", "token", "secret", "key", "auth", "authorization"]):
                        d[k] = "REDACTED"
                    else:
                        _mask_dict(v)
            elif isinstance(d, list):
                for item in d:
                    _mask_dict(item)
            return d
        
        masked_data = _mask_dict(data)
        return json.dumps(masked_data)
    except json.JSONDecodeError:
        # Non-JSON string; truncate to prevent leakage
        if len(text) > 200:
            return text[:200] + "... [TRUNCATED FOR SECURITY]"
        return text

# StreamHandler for Cloud Run (stdout/stderr)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG) # Set to DEBUG for maximum verbosity
stream_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)

# RotatingFileHandler: 5MB max, 3 backups (for local debugging/persistence if needed)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
file_handler.setLevel(logging.DEBUG) # Set to DEBUG for maximum verbosity
file_formatter = logging.Formatter('{"module": "%(module)s", "function": "%(funcName)s", "message": %(message)s}')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

def log_result(func):
    """Decorator to log function calls and their results."""
    
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                logger.debug(f"Function {func.__name__} executed successfully.") # Use debug for success
                return result
            except Exception as e:
                clean_error = redact_secrets(str(e))
                logger.error(f"Error in {func.__name__}: {clean_error}", exc_info=True) # Log full traceback
                raise e
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                logger.debug(f"Function {func.__name__} executed successfully.") # Use debug for success
                return result
            except Exception as e:
                clean_error = redact_secrets(str(e))
                logger.error(f"Error in {func.__name__}: {clean_error}", exc_info=True) # Log full traceback
                raise e
        return sync_wrapper

