#!/usr/bin/env python3
"""
Memory Sync Wrapper — вызывается агентом при каждом сообщении
1. Читает состояние других нод
2. Сохраняет user message
3. Сохраняет assistant response (после ответа)
"""
import os
import sys
import argparse

sys.path.insert(0, '/usr/local/lib/python3.7/dist-packages')
sys.path.insert(0, '/home/<USER>/hermes')

os.environ.setdefault('NODE_ID', 'kozanout')

import memory_sync

def main():
    parser = argparse.ArgumentParser(description='Memory Sync Wrapper')
    parser.add_argument('--user-msg', type=str, help='User message to save')
    parser.add_argument('--assistant-msg', type=str, help='Assistant response to save')
    parser.add_argument('--task', type=str, help='Current task name')
    parser.add_argument('--summary', type=str, help='Task summary')
    args = parser.parse_args()

    print("=" * 50)
    print("DISTRIBUTED MEMORY SYNC")
    print("=" * 50)

    # 1. Read other nodes
    print("\nOther nodes:")
    memory_sync.refresh_cache()
    others = memory_sync.get_others_state()
    
    if others:
        for node in others:
            age = memory_sync.humanize_age(node.get('updated_at', ''))
            status = node.get('status', '?')
            summary = (node.get('summary', 'n/a'))[:50]
            print("  - {}: {} | {} | {} ago".format(
                node['node_id'], status, summary, age
            ))
    else:
        print("  (no other nodes reporting)")

    # 2. Save user message if provided
    if args.user_msg:
        memory_sync.post_hook_save_state(
            status='active',
            current_task=args.task or 'processing',
            summary=args.summary or args.user_msg[:100],
            last_user_msg=args.user_msg
        )
        # Also save to session_history
        import requests
        url = 'https://<SUPABASE_URL>'
        key = '<SUPABASE_KEY>'
        headers = {'apikey': key, 'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
        from datetime import datetime, timezone
        data = {
            'node_id': os.environ.get('NODE_ID', 'kozanout'),
            'session_id': 'default',
            'role': 'user',
            'content': args.user_msg[:4000],
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        r = requests.post(url + '/rest/v1/session_history', headers=headers, json=data, timeout=10)
        print("\nSaved user message: {} chars".format(len(args.user_msg)))

    # 3. Save assistant message if provided
    if args.assistant_msg:
        import requests
        url = 'https://<SUPABASE_URL>'
        key = '<SUPABASE_KEY>'
        headers = {'apikey': key, 'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
        from datetime import datetime, timezone
        data = {
            'node_id': os.environ.get('NODE_ID', 'kozanout'),
            'session_id': 'default',
            'role': 'assistant',
            'content': args.assistant_msg[:4000],
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        r = requests.post(url + '/rest/v1/session_history', headers=headers, json=data, timeout=10)
        print("Saved assistant message: {} chars".format(len(args.assistant_msg)))

    # 4. Update state if task provided
    if args.task:
        memory_sync.post_hook_save_state(
            status='active',
            current_task=args.task,
            summary=args.summary or ''
        )

    print("\nSync complete")
    print("=" * 50)

if __name__ == '__main__':
    main()
