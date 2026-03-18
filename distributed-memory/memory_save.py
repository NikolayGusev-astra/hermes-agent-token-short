#!/usr/bin/env python3
"""
Memory Save Tool — saves messages and state to Supabase
Called by Hermes Agent for distributed memory sync
"""
import os
import sys
import argparse
import json
from datetime import datetime, timezone

# Add paths
sys.path.insert(0, '/usr/local/lib/python3.7/dist-packages')
sys.path.insert(0, '/home/<USER>/hermes')

import requests

# Config
SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://<SUPABASE_URL>')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '<SUPABASE_KEY>')
NODE_ID = os.getenv('NODE_ID', 'kozanout')

REST_URL = SUPABASE_URL + '/rest/v1'
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal'
}


def save_message(role, content, session_id='default'):
    """Save a message to session_history"""
    data = {
        'node_id': NODE_ID,
        'session_id': session_id,
        'role': role,
        'content': content[:4000],  # Limit size
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    try:
        r = requests.post(REST_URL + '/session_history', headers=HEADERS, json=data, timeout=10)
        if r.status_code in [200, 201]:
            print("OK: Saved {} message ({} chars)".format(role, len(content)))
            return True
        else:
            print("ERROR: {} - {}".format(r.status_code, r.text[:100]))
            return False
    except Exception as e:
        print("ERROR: {}".format(e))
        return False


def update_state(status='idle', task=None, summary=None):
    """Update agent state"""
    data = {
        'node_id': NODE_ID,
        'status': status,
        'current_task': task or 'idle',
        'summary': (summary or '')[:500],
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # Try update first
        r = requests.patch(
            REST_URL + '/agent_state?node_id=eq.' + NODE_ID,
            headers=HEADERS,
            json=data,
            timeout=10
        )
        
        # If no rows updated, insert
        if r.status_code == 200 and 'Prefer: return=representation' not in str(r.text):
            count = len(r.json()) if r.text else 0
            if count == 0:
                r = requests.post(REST_URL + '/agent_state', headers=HEADERS, json=data, timeout=10)
        
        if r.status_code in [200, 201, 204]:
            print("OK: State updated (status={}, task={})".format(status, task))
            return True
        else:
            print("ERROR: {} - {}".format(r.status_code, r.text[:100]))
            return False
    except Exception as e:
        print("ERROR: {}".format(e))
        return False


def get_others():
    """Get state of other nodes"""
    try:
        r = requests.get(
            REST_URL + '/agent_state?select=node_id,status,current_task,summary,updated_at&node_id=neq.' + NODE_ID + '&order=updated_at.desc',
            headers={k: v for k, v in HEADERS.items() if k != 'Prefer'},
            timeout=10
        )
        
        if r.status_code == 200:
            data = r.json()
            if not data:
                print("No other nodes reporting")
                return []
            
            print("Other nodes:")
            for node in data:
                # Calculate age
                updated = node.get('updated_at', '')
                try:
                    then = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                    delta = datetime.now(timezone.utc) - then
                    if delta.days > 0:
                        age = "{}d".format(delta.days)
                    elif delta.seconds >= 3600:
                        age = "{}h".format(delta.seconds // 3600)
                    elif delta.seconds >= 60:
                        age = "{}m".format(delta.seconds // 60)
                    else:
                        age = "{}s".format(delta.seconds)
                except:
                    age = "?"
                
                print("  - {}: {} | {} | {} ago".format(
                    node.get('node_id', '?'),
                    node.get('status', '?'),
                    (node.get('summary', '') or '')[:50],
                    age
                ))
            return data
        else:
            print("ERROR: {}".format(r.status_code))
            return []
    except Exception as e:
        print("ERROR: {}".format(e))
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
    parser.add_argument('--status', default='idle', choices=['idle', 'active', 'busy', 'error'],
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
