#!/usr/bin/env python3
"""
Unified Configuration for Distributed Memory System.
Loads from environment variables and optional .env file.
"""
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Base paths
HERMES_HOME = Path(os.getenv('HERMES_HOME', os.path.expanduser('~/.hermes')))
HERMES_TOOLS_DIR = HERMES_HOME / 'tools'

# Load .env file if exists
ENV_FILE = HERMES_HOME / 'memory.env'
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

# Supabase configuration
SUPABASE_URL: str = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY: str = os.getenv('SUPABASE_KEY', '')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_KEY must be set. "
        f"Create {ENV_FILE} with:\n"
        "SUPABASE_URL=https://<PROJECT>.supabase.co\n"
        "SUPABASE_KEY=<ANON_KEY>"
    )

# Node identification
NODE_ID: str = os.getenv('NODE_ID', '')
if not NODE_ID:
    raise RuntimeError(
        "NODE_ID must be set. "
        f"Add to {ENV_FILE}: NODE_ID=kozanout"
    )

# Session ID generation (deterministic per day)
def get_session_id() -> str:
    """Generate deterministic session ID based on node + date."""
    import hashlib
    day = datetime.now().strftime('%Y-%m-%d')
    raw = f"{NODE_ID}:{day}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]

SESSION_ID: str = get_session_id()

# API configuration
REST_URL = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

# Performance tuning
CACHE_TTL: int = int(os.getenv('MEMORY_CACHE_TTL', '30'))  # seconds
REQUEST_TIMEOUT: int = int(os.getenv('MEMORY_TIMEOUT', '10'))  # seconds
CONTENT_MAX_LENGTH: int = int(os.getenv('MEMORY_CONTENT_LIMIT', '4000'))

# Feature flags
ENABLE_RETRY: bool = os.getenv('MEMORY_ENABLE_RETRY', 'true').lower() == 'true'
RETRY_MAX_ATTEMPTS: int = int(os.getenv('MEMORY_RETRY_ATTEMPTS', '3'))
RETRY_BACKOFF_BASE: float = 1.0

# Debug
DEBUG: bool = os.getenv('MEMORY_DEBUG', 'false').lower() == 'true'

def log(msg: str) -> None:
    """Debug logging."""
    if DEBUG:
        print(f"[MEMORY_CONFIG] {msg}")

def validate() -> bool:
    """Validate configuration."""
    if not SUPABASE_URL.startswith('https://'):
        log("WARNING: SUPABASE_URL should use HTTPS")
    if len(NODE_ID) > 50:
        log("WARNING: NODE_ID is very long, may cause issues")
    return True

validate()
