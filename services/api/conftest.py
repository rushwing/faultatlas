import os
import sys
from pathlib import Path

# Ensure the service root is on the path so `app.*` imports resolve
sys.path.insert(0, str(Path(__file__).parent))

# Provide required env vars so Settings() can be instantiated without a .env file
os.environ.setdefault("OPENAI_API_KEY", "test-key")
