#!/usr/bin/env python3
"""
Memory Sync Wrapper — вызывается агентом при каждом сообщении.
1. Читает состояние других нод
2. Сохраняет user message
3. Сохраняет assistant response (после ответа)
"""
import os
import sys
import argparse
from datetime import datetime, timezone
from typing import Optional

# Add hermes home to path
HERMES_HOME = os.path.expanduser('~/.hermes')
if HERMES_HOME not in sys.path:
    sys.path.insert(0, HERMES_HOME)

from memory_config import NODE_ID, CONTENT_MAX_LENGTH, DEBUG, log
from supabase_client import get_client


def save_session_message(role: str, content: str, session_id: str = 'default') -> bool:
    """Save message to session_history with deduplication."""
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
        
        # Use upsert to prevent duplicates
        success = client.post('session_history', data)
        
        if DEBUG:
            log(f"Saved {role} message: {len(content)} chars")
        
        return success
        
    except Exception as e:
        log(f"Error saving message: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Memory Sync Wrapper')
    parser.add_argument('--user-msg', type=str, help='User message to save')
    parser.add_argument('--assistant-msg', type=str, help='Assistant response to save')
    parser.add_argument('--task', type=str, help='Current task name')
    parser.add_argument('--summary', type=str, help='Task summary')
    parser.add_argument('--session', default='default', help='Session ID')
    args = parser.parse_args()

    print("=" * 50)
    print("DISTRIBUTED MEMORY SYNC")
    print("=" * 50)

    import memory_sync

    # 1. Read other nodes
    print("\nOther nodes:")
    memory_sync.refresh_cache()
    others = memory_sync.get_other_nodes()
    
    if others:
        for node in others:
            age = memory_sync._humanize_age(node.get('updated_at', ''))
            status = node.get('status', '?')
            summary = (node.get('summary', 'n/a') or '')[:50]
            print(f"  - {node['node_id']}: {status} | {summary} | {age} ago")
    else:
        print("  (no other nodes reporting)")

    # 2. Save user message if provided
    if args.user_msg:
        save_session_message('user', args.user_msg, args.session)
        
        # Also update state
        memory_sync.save_state(
            status='active',
            current_task=args.task or 'processing',
            summary=args.summary or args.user_msg[:100],
            last_user_msg=args.user_msg
        )

    # 3. Save assistant message if provided
    if args.assistant_msg:
        save_session_message('assistant', args.assistant_msg, args.session)
        print(f"Saved assistant message: {len(args.assistant_msg)} chars")

    # 4. Update state if task provided
    if args.task:
        memory_sync.save_state(
            status='active',
            current_task=args.task,
            summary=args.summary or ''
        )

    print("\nSync complete")
    print("=" * 50)


if __name__ == '__main__':
    main()
