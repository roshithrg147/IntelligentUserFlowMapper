import os
import json
import inspect
from functools import wraps

LOG_FILE = "results/function_results.log"

# Ensure directory exists
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def log_result(func):
    """Decorator to log function calls and their results."""
    
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            _write_log(func.__module__, func.__name__, result)
            return result
        return async_wrapper
    else:
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            _write_log(func.__module__, func.__name__, result)
            return result
        return sync_wrapper

def _write_log(module_name, func_name, result):
    try:
        if isinstance(result, (dict, list)):
            res_str = f"[Complex Object: {type(result).__name__}, length={len(result)}]"
        else:
            res_str = str(result)
            if len(res_str) > 2000:
                res_str = res_str[:2000] + "... [truncated]"
            
        log_entry = json.dumps({
            "module": module_name,
            "function": func_name,
            "result": res_str
        })
        
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        # Failsafe logging in case string conversion or JSON serialization fails
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "module": module_name,
                "function": func_name,
                "error_logging": str(e)
            }) + "\n")
