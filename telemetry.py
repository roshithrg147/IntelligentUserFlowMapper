import structlog
from prometheus_client import Gauge, Histogram, Counter

# --- Metrics ---
ACTIVE_BROWSER_CONTEXTS = Gauge(
    "active_browser_contexts", 
    "Number of currently active browser contexts"
)
MAPPING_DURATION = Histogram(
    "mapping_duration_seconds", 
    "Time spent mapping a user flow",
    ["domain"]
)
FAILURE_RATE = Counter(
    "failure_rate_by_domain", 
    "Failures during crawl operations per domain",
    ["domain", "error_type"]
)

# --- Logging Setup ---
def setup_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

setup_logging()
logger = structlog.get_logger("UIFlowMapper")
