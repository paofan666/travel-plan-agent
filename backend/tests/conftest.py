"""Keep automated tests isolated from developer credentials and live services."""

import os


os.environ["LLM_API_KEY"] = ""
os.environ["LLM_BASE_URL"] = ""
os.environ["AMAP_API_KEY"] = ""
os.environ["ENABLE_AMAP_ENRICHMENT"] = "false"
os.environ["REDIS_ENABLED"] = "false"
