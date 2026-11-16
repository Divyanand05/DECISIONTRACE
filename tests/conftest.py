"""
Shared pytest fixtures.
"""
import os
import sys
from pathlib import Path

import pytest

# Ensure the project root is on PYTHONPATH so imports work from any test runner
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point tests at a test-only database URL if set
def pytest_configure(config):
    test_db = os.environ.get("TEST_DATABASE_URL")
    if test_db:
        os.environ["DATABASE_URL"] = test_db
