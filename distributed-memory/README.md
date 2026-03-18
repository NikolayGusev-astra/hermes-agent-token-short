# Distributed Memory for Hermes Agent

Cross-node memory synchronization system for Hermes Agent deployments. Enables multiple AI agents running on different machines to share conversation history, state, and context.

## Features

- **Cross-node synchronization**: Multiple agents share conversation history
- **State management**: Track what each node is doing
- **Persistent memory**: Conversations survive across sessions
- **Real-time coordination**: Nodes can see each other's status
- **Lightweight**: Uses only REST API calls, no complex infrastructure

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Node A     │     │  Node B     │     │  Node C     │
│  (kozanout) │     │ (frankfurt) │     │  (nl-vps)   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                    ┌─────────────┐
                    │  Supabase   │
                    │  (REST API) │
                    └─────────────┘
```

## Components

| Component | File | Purpose |
|-----------|------|---------|
| Hooks | `sitecustomize.py` | Patches AIAgent to auto-save messages |
| Sync Core | `memory_sync.py` | REST API client for Supabase |
| Wrapper | `memory_sync_wrapper.py` | Quick sync at session start |
| Tool | `memory_save.py` | CLI tool for saving messages/state |

## Quick Start

### 1. Configuration

Create `~/.hermes/memory.env`:
```bash
NODE_ID=your_node_name
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>
```

### 2. Installation

```bash
# Copy files to ~/.hermes/
cp memory_sync.py memory_sync_wrapper.py ~/.hermes/
cp memory_save.py ~/.hermes/tools/
cp sitecustomize.py /usr/lib/python3.X/site-packages/

# Make executable
chmod +x ~/.hermes/tools/memory_save.py
```

### 3. Usage

```bash
# Check other nodes
python3 ~/.hermes/memory_sync_wrapper.py

# Save message
python3 ~/.hermes/tools/memory_save.py --role user --content "Hello"

# Update state
python3 ~/.hermes/tools/memory_save.py --update-state --status active --task "working"
```

## Tables

| Table | Purpose |
|-------|---------|
| `agent_state` | Current state of each node |
| `session_history` | Full conversation history |
| `user_memory` | Long-term user preferences |
| `shared_tasks` | Task coordination between nodes |
| `node_logs` | Debug logs |

## How It Works

1. **Session Start**: `memory_sync_wrapper.py` reads other nodes' state
2. **During Conversation**: Messages auto-saved via `sitecustomize.py` hooks
3. **State Updates**: Agents update their status as tasks progress
4. **Cross-node View**: Any node can query others' current state

## Documentation

See [DISTRIBUTED_MEMORY.md](DISTRIBUTED_MEMORY.md) for detailed documentation including:
- Installation instructions
- Configuration options
- API reference
- Troubleshooting
- Security best practices

## Code Examples

### Save Message
```python
import requests

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

def save_message(node_id, session_id, role, content):
    url = f"{SUPABASE_URL}/rest/v1/session_history"
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'node_id': node_id,
        'session_id': session_id,
        'role': role,
        'content': content[:3000],  # Limit size
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    r = requests.post(url, headers=headers, json=data, timeout=10)
    return r.status_code in (200, 201)
```

### Get Other Nodes
```python
def get_other_nodes(my_node_id):
    url = f"{SUPABASE_URL}/rest/v1/agent_state"
    params = {
        'node_id': f'neq.{my_node_id}',
        'order': 'updated_at.desc'
    }
    headers = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}
    r = requests.get(url, headers=headers, params=params, timeout=5)
    return r.json() if r.status_code == 200 else []
```

### Update State
```python
def update_state(node_id, status, task, summary):
    url = f"{SUPABASE_URL}/rest/v1/agent_state?node_id=eq.{node_id}"
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    }
    data = {
        'node_id': node_id,
        'status': status,
        'current_task': task,
        'summary': summary[:500],
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    r = requests.patch(url, headers=headers, json=data, timeout=10)
    return r.status_code in (200, 201)
```

## Security

- Use environment variables for credentials
- Never commit API keys to version control
- Use anon key (not service_role key)
- Enable RLS policies in Supabase
- Rotate keys regularly

## Performance

- 30-second cache for other nodes' state
- Batch inserts for multiple messages
- 10-30 second timeouts
- Content limits (3000 chars)

## Integration

The system integrates with Hermes Agent:
- **Automatic**: Hooks patch AIAgent at import time
- **Transparent**: Memory context in system prompt
- **Persistent**: Messages saved across sessions
- **Coordinated**: Multiple agents collaborate
