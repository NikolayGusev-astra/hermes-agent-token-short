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

### 1. memory_config.py
Unified configuration module:
- Loads environment variables from `.env` files
- Validates required configuration
- Provides constants for all modules

### 2. supabase_client.py
Base REST API client:
- Singleton pattern for connection reuse
- Retry with exponential backoff
- Automatic content truncation
- Message deduplication via `message_id`

### 3. sitecustomize.py
Python site-wide customization:
- Loads environment variables from `.env` files
- Patches AIAgent to save messages and update state
- Provides memory context from other nodes
- Installs import hook for dynamic patching

### 4. memory_sync.py
Core synchronization module:
- REST API client for Supabase
- Caches other nodes' state locally
- Provides functions to get other nodes' state
- Updates current node's state

### 5. memory_sync_wrapper.py
Wrapper for quick synchronization:
- Called at session start
- Reads other nodes' state
- Saves user messages
- Saves assistant responses

### 6. memory_save.py
Tool for saving messages and state:
- Command-line interface
- Saves messages with role (user/assistant/tool/system)
- Updates agent state (status/task/summary)
- Gets other nodes' state

## Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `agent_state` | Current state of each node | `node_id`, `status`, `current_task`, `summary`, `updated_at` |
| `session_history` | Full conversation history | `node_id`, `session_id`, `role`, `content`, `message_id`, `created_at` |

## Configuration

### Environment Variables
```bash
# Node identification
NODE_ID=kozanout  # or frankfurt, nl-vps, etc.

# Supabase credentials (use environment variables, not hardcoded)
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>

# Optional: Custom paths and tuning
HERMES_HOME=/home/user/.hermes
MEMORY_CACHE_TTL=30
MEMORY_TIMEOUT=10
MEMORY_CONTENT_LIMIT=4000
MEMORY_ENABLE_RETRY=true
MEMORY_RETRY_ATTEMPTS=3
MEMORY_DEBUG=false
```

### memory.env (Recommended)
```bash
# Node-specific configuration
NODE_ID=kozanout
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>
```

## Installation

### 1. Install memory modules
```bash
# Create hermes directory
mkdir -p ~/.hermes/tools

# Copy all modules
cp memory_config.py supabase_client.py memory_sync.py ~/.hermes/
cp memory_sync_wrapper.py ~/.hermes/
cp memory_save.py ~/.hermes/tools/

# Copy sitecustomize to site-packages
cp sitecustomize.py /usr/lib/python3.X/site-packages/
# Or for virtual environments
cp sitecustomize.py $VENV/lib/python3.X/site-packages/

# Make executable
chmod +x ~/.hermes/tools/memory_save.py
```

### 2. Configure environment
```bash
# Create memory.env
cat > ~/.hermes/memory.env << EOF
NODE_ID=your_node_name
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>
EOF

# Set permissions
chmod 600 ~/.hermes/memory.env
```

## Usage

### Check Other Nodes
```bash
# Get status of other nodes
python3 ~/.hermes/memory_sync_wrapper.py --get-others

# Or manually
python3 ~/.hermes/memory_sync.py
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
   Agent starts → sitecustomize.py loads → get other nodes' state
   ```

2. **During Conversation**
   ```
   User message → save to session_history (with deduplication)
   Assistant response → save to session_history
   ```

3. **Task Management**
   ```
   Start task → update_state(status=active, task="name")
   Complete task → update_state(status=idle, task="", summary="Done")
   ```

4. **Shutdown**
   ```
   SIGTERM/SIGINT → save final state (offline) → exit
   ```

## Key Features

### Idempotent Messages
Each message gets a unique `message_id` based on:
- Node ID
- Session ID
- Role
- Content (first 100 chars)
- Timestamp

This prevents duplicates when:
- Agent restarts
- Network retries
- Multiple saves of same message

### Retry Logic
Automatic retry with exponential backoff:
- Transient errors (429, 500-504)
- Timeouts
- Up to 3 attempts by default

### Graceful Shutdown
- SIGTERM/SIGINT handlers
- Final state saved before exit
- No lost updates on restart

## Best Practices

### 1. Use Environment Variables
```python
# Good - uses memory_config.py
from memory_config import NODE_ID, SUPABASE_URL

# Environment variables are loaded automatically
# from ~/.hermes/memory.env
```

### 2. Limit Content Size
```python
# Automatic truncation
# Content over LIMIT is truncated before sending
CONTENT_MAX_LENGTH = 4000  # default
```

### 3. Handle Errors Gracefully
```python
# All functions return bool for success/failure
success = save_message('user', 'Hello')
if not success:
    # Handle error - already logged
    pass
```

### 4. Use Batch Operations
```python
# Save multiple messages at once - each is idempotent
for msg in messages:
    save_message(msg['role'], msg['content'])
```

## Troubleshooting

### Common Issues

1. **"SUPABASE_URL and SUPABASE_KEY must be set"**
   - Check that ~/.hermes/memory.env exists
   - Verify format: `KEY=value` (no spaces around =)

2. **"NODE_ID must be set"**
   - Add `NODE_ID=your_name` to config

3. **"No module named 'memory_sync'"**
   - Check that files are in ~/.hermes/
   - Ensure ~/.hermes/ is in Python path

4. **"Connection timeout"**
   - Check network connectivity to Supabase
   - Verify SUPABASE_URL and SUPABASE_KEY are correct

5. **"Duplicate entries"**
   - Should not happen with message_id deduplication
   - Check database has unique constraint on message_id

### Debug Mode
```bash
# Enable debug logging
export MEMORY_DEBUG=true
python3 ~/.hermes/memory_sync.py
```

## Security Considerations

1. **Never commit credentials** - Use environment variables
2. **Use anon key** - Not service_role key
3. **Restrict database access** - Use RLS policies
4. **Rotate keys regularly** - Supabase allows key rotation
5. **Monitor usage** - Supabase dashboard shows API calls

## Performance

- **Caching**: 30-second cache for other nodes' state
- **Retry**: Exponential backoff with 3 attempts
- **Timeouts**: 10-second default for API calls
- **Content limits**: Truncate large messages (4000 chars default)
- **Dedup**: message_id prevents duplicates

## Database Schema (SQL)

```sql
-- agent_state table
CREATE TABLE agent_state (
    node_id TEXT PRIMARY KEY,
    status TEXT DEFAULT 'idle',
    current_task TEXT DEFAULT 'idle',
    summary TEXT,
    last_user_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- session_history table (with deduplication)
CREATE TABLE session_history (
    id SERIAL PRIMARY KEY,
    node_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    message_id TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient queries
CREATE INDEX idx_session_history_node ON session_history(node_id, session_id);
CREATE INDEX idx_session_history_created ON session_history(created_at DESC);
CREATE INDEX idx_agent_state_updated ON agent_state(updated_at DESC);
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

## Version History

### v2.0 (Current)
- Unified configuration via memory_config.py
- Base client with retry and deduplication
- Deterministic session IDs
- Graceful shutdown handlers
- Improved error handling

### v1.0 (Legacy)
- Original implementation
- Hardcoded URLs and keys
- No retry logic
- Session leaks on restart
