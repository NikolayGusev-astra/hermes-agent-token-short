# Distributed Memory for Hermes Agent

Cross-node memory synchronization system for Hermes Agent deployments. Enables multiple AI agents running on different machines to share conversation history, state, and context.

## Features

- **Cross-node synchronization**: Multiple agents share conversation history
- **State management**: Track what each node is doing
- **Persistent memory**: Conversations survive across sessions
- **Real-time coordination**: Nodes can see each other's status
- **Idempotent operations**: Deduplication prevents duplicate messages
- **Graceful shutdown**: State saved on SIGTERM/SIGINT
- **Retry logic**: Automatic retry with exponential backoff

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

## Quick Start

### 1. Configuration

Create `~/.hermes/memory.env`:
```bash
# Node identification
NODE_ID=your_node_name

# Supabase credentials
SUPABASE_URL=https://<PROJECT_ID>.supabase.co
SUPABASE_KEY=<ANON_KEY>
```

### 2. Installation

```bash
# Create hermes directory
mkdir -p ~/.hermes/tools

# Copy all files
cp memory_config.py supabase_client.py memory_sync.py ~/.hermes/
cp memory_sync_wrapper.py ~/.hermes/
cp memory_save.py ~/.hermes/tools/
cp sitecustomize.py /usr/lib/python3.X/site-packages/

# Make executable
chmod +x ~/.hermes/tools/memory_save.py
```

### 3. Usage

```bash
# Check other nodes
python3 ~/.hermes/memory_sync_wrapper.py --get-others

# Save message
python3 ~/.hermes/tools/memory_save.py --role user --content "Hello"

# Update state
python3 ~/.hermes/tools/memory_save.py --update-state --status active --task "working"
```

## Components

| Component | File | Purpose |
|-----------|------|---------|
| Config | `memory_config.py` | Unified configuration with env support |
| Client | `supabase_client.py` | REST API client with retry/dedup |
| Hooks | `sitecustomize.py` | Patches AIAgent to auto-save messages |
| Sync Core | `memory_sync.py` | Core synchronization functions |
| Wrapper | `memory_sync_wrapper.py` | Quick sync at session start |
| Tool | `memory_save.py` | CLI tool for saving messages/state |

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ID` | required | Unique node identifier |
| `SUPABASE_URL` | required | Supabase project URL |
| `SUPABASE_KEY` | required | Supabase anon key |
| `HERMES_HOME` | `~/.hermes` | Base directory for config |
| `MEMORY_CACHE_TTL` | `30` | Cache TTL in seconds |
| `MEMORY_TIMEOUT` | `10` | Request timeout in seconds |
| `MEMORY_CONTENT_LIMIT` | `4000` | Max content length |
| `MEMORY_ENABLE_RETRY` | `true` | Enable retry logic |
| `MEMORY_RETRY_ATTEMPTS` | `3` | Max retry attempts |
| `MEMORY_DEBUG` | `false` | Enable debug logging |

## Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `agent_state` | Current state of each node | `node_id`, `status`, `current_task`, `summary`, `updated_at` |
| `session_history` | Full conversation history | `node_id`, `session_id`, `role`, `content`, `message_id`, `created_at` |

## Database Schema

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
    message_id TEXT UNIQUE,  -- for deduplication
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS (recommended)
ALTER TABLE agent_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_history ENABLE ROW LEVEL SECURITY;

-- RLS policies (adjust for your needs)
CREATE POLICY "Allow all for authenticated" ON agent_state FOR ALL USING (true);
CREATE POLICY "Allow all for authenticated" ON session_history FOR ALL USING (true);
```

## Key Improvements (v2.0)

### 1. Unified Configuration
- Single config file (`memory_config.py`)
- Environment variables from `.env` file
- Validation at startup

### 2. Base Client
- Retry with exponential backoff
- Automatic idempotent message IDs
- Content truncation
- Graceful error handling

### 3. Session ID
- Deterministic per node + date
- Survives agent restarts
- `message_id` field for deduplication

### 4. Graceful Shutdown
- SIGTERM/SIGINT handlers
- Final state saved on exit

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
- Content limits (4000 chars default)
- Retry with exponential backoff

## Troubleshooting

### "SUPABASE_URL and SUPABASE_KEY must be set"
Check that `~/.hermes/memory.env` exists with correct values.

### "NODE_ID must be set"
Add `NODE_ID=kozanout` to your config.

### "No module named 'memory_sync'"
Ensure `~/.hermes/` is in Python path or files are copied correctly.

### "Connection timeout"
Check network connectivity and Supabase project status.

## Integration

The system integrates with Hermes Agent:
- **Automatic**: Hooks patch AIAgent at import time
- **Transparent**: Memory context in system prompt
- **Persistent**: Messages saved across sessions
- **Coordinated**: Multiple agents collaborate
