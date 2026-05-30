import os
import pytest

# Force fake mode for all tests — set BEFORE any app imports
os.environ["LLM_MODE"] = "fake"
