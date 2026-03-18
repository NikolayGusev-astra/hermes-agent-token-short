#!/usr/bin/env python3
"""
Memory Save Tool — saves messages and state to Supabase.
Called by Hermes Agent for distributed memory sync.
"""
import os
import sys
import argparse
from datetime import datetime, timezone

# Add hermes home to path
HERMES_HOME = os.path.expanduser('~/.hermes')
if HERMES_HOME not in sys.path:
    sys.path.insert(0, HERMES_HOME)

from memory_config import NODE_ID, CONTENT_MAX_LENGTH, DEBUG, log
from supabase_client import get_client


def save_message(role: str, content: str, session_id: str = 'default') -> bool:
    """Save a message to session_history with deduplication."""
    try:
        client = get_client()
        
        # Generate idempotent message ID
        message_id = client._make_hash_id(role, content)
        
        data = {
            'node_id': NODE_ID,
            'session_id': session_id,
            'role': role,
            'content': content[:CONTENT_MAX_LENGTH],
            'message_id': message_id,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        success = client.post('session_history', data)
        
        if success:
            print(f"OK: Saved {role} message ({len(content)} chars)")
        else:
            print(f"ERROR: Failed to save message")
        
        return success
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def update_state(
    status: str = 'idle',
    task: str = None,
    summary: str = None
) -> bool:
    """Update agent state."""
    try:
        client = get_client()
        
        data = {
            'node_id': NODE_ID,
            'status': status,
            'current_task': task or 'idle',
            'summary': (summary or '')[:500],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        success = client.upsert_state('agent_state', data, key_field='node_id')
        
        if success:
            print(f"OK: State updated (status={status}, task={task})")
        else:
            print(f"ERROR: Failed to update state")
        
        return success
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def get_others() -> list:
    """Get state of other nodes."""
    try:
        client = get_client()
        
        nodes = client.get(
            'agent_state',
            select='node_id,status,current_task,summary,updated_at',
            filters={'node_id': f'neq.{NODE_ID}'},
            order='updated_at.desc'
        )
        
        if not nodes:
            print("No other nodes reporting")
            return []
        
        print("Other nodes:")
        for node in nodes:
            # Calculate age
            updated = node.get('updated_at', '')
            try:
                then = datetime.fromisoformat(updated.replace('Z', '+00:00'))
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
            
            print(f"  - {node.get('node_id', '?')}: {node.get('status', '?')} | "
                  f"{(node.get('summary', '') or '')[:50]} | {age} ago")
        
        return nodes
        
    except Exception as e:
        print(f"ERROR: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description='Memory Save Tool')
    
    # Message mode
    parser.add_argument('--role', choices=['user', 'assistant', 'tool', 'system'],
                       help='Message role')
    parser.add_argument('--content', type=str, help='Message content')
    parser.add_argument('--session', default='default', help='Session ID')
    
    # State mode
    parser.add_argument('--update-state', action='store_true', help='Update agent state')
    parser.add_argument('--status', default='idle', choices=['idle', 'active', 'busy', 'error', 'offline'],
                       help='Agent status')
    parser.add_argument('--task', type=str, help='Current task name')
    parser.add_argument('--summary', type=str, help='Task summary')
    
    # Get others mode
    parser.add_argument('--get-others', action='store_true', help='Get other nodes state')
    
    args = parser.parse_args()
    
    if args.role and args.content:
        save_message(args.role, args.content, args.session)
    elif args.update_state:
        update_state(args.status, args.task, args.summary)
    elif args.get_others:
        get_others()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
