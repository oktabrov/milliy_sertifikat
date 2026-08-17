"""Test environment.

These must be set before anything imports `app.config`, because the settings
object is cached. Real environment variables outrank the developer's own .env
file, so a local .env with the live bot token cannot leak into a test run.
"""

from __future__ import annotations

import os
import tempfile

TEST_BOT_TOKEN = "123456:test-token-not-real"

os.environ["BOT_TOKEN"] = TEST_BOT_TOKEN
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="testbot-data-")
os.environ["USE_POLLING"] = "false"
os.environ["WEBHOOK_BASE"] = ""
os.environ["REQUIRED_CHANNELS"] = ""
os.environ["ADMIN_IDS"] = ""
os.environ["COHORT_SIZE"] = "800"
os.environ["MIN_REAL_SUBMISSIONS"] = "20"
