# Distributed Memory System

Cross-node memory synchronization for Hermes Agent deployments. Enables multiple agents to share conversation history, state, and context via Supabase REST API.

## Overview

The distributed memory system allows Hermes agents running on different machines to:
- Share conversation history across nodes
- Sync agent state (status, current task, summary)
- Coordinate work between nodes
- Maintain persistent memory across sessions

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

### 1. sitecustomize.py
Python site-wide customization that hooks into Hermes Agent:
- Loads environment variables from `.env` files
- Patches AIAgent to save messages and update state
- Provides memory context from other nodes
- Installs import hook for dynamic patching

### 2. memory_sync.py
Core synchronization module:
- REST API client for Supabase
- Caches other nodes' state locally
- Provides functions to get other nodes' state
- Updates current node's state

### 3. memory_sync_wrapper.py
Wrapper for quick synchronization:
- Called at session start
- Reads other nodes' state
- Saves user messages
- Saves assistant responses

### 4. memory_save.py
Tool for saving messages and state:
- Command-line interface
- Saves messages with role (user/assistant/tool/system)
- Updates agent state (status/task/summary)
- Gets other nodes' state

## Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `agent_state` | Current state of each node | `node_id`, `status`, `current_task`, `summary`, `updated_at` |
| `session_history` | Full conversation history | `node_id`, `session_id`, `role`, `content`, `created_at` |
| `user_memory` | Long-term user preferences | `user_id`, `category`, `key`, `value` |
| `shared_tasks` | Task coordination | `task_id`, `assigned_to`, `status` |
| `node_logs` | Debug logs | `node_id`, `level`, `message`, `timestamp` |

## Configuration

### Environment Variables
```bash
# Node identification
NODE_ID=kozanout  # or frankfurt, nl-vps, etc.

# Supabase credentials (use environment variables, not hardcoded)
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>

# Optional: Custom paths
HERMES_HOME=/home/user/.hermes
```

### memory.env (Recommended)
```bash
# Node-specific configuration
NODE_ID=kozanout
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>
```

## Installation

### 1. Install sitecustomize.py
```bash
# Copy to Python site-packages
cp sitecustomize.py /usr/lib/python3.X/site-packages/

# Or for virtual environments
cp sitecustomize.py $VENV/lib/python3.X/site-packages/
```

### 2. Install memory tools
```bash
# Create tools directory
mkdir -p ~/.hermes/tools

# Copy tools
cp memory_sync.py ~/.hermes/
cp memory_sync_wrapper.py ~/.hermes/
cp memory_save.py ~/.hermes/tools/

# Make executable
chmod +x ~/.hermes/tools/memory_save.py
```

### 3. Configure environment
```bash
# Create memory.env
cat > ~/.hermes/memory.env << EOF
NODE_ID=your_node_name
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>
EOF
```

## Usage

### Check Other Nodes
```bash
# Get status of other nodes
python3 ~/.hermes/memory_sync_wrapper.py

# Or manually
python3 ~/.hermes/memory_sync.py --get-others
```

### Save Messages
```bash
# Save user message
python3 ~/.hermes/tools/memory_save.py --role user --content "User message"

# Save assistant response
python3 ~/.hermes/tools/memory_save.py --role assistant --content "Assistant response"
```

### Update State
```bash
# Set status to active
python3 ~/.hermes/tools/memory_save.py --update-state --status active --task "processing" --summary "Working on task"

# Set status to idle
python3 ~/.hermes/tools/memory_save.py --update-state --status idle --task "" --summary "Completed"
```

## Workflow

1. **Session Start**
   ```
   Agent starts → memory_sync_wrapper.py → get other nodes' state
   ```

2. **During Conversation**
   ```
   User message → save to session_history
   Assistant response → save to session_history
   ```

3. **Task Management**
   ```
   Start task → update_state(status=active, task="name")
   Complete task → update_state(status=idle, task="", summary="Done")
   ```

## Best Practices

### 1. Use Environment Variables
```python
# Good
SUPABASE_URL = os.getenv('SUPABASE_URL', 'default_url')

# Bad
SUPABASE_URL = 'https://actual-url.supabase.co'  # Exposed in code
```

### 2. Limit Content Size
```python
# Truncate large content
content = str(content)[:3000]  # Limit to 3000 characters
```

### 3. Handle Errors Gracefully
```python
try:
    # API call
    r = requests.post(url, json=data, timeout=10)
    if r.status_code not in (200, 201):
        print(f"Error: {r.status_code}")
except Exception as e:
    print(f"Exception: {e}")
```

### 4. Use Batch Operations
```python
# Save multiple messages at once
messages = [...]
BATCH = 100
for i in range(0, len(messages), BATCH):
    batch = messages[i:i+BATCH]
    requests.post(url, json=batch, timeout=30)
```

## Troubleshooting

### Common Issues

1. **"No module named 'memory_sync'"**
   - Check that memory_sync.py is in Python path
   - Ensure ~/.hermes/ is in sys.path

2. **"Connection timeout"**
   - Check network connectivity to Supabase
   - Verify SUPABASE_URL and SUPABASE_KEY are correct

3. **"Permission denied"**
   - Ensure scripts are executable: `chmod +x *.py`
   - Check file ownership: `chown -R user:user ~/.hermes/`

4. **"Duplicate entries"**
   - System uses content-based deduplication
   - Check for network retries causing duplicates

### Debug Mode
```python
# Enable verbose logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

1. **Never commit credentials** - Use environment variables
2. **Use anon key** - Not service_role key
3. **Restrict database access** - Use RLS policies
4. **Rotate keys regularly** - Supabase allows key rotation
5. **Monitor usage** - Supabase dashboard shows API calls

## Performance

- **Caching**: 30-second cache for other nodes' state
- **Batch operations**: Use batch inserts for multiple messages
- **Timeouts**: 10-30 second timeouts for API calls
- **Content limits**: Truncate large messages (3000 chars)

## Scaling

The system scales horizontally:
- Each node operates independently
- Supabase handles the coordination layer
- No single point of failure (except Supabase itself)
- Add new nodes by installing the same tools

## Monitoring

### Check Node Status
```sql
-- In Supabase SQL Editor
SELECT node_id, status, current_task, updated_at 
FROM agent_state 
ORDER BY updated_at DESC;
```

### View Recent Activity
```sql
SELECT node_id, role, LEFT(content, 50), created_at 
FROM session_history 
ORDER BY created_at DESC 
LIMIT 20;
```

## Integration with Hermes Agent

The distributed memory system integrates seamlessly:
- **Automatic**: sitecustomize.py patches AIAgent
- **Transparent**: Memory context appears in system prompt
- **Persistent**: Messages saved across sessions
- **Coordinated**: Multiple agents can collaborate

## Example: Multi-Node Setup

### Node A (kozanout)
```bash
NODE_ID=kozanout
# Runs as ngusev user
```

### Node B (frankfurt)
```bash
NODE_ID=frankfurt
# Runs as root user
```

### Node C (nl-vps)
```bash
NODE_ID=nl-vps
# Runs as root user
```

All nodes share the same Supabase project and can see each other's state.
