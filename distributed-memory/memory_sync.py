#!/usr/bin/env python3
"""
Distributed Hermes Memory — Supabase sync via REST API
No dependencies except requests
"""

import os
import time
import json
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    exit(1)

# ─── Config ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://<SUPABASE_URL>')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '<SUPABASE_KEY>')
NODE_ID = os.getenv('NODE_ID', 'unknown')

REST_URL = SUPABASE_URL + '/rest/v1/agent_state'
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

# ─── Local Cache ─────────────────────────────────────────────────────────────
_OTHER_NODES_CACHE = {}
_CACHE_TIMESTAMP = 0
CACHE_TTL = 30

# ─── Realtime ────────────────────────────────────────────────────────────────
_realtime_thread = None
_realtime_running = False


def is_cache_fresh():
    return (time.time() - _CACHE_TIMESTAMP) < CACHE_TTL


def humanize_age(iso_time):
    if not iso_time:
        return "unknown"
    then = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    delta = now - then
    
    if delta.days > 0:
        return "{}d {}h".format(delta.days, delta.seconds // 3600)
    elif delta.seconds >= 3600:
        return "{}h {}m".format(delta.seconds // 3600, (delta.seconds % 3600) // 60)
    elif delta.seconds >= 60:
        return "{}m".format(delta.seconds // 60)
    else:
        return "{}s".format(delta.seconds)


def pre_hook_inject_context(base_prompt):
    """Read other nodes state, inject into system prompt"""
    global _OTHER_NODES_CACHE, _CACHE_TIMESTAMP
    
    if is_cache_fresh() and _OTHER_NODES_CACHE:
        others = list(_OTHER_NODES_CACHE.values())
    else:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            params = {
                'select': 'node_id,status,current_task,summary,updated_at',
                'node_id': 'neq.' + NODE_ID,
                'updated_at': 'gt.' + cutoff,
                'order': 'updated_at.desc'
            }
            r = requests.get(REST_URL, headers=HEADERS, params=params, timeout=10)
            r.raise_for_status()
            others = r.json()
            
            _OTHER_NODES_CACHE = {node['node_id']: node for node in others}
            _CACHE_TIMESTAMP = time.time()
        except Exception as e:
            print("[MEMORY_SYNC] Error: {}".format(e))
            others = list(_OTHER_NODES_CACHE.values()) if _OTHER_NODES_CACHE else []
    
    if not others:
        return base_prompt
    
    lines = ["\nDISTRIBUTED STATE (other nodes):"]
    for node in others:
        age = humanize_age(node.get('updated_at'))
        lines.append(
            "\n{}:".format(node['node_id']) +
            "\n   Status: " + str(node.get('status', 'unknown')) +
            "\n   Task: " + str(node.get('current_task', 'idle')) +
            "\n   Summary: " + str(node.get('summary', 'n/a')) +
            "\n   Updated: " + age + " ago"
        )
    
    return base_prompt + "\n".join(lines)


def post_hook_save_state(status='active', current_task=None, summary=None, last_user_msg=None):
    """Save own state"""
    try:
        data = {
            'node_id': NODE_ID,
            'status': status,
            'current_task': current_task or 'idle',
            'last_user_message': (last_user_msg or '')[:200],
            'summary': (summary or '')[:500],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        r = requests.post(REST_URL, headers=HEADERS, json=data, timeout=10)
        
        # If conflict (node exists), update instead
        if r.status_code == 409:
            r = requests.patch(
                REST_URL + '?node_id=eq.' + NODE_ID,
                headers=HEADERS,
                json=data,
                timeout=10
            )
        
        r.raise_for_status()
        print("[MEMORY_SYNC] State saved: {}".format(status))
        return True
    except Exception as e:
        print("[MEMORY_SYNC] Error saving: {}".format(e))
        return False


def get_others_state():
    """Get cached state of other nodes"""
    return list(_OTHER_NODES_CACHE.values())


def get_node_state(node_id):
    """Get state of specific node"""
    return _OTHER_NODES_CACHE.get(node_id)


def refresh_cache():
    """Force refresh cache from server"""
    global _CACHE_TIMESTAMP
    _CACHE_TIMESTAMP = 0
    return pre_hook_inject_context("")


def watch_other_nodes(callback=None, interval=5):
    """Simple polling for changes (no websocket needed)"""
    global _realtime_running, _realtime_thread
    
    if _realtime_running:
        return
    
    _realtime_running = True
    
    def poll_loop():
        last_seen = {}
        while _realtime_running:
            try:
                cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                params = {
                    'select': 'node_id,updated_at,summary,status',
                    'node_id': 'neq.' + NODE_ID,
                    'updated_at': 'gt.' + cutoff,
                    'order': 'updated_at.desc'
                }
                r = requests.get(REST_URL, headers=HEADERS, params=params, timeout=10)
                if r.status_code == 200:
                    for node in r.json():
                        nid = node['node_id']
                        if nid not in last_seen or last_seen[nid] != node.get('updated_at'):
                            last_seen[nid] = node.get('updated_at')
                            _OTHER_NODES_CACHE[nid] = node
                            age = humanize_age(node.get('updated_at'))
                            print("[SYNC] {}: {} ({} ago)".format(
                                nid, (node.get('summary', ''))[:60], age))
                            if callback:
                                callback(node)
            except Exception as e:
                print("[MEMORY_SYNC] Poll error: {}".format(e))
            
            time.sleep(interval)
    
    import threading
    _realtime_thread = threading.Thread(target=poll_loop, daemon=True)
    _realtime_thread.start()
    print("[MEMORY_SYNC] Polling started (interval: {}s)".format(interval))


def stop_watching():
    global _realtime_running
    _realtime_running = False
    print("[MEMORY_SYNC] Polling stopped")


if __name__ == '__main__':
    print("Memory Sync Module (REST API)")
    print("=============================")
    print("Node:", NODE_ID)
    print("URL:", SUPABASE_URL)
    print("")
    
    print("Testing...")
    try:
        r = requests.get(REST_URL, headers=HEADERS, params={'select': 'node_id', 'limit': 1}, timeout=10)
        if r.status_code == 200:
            print("OK! Table accessible")
            print("Rows:", len(r.json()))
        else:
            print("Error:", r.status_code, r.text[:100])
    except Exception as e:
        print("Error:", e)
