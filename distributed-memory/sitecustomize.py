#!/usr/bin/env python3
"""
Distributed Memory Hooks for Hermes Agent.
Automatically patches AIAgent to sync memory across nodes.
"""
import os
import sys
import signal
import importlib
from datetime import datetime, timezone
from typing import Optional, Any

# Add hermes home to path
HERMES_HOME = os.path.expanduser('~/.hermes')
if HERMES_HOME not in sys.path:
    sys.path.insert(0, HERMES_HOME)

# Import after path setup
try:
    from memory_config import (
        NODE_ID, SESSION_ID, CONTENT_MAX_LENGTH, DEBUG, log
    )
    from supabase_client import get_client
    CONFIG_LOADED = True
except RuntimeError as e:
    print(f"[Memory Hooks] ⚠️ Config not loaded: {e}")
    CONFIG_LOADED = False
except ImportError as e:
    print(f"[Memory Hooks] ⚠️ Import error: {e}")
    CONFIG_LOADED = False


_hooked = False
_original_init = None
_original_run = None


def _get_memory_context() -> str:
    """Fetch other nodes state and format for system prompt."""
    if not CONFIG_LOADED:
        return ""
    
    try:
        client = get_client()
        
        # Get nodes updated in last 30 minutes
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        
        nodes = client.get(
            'agent_state',
            select='node_id,status,current_task,summary,updated_at',
            filters={'node_id': f'neq.{NODE_ID}', 'updated_at': f'gt.{cutoff}'},
            order='updated_at.desc'
        )
        
        if not nodes:
            return ""
        
        lines = ["\n\nDISTRIBUTED STATE (other nodes):"]
        for n in nodes:
            try:
                then = datetime.fromisoformat(n.get('updated_at', '').replace('Z', '+00:00'))
                delta = datetime.now(timezone.utc) - then
                if delta.days > 0:
                    age = f"{delta.days}d"
                elif delta.seconds >= 3600:
                    age = f"{delta.seconds // 3600}h"
                elif delta.seconds >= 60:
                    age = f"{delta.seconds // 60}m"
                else:
                    age = f"{delta.seconds}s"
            except Exception:
                age = "?"
            
            lines.append(
                f"  * {n.get('node_id', '?')}: {n.get('status', '?')} | "
                f"{n.get('current_task', '-')} | {(n.get('summary', '') or '')[:50]} | {age} ago"
            )
        
        return "\n".join(lines)
        
    except Exception as e:
        if DEBUG:
            log(f"Error getting context: {e}")
        return ""


def _save_message(role: str, content: str) -> bool:
    """Save message to session_history with deduplication."""
    if not CONFIG_LOADED:
        return False
    
    try:
        client = get_client()
        message_id = client._make_hash_id(role, content)
        
        data = {
            'node_id': NODE_ID,
            'session_id': SESSION_ID,
            'role': role,
            'content': str(content)[:CONTENT_MAX_LENGTH],
            'message_id': message_id,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        client.post('session_history', data)
        return True
        
    except Exception as e:
        if DEBUG:
            log(f"Error saving message: {e}")
        return False


def _update_state(status: str = 'active', task: str = None, summary: str = None) -> bool:
    """Update current node state."""
    if not CONFIG_LOADED:
        return False
    
    try:
        client = get_client()
        
        data = {
            'node_id': NODE_ID,
            'status': status,
            'current_task': task or 'idle',
            'summary': (summary or '')[:500],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        client.upsert_state('agent_state', data, key_field='node_id')
        return True
        
    except Exception as e:
        if DEBUG:
            log(f"Error updating state: {e}")
        return False


def _do_patch() -> None:
    """Patch AIAgent to inject memory hooks."""
    global _hooked, _original_init, _original_run
    
    if _hooked:
        return
    
    if not CONFIG_LOADED:
        print("[Memory Hooks] ⚠️ Cannot patch - config not loaded")
        return
    
    try:
        # Try to import run_agent
        import run_agent
        
        if not hasattr(run_agent, 'AIAgent'):
            print("[Memory Hooks] ⚠️ AIAgent not found in run_agent")
            return
        
        _original_init = run_agent.AIAgent.__init__
        _original_run = run_agent.AIAgent.run_conversation
        
        def patched_init(self, *args, **kwargs):
            """Patch __init__ to inject memory context."""
            existing = kwargs.get('ephemeral_system_prompt') or ''
            kwargs['ephemeral_system_prompt'] = existing + _get_memory_context()
            _original_init(self, *args, **kwargs)
            _update_state('active', 'ready', 'Agent started')
        
        def patched_run(self, *args, **kwargs):
            """Patch run_conversation to save messages."""
            # Save user message
            if args:
                msg = args[0]
                if isinstance(msg, str):
                    _save_message('user', msg)
                elif isinstance(msg, dict):
                    content = str(msg.get('content', msg))
                    _save_message('user', content)
            
            result = _original_run(self, *args, **kwargs)
            
            # Save assistant response
            if result:
                _save_message('assistant', str(result)[:CONTENT_MAX_LENGTH])
                _update_state('active', 'ready', str(result)[:80])
            
            return result
        
        run_agent.AIAgent.__init__ = patched_init
        run_agent.AIAgent.run_conversation = patched_run
        _hooked = True
        
        print(f"[Memory Hooks] ✅ Agent patched! (node: {NODE_ID})")
        
    except ImportError as e:
        print(f"[Memory Hooks] ⚠️ run_agent not available yet: {e}")
    except Exception as e:
        print(f"[Memory Hooks] ⚠️ Patch failed: {e}")


def _graceful_shutdown(signum=None, frame=None) -> None:
    """Handle shutdown to save final state."""
    if CONFIG_LOADED:
        _update_state('offline', 'shutdown', 'Agent stopped')
    sys.exit(0)


# Register shutdown handlers
signal.signal(signal.SIGTERM, _graceful_shutdown)
signal.signal(signal.SIGINT, _graceful_shutdown)


# Try to patch immediately
if CONFIG_LOADED:
    print(f"[Memory Hooks] ✅ Loading (node: {NODE_ID}, session: {SESSION_ID})")
    _do_patch()

# Hook import for delayed patching
try:
    import builtins
    _original_import = builtins.__import__
    
    def hooked_import(name: str, *args, **kwargs):
        """Intercept imports to patch when run_agent becomes available."""
        result = _original_import(name, *args, **kwargs)
        
        if name == 'run_agent' and not _hooked and CONFIG_LOADED:
            try:
                _do_patch()
            except Exception as e:
                print(f"[Memory Hooks] ⚠️ Delayed patch failed: {e}")
        
        return result
    
    builtins.__import__ = hooked_import
    print("[Memory Hooks] ✅ Import hook installed")
    
except Exception as e:
    print(f"[Memory Hooks] ⚠️ Hook error: {e}")
