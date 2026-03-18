#!/usr/bin/env python3
"""
Distributed Hermes Memory — Supabase sync via REST API.
Uses unified config and Supabase client.
"""
import os
import sys
import time
import threading
import signal
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Callable

# Add hermes home to path
HERMES_HOME = os.path.expanduser('~/.hermes')
if HERMES_HOME not in sys.path:
    sys.path.insert(0, HERMES_HOME)

from memory_config import (
    NODE_ID, CACHE_TTL, DEBUG, log
)
from supabase_client import get_client


# Local cache
_other_nodes_cache: Dict = {}
_cache_timestamp: float = 0
_cache_lock = threading.Lock()

# Realtime polling
_realtime_thread: Optional[threading.Thread] = None
_realtime_running = False


def _humanize_age(iso_time: str) -> str:
    """Convert ISO timestamp to human-readable age."""
    if not iso_time:
        return "unknown"
    try:
        then = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = now - then
        
        if delta.days > 0:
            return f"{delta.days}d {delta.seconds // 3600}h"
        elif delta.seconds >= 3600:
            return f"{delta.seconds // 3600}h {(delta.seconds % 3600) // 60}m"
        elif delta.seconds >= 60:
            return f"{delta.seconds // 60}m"
        else:
            return f"{delta.seconds}s"
    except Exception:
        return "unknown"


def is_cache_fresh() -> bool:
    """Check if cache is still valid."""
    return (time.time() - _cache_timestamp) < CACHE_TTL


def get_other_nodes(force_refresh: bool = False) -> List[Dict]:
    """Get state of other nodes from cache or API."""
    global _other_nodes_cache, _cache_timestamp
    
    with _cache_lock:
        if is_cache_fresh() and _other_nodes_cache and not force_refresh:
            return list(_other_nodes_cache.values())
        
        try:
            client = get_client()
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            
            others = client.get(
                'agent_state',
                select='node_id,status,current_task,summary,updated_at',
                filters={'node_id': f'neq.{NODE_ID}', 'updated_at': f'gt.{cutoff}'},
                order='updated_at.desc'
            )
            
            _other_nodes_cache = {node['node_id']: node for node in (others or [])}
            _cache_timestamp = time.time()
            
            if DEBUG:
                log(f"Fetched {len(_other_nodes_cache)} other nodes")
            
            return list(_other_nodes_cache.values())
            
        except Exception as e:
            log(f"Error fetching nodes: {e}")
            return list(_other_nodes_cache.values()) if _other_nodes_cache else []


def inject_context(base_prompt: str) -> str:
    """Read other nodes state, inject into system prompt."""
    others = get_other_nodes()
    
    if not others:
        return base_prompt
    
    lines = ["\n\nDISTRIBUTED STATE (other nodes):"]
    for node in others:
        age = _humanize_age(node.get('updated_at'))
        lines.append(
            f"\n{node['node_id']}:"
            f"\n   Status: {node.get('status', 'unknown')}"
            f"\n   Task: {node.get('current_task', 'idle')}"
            f"\n   Summary: {node.get('summary', 'n/a')}"
            f"\n   Updated: {age} ago"
        )
    
    return base_prompt + "".join(lines)


def save_state(
    status: str = 'active',
    current_task: Optional[str] = None,
    summary: Optional[str] = None,
    last_user_msg: Optional[str] = None
) -> bool:
    """Save current node state to database."""
    try:
        client = get_client()
        
        data = {
            'node_id': NODE_ID,
            'status': status,
            'current_task': current_task or 'idle',
            'last_user_message': (last_user_msg or '')[:200] if last_user_msg else '',
            'summary': (summary or '')[:500],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        success = client.upsert_state('agent_state', data, key_field='node_id')
        
        if DEBUG:
            log(f"State saved: {status}")
        
        return success
        
    except Exception as e:
        log(f"Error saving state: {e}")
        return False


def get_node_state(node_id: str) -> Optional[Dict]:
    """Get state of specific node from cache."""
    with _cache_lock:
        return _other_nodes_cache.get(node_id)


def refresh_cache() -> None:
    """Force refresh cache from server."""
    global _cache_timestamp
    _cache_timestamp = 0
    get_other_nodes(force_refresh=True)


def watch_other_nodes(callback: Optional[Callable] = None, interval: int = 5) -> None:
    """Start polling for changes in other nodes."""
    global _realtime_running, _realtime_thread
    
    if _realtime_running:
        return
    
    _realtime_running = True
    
    def poll_loop():
        last_seen = {}
        while _realtime_running:
            try:
                client = get_client()
                cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                
                others = client.get(
                    'agent_state',
                    select='node_id,updated_at,summary,status,current_task',
                    filters={'node_id': f'neq.{NODE_ID}', 'updated_at': f'gt.{cutoff}'},
                    order='updated_at.desc'
                )
                
                if others:
                    for node in others:
                        nid = node['node_id']
                        updated = node.get('updated_at')
                        
                        if nid not in last_seen or last_seen[nid] != updated:
                            last_seen[nid] = updated
                            
                            with _cache_lock:
                                _other_nodes_cache[nid] = node
                            
                            age = _humanize_age(updated)
                            log(f"{nid}: {node.get('summary', '')[:60]} ({age} ago)")
                            
                            if callback:
                                callback(node)
                                
            except Exception as e:
                log(f"Poll error: {e}")
            
            time.sleep(interval)
    
    _realtime_thread = threading.Thread(target=poll_loop, daemon=True)
    _realtime_thread.start()
    log(f"Polling started (interval: {interval}s)")


def stop_watching() -> None:
    """Stop polling for node changes."""
    global _realtime_running
    _realtime_running = False
    log("Polling stopped")


def graceful_shutdown(signum=None, frame=None) -> None:
    """Handle shutdown signals gracefully."""
    log("Shutting down...")
    stop_watching()
    save_state('offline', 'shutdown', 'Agent stopped')
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGTERM, graceful_shutdown)
signal.signal(signal.SIGINT, graceful_shutdown)


if __name__ == '__main__':
    print("Memory Sync Module (REST API)")
    print("=" * 40)
    print(f"Node: {NODE_ID}")
    print(f"Session: {os.getenv('SESSION_ID', 'N/A')}")
    print("")
    
    print("Testing connection...")
    try:
        client = get_client()
        nodes = client.get('agent_state', select='node_id', limit=1)
        print(f"OK! Table accessible, {len(nodes or [])} rows")
    except Exception as e:
        print(f"Error: {e}")
