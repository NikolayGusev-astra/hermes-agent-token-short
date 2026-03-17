# Hermes Agent Token Optimization Guide

Comprehensive strategies for reducing LLM token consumption in Hermes Agent deployments — from zero-cost config tweaks to architectural redesigns.

## Table of Contents

- [Anatomy of a Single API Call](#anatomy-of-a-single-api-call)
- [Token Budget per Layer](#token-budget-per-layer)
- [Optimization Strategies](#optimization-strategies)
  - [Layer 0: Zero-Cost Config Changes](#layer-0-zero-cost-config-changes)
  - [Layer 1: Platform-Aware Context](#layer-1-platform-aware-context)
  - [Layer 2: Adaptive Tool Routing](#layer-2-adaptive-tool-routing)
  - [Layer 3: Smart Skill Selection](#layer-3-smart-skill-selection)
  - [Layer 4: Schema Compression](#layer-4-schema-compression)
  - [Layer 5: History & Compression](#layer-5-history--compression)
  - [Layer 6: Model Routing](#layer-6-model-routing)
  - [Layer 7: Architectural Patterns](#layer-7-architectural-patterns)
- [Harness Quality (Indirect Token Savings)](#harness-quality-indirect-token-savings)
  - [Hashline-Enhanced File Editing](#hashline-enhanced-file-editing)
  - [TTSR (Time Traveling Streaming Rules)](#ttsr-time-traveling-streaming-rules)
  - [Workspace Files Optimization](#workspace-files-from-openclaw-anatomy)
- [Offline Batch Processing (No API Costs)](#offline-batch-processing-no-api-costs)
  - [MOEX Backtesting Pipeline](#scenario-moex-backtesting-with-local-models)
  - [Provider Independence](#7e-provider-independence-resilience-layer)
- [Use Case Matrix](#use-case-matrix)
- [Implementation Roadmap](#implementation-roadmap)
- [Anti-Patterns](#anti-patterns)

---

## Anatomy of a Single API Call

Every message sent to the LLM contains these components:

```
┌─────────────────────────────────────────┐
│ SYSTEM PROMPT (~7-8K tokens)            │
│  ├─ Agent identity (~130 tok)           │
│  ├─ Behavioral guidance (~190 tok)      │
│  ├─ Persistent memory (MEMORY.md)       │
│  ├─ User profile (USER.md)              │
│  ├─ Skills index (all descriptions)     │  ← often oversized
│  ├─ Context files (AGENTS.md, SOUL.md)  │  ← often unnecessary
│  ├─ Platform hint (~110 tok)            │
│  └─ Timestamp (~15 tok)                 │
├─────────────────────────────────────────┤
│ TOOL SCHEMAS (~8-9K tokens)             │
│  ├─ Full JSON schemas for every tool    │  ← the biggest block
│  ├─ Parameter descriptions              │
│  └─ Enum values, defaults               │
├─────────────────────────────────────────┤
│ CONVERSATION HISTORY (grows each turn)  │
│  ├─ Previous user messages              │
│  ├─ Previous assistant responses        │
│  ├─ Tool call definitions               │
│  └─ Tool results (often huge)           │  ← runaway growth
├─────────────────────────────────────────┤
│ CURRENT USER MESSAGE (~few tokens)      │
└─────────────────────────────────────────┘
```

**Baseline (typical "привет" in Telegram with 30 tools, full skills):**
- System prompt text: ~31K chars (~7.8K tokens)
- Tool schemas: ~35K chars (~8.7K tokens)
- Minimum per call: **~16.5K tokens**

---

## Token Budget per Layer

| Layer | Chars | Tokens | % of baseline | Removable? |
|-------|-------|--------|---------------|------------|
| Identity + guidance | 1,700 | ~425 | 2.6% | No — core |
| Memory + user profile | 3,200 | ~800 | 4.8% | Partially |
| Skills index | 12,000+ | ~3,000 | 18.2% | Yes — heavily |
| Context files (AGENTS.md) | 14,000+ | ~3,500 | 21.2% | Yes — by platform |
| Platform hint | 450 | ~110 | 0.7% | No — tiny |
| Tool schemas (30 tools) | 35,000 | ~8,750 | 53.0% | Partially |
| Conversation history | variable | variable | grows | Compress |
| **Total minimum** | **~66K** | **~16.5K** | **100%** | |

---

## Optimization Strategies

### Layer 0: Zero-Cost Config Changes

No code changes. Flip existing config flags.

#### 0a. Skip context files for messaging platforms

AGENTS.md, .cursorrules, and SOUL.md are development guides loaded into every API call. In messaging platforms (Telegram, WhatsApp, Signal, Discord) they are almost never relevant.

```yaml
# config.yaml — already supported via AIAgent param
skip_context_files: true  # or pass per-platform
```

**Savings: ~3,500 tokens per call (-21%)**
**Risk: Zero** — context files are only needed in CLI/coding scenarios. If a messaging user references a project, the agent can use file tools to read it on demand.

#### 0b. Platform-specific ephemeral system prompt

The `ephemeral_system_prompt` config option lets you inject a short note per platform. Use it to tell the agent it's in messaging mode and doesn't need to consider coding context.

```yaml
# For telegram/discord gateway
ephemeral_system_prompt: "You are in messaging mode. Skip coding context unless explicitly asked."
```

**Savings: Indirect — prevents unnecessary tool calls**
**Risk: Minimal**

#### 0c. Reduce memory file sizes

MEMORY.md and USER.md are injected into every call. Keep them under 2KB combined.

**Savings: variable**
**Risk: If you over-trim, the agent forgets important context**

#### 0d. Reset long sessions proactively

Conversation history grows unboundedly. Even with compression, accumulated tool results bloat the context. Implement auto-reset hints.

```yaml
# config.yaml
display:
  session_reset_hint_at: 50  # warn user after N messages
```

**Savings: Prevents runaway growth (saves 50-200K tokens in long sessions)**
**Risk: Losing conversation context — but compression handles this**

---

### Layer 1: Platform-Aware Context

Make context loading conditional on platform and task type.

#### 1a. Platform-gated skills index

Not all skills are relevant for all platforms. A Telegram user never needs `mlops/training/axolotl`.

```python
# In skill frontmatter (SKILL.md):
---
name: axolotl
description: Fine-tune LLMs with Axolotl
metadata:
  hermes:
    platforms: ["cli"]  # Only show in CLI mode
---
```

Then in `prompt_builder.py`, filter by platform:

```python
def build_skills_system_prompt(platform: str = None, ...):
    # Skip skills that don't match current platform
    if not skill_matches_platform(frontmatter, platform):
        continue
```

**Categorization by relevance:**

| Category | CLI | Telegram | Discord | Cron |
|----------|-----|----------|---------|------|
| mlops/* (39 skills) | ✅ | ❌ | ❌ | ❌ |
| github/* (6 skills) | ✅ | ⚠️ rare | ⚠️ rare | ❌ |
| gaming/* (2 skills) | ✅ | ❌ | ❌ | ❌ |
| research/* (11 skills) | ✅ | ⚠️ | ⚠️ | ⚠️ |
| finance/* (9 skills) | ✅ | ✅ | ✅ | ✅ |
| devops/* (3 skills) | ✅ | ✅ | ✅ | ✅ |
| smart-home (1) | ✅ | ✅ | ⚠️ | ✅ |
| productivity/* (6) | ✅ | ⚠️ | ⚠️ | ✅ |

**Savings: ~2,000 tokens per call (-12%)**
**Risk: Minimal** — skills are opt-in loaded anyway. If the agent needs a hidden skill, it can `skills_list` to discover it.

#### 1b. Platform-specific toolsets

Define separate toolsets per platform with different tool scopes:

```python
"hermes-telegram-lite": {
    "tools": [
        "web_search", "web_extract",
        "terminal", "process",
        "read_file", "write_file", "search_files",
        "memory", "session_search",
        "clarify", "send_message",
        "text_to_speech",
        "todo",
        "skills_list", "skill_view", "skill_manage",
        "cronjob",
    ],
    # NO browser tools, NO execute_code, NO patch, NO delegate
}
```

**Savings: ~5,000 tokens from removed schemas (-30%)**
**Risk: Medium** — user loses instant access to removed tools. Mitigate with `skills_list` fallback or `/tools` toggle.

---

### Layer 2: Adaptive Tool Routing

Dynamically select which tool schemas to include based on the user's message.

#### 2a. Rule-based classifier (zero dependencies)

A fast regex/keyword matcher that categorizes queries before building the prompt:

```python
TOOL_ROUTING_RULES = {
    "web_query": {
        "patterns": [r"найд[иі]", r"search", r"google", r"погода", r"что такое"],
        "tools": ["web_search", "web_extract", "browser_*"],
    },
    "file_query": {
        "patterns": [r"прочитай", r"покажи файл", r"read", r"cat "],
        "tools": ["read_file", "search_files"],
    },
    "coding": {
        "patterns": [r"исправ[ьи]", r"напиш[иі] код", r"баг", r"fix", r"debug"],
        "tools": "all",  # include everything
        "context_files": True,  # also load AGENTS.md
    },
    "system": {
        "patterns": [r"запусти", r"выполни", r"systemctl", r"service"],
        "tools": ["terminal", "process", "read_file"],
    },
    "simple": {  # fallback
        "patterns": [],
        "tools": ["web_search", "terminal", "read_file", "memory", "clarify", "send_message"],
    },
}

def route_tools(message: str) -> list[str]:
    for category, config in TOOL_ROUTING_RULES.items():
        for pattern in config["patterns"]:
            if re.search(pattern, message, re.IGNORECASE):
                return config["tools"]
    return TOOL_ROUTING_RULES["simple"]["tools"]
```

**Caveat:** Tool schemas must include all tools the model might want to call. If the classifier misses, the model won't have access to the needed tool. Mitigation: always include a "core" set (terminal, memory, read_file, web_search) regardless of routing.

**Savings: 40-60% of tool schema tokens on simple queries**
**Risk: Medium** — misclassification blocks needed tools. Use generous "core set" as safety net.

#### 2b. Embedding-based router (lightweight)

Pre-compute skill/tool embeddings, match at query time:

```python
# Dependencies: sentence-transformers (~80MB model), numpy
from sentence_transformers import SentenceTransformer
import numpy as np

class ToolRouter:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')  # 80MB
        self.tool_embeddings = {}  # pre-computed
        
    def preload(self, tool_definitions: list[dict]):
        for tool in tool_definitions:
            desc = tool["function"]["description"]
            self.tool_embeddings[tool["function"]["name"]] = \
                self.model.encode(desc)
    
    def select_tools(self, query: str, top_k: int = 15) -> list[str]:
        query_emb = self.model.encode(query)
        scores = {
            name: np.dot(query_emb, emb) 
            for name, emb in self.tool_embeddings.items()
        }
        # Always include core tools
        core = {"terminal", "memory", "read_file", "send_message", "clarify"}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        selected = core | {name for name, _ in ranked[:top_k]}
        return list(selected)
```

**Latency:** ~5ms on CPU for embedding + cosine.
**Memory:** ~200MB (model + numpy + overhead).

**Savings: 30-50% of tool schema tokens**
**Risk: Low** — core tools always included, embedding is surprisingly good at matching intents to descriptions.

#### 2c. Two-pass invocation (for complex routing)

First call with minimal tools + classifier, second call with full tools if needed:

```
Turn 1: user message → call with [web_search, terminal, memory, clarify]
        If model responds normally → done
        If model says "I need tool X" → proceed to Turn 2

Turn 2: same message → call with full toolset
```

**Savings: 70% on queries that resolve in pass 1**
**Risk: High latency (2x API calls), doubled cost on pass-2 queries.** Only viable for very cheap models on pass 1.

---

### Layer 3: Smart Skill Selection

Skills index is the third-largest token consumer. Replace "all skills listed" with "relevant skills only."

#### 3a. Category-based gating (zero cost)

Add `platforms` field to skill frontmatter, filter at prompt build time. Same as Layer 1a but more granular:

```yaml
---
name: tensorrt-llm
description: Optimizes LLM inference with NVIDIA TensorRT
metadata:
  hermes:
    platforms: ["cli"]
    requires_tools: ["terminal", "execute_code"]
    requires_env: ["CUDA_VISIBLE_DEVICES"]
---
```

If `requires_tools` lists tools not in the current toolset, skip the skill.

**Savings: 40-70% of skills index depending on platform**
**Risk: Minimal — `skills_list` tool always available for discovery**

#### 3b. Lazy skill loading with search

Instead of listing all skills in the system prompt, provide only the `skills_list` and `skill_view` tools:

```
System prompt: (no skills index at all)

User: "help me fine-tune a model"
Agent: calls skills_list(query="fine-tune") → gets top matches
Agent: calls skill_view("axolotl") → loads instructions
Agent: follows instructions
```

**Savings: ~3,000 tokens (entire skills index)**
**Risk: Medium** — adds 1-2 tool calls to every skill-related task. The model might not think to search for skills. Mitigation: strong instruction in system prompt.

#### 3c. Semantic skill index (compact)

Replace the full skills listing with a dense format:

```
# Before (12,000 chars):
## mlops:
  - axolotl: Expert guidance for fine-tuning LLMs with Axolotl
  - accelerate: Simplest distributed training API...
  - flash-attention: Optimizes transformer attention...
  ... (39 entries with descriptions)

# After (2,000 chars):
## Skills (use skills_list to discover):
  mlops: training, inference, evaluation, vector-dbs (39 skills)
  finance: trading, backtest, market analysis (9 skills)
  research: papers, arxiv, OSINT (11 skills)
  devops: kozanout-ssh, disk-cleanup, wireguard (3 skills)
  productivity: google-workspace, notion, pdf, pptx (6 skills)
  ... (category names + counts only)
```

**Savings: ~2,500 tokens**
**Risk: Low** — agent uses `skills_list` for details

#### 3d. Pre-computed skill embeddings + query match

Same approach as tool routing (Layer 2b) but for skills:

```python
class SkillRouter:
    def select_skills(self, query: str, top_k: int = 5) -> list[str]:
        query_emb = self.model.encode(query)
        # Returns top_k most relevant skill names
        # Build mini-index with only those skills
```

**Savings: ~2,500 tokens (12K → 2K chars)**
**Risk: Very low** — model still has `skills_list` as fallback

---

### Layer 4: Schema Compression

Tool schemas are the single largest token consumer. Compress them.

#### 4a. Short descriptions for messaging

Maintain two description sets per tool — full (CLI) and compact (messaging):

```python
# In tool registration:
registry.register(
    name="terminal",
    description="Execute shell commands on a Linux environment...",
    description_short="Run shell commands. Returns output and exit code.",
    parameters={...},
)
```

**Savings: ~2,000 tokens across all tools**
**Risk: Minimal** — model understands short descriptions fine

#### 4b. Remove optional parameters from schemas

Many tools have rarely-used optional parameters. Strip them for messaging:

```python
# Full schema:
terminal(command, timeout=180, workdir=None, background=False, 
         check_interval=30, pty=False)

# Messaging schema:
terminal(command, timeout=180)
```

Model can still call with defaults; for advanced usage, CLI mode has full schemas.

**Savings: ~1,500 tokens**
**Risk: Low** — defaults work for 95% of cases

#### 4c. Enum compression

Some schemas list huge enums. Compress or remove:

```python
# Before: 200 chars
"direction": {"type": "string", "enum": ["up", "down"], 
              "description": "Scroll direction, either up or down"}

# After: 60 chars  
"direction": {"type": "string", "enum": ["up", "down"]}
```

**Savings: ~500 tokens**
**Risk: Minimal**

#### 4d. Schema $ref deduplication

If multiple tools share parameter types (e.g., file paths), use JSON Schema `$ref` to define once. Note: not all OpenAI-compatible APIs support `$ref` in tool schemas.

**Savings: ~500-1,000 tokens**
**Risk: Compatibility** — test with your provider

---

### Layer 5: History & Compression

Conversation history grows linearly with each turn. Unchecked, it becomes the dominant cost.

#### 5a. Context compression (already implemented)

Hermes Agent's `ContextCompressor` summarizes middle turns when context exceeds threshold (default 50%). Uses a cheap model (e.g., Gemini Flash) to compress.

**Key settings:**
```python
ContextCompressor(
    threshold_percent=0.50,     # compress at 50% context
    protect_first_n=3,          # always keep first 3 turns
    protect_last_n=4,           # always keep last 4 turns
    summary_target_tokens=2500, # aim for 2.5K token summary
)
```

**Savings: 40-80% of history tokens in long sessions**
**Risk: Information loss in compression** — tune `protect_last_n` higher for critical tasks

#### 5b. Tool result truncation

Tool results (especially `terminal` output, `web_extract` content) can be thousands of tokens. Truncate aggressively:

```python
# In tool handler:
MAX_TOOL_RESULT_TOKENS = 2000
if len(result) > MAX_TOOL_RESULT_TOKENS * 4:
    result = result[:MAX_TOOL_RESULT_TOKENS*4] + \
             "\n\n[Truncated — use offset/limit params for more]"
```

**Savings: Variable — can save 5-20K tokens per tool call**
**Risk: Model might miss important context from truncated output.** Mitigate with smart truncation (keep head + tail).

#### 5c. Separate system context from conversation

Use prompt caching (Anthropic's cache_control) to mark the system prompt + tool schemas as cached prefix. Subsequent calls within 5 minutes only pay the "write" cost (1.25x) once, then 0.1x for cache reads.

**Already implemented** in Hermes Agent via `apply_anthropic_cache_control()`.

**Savings: 75-90% cost on cached prefix (not tokens, but dollars)**
**Risk: Cache breaks if system prompt changes mid-conversation** (hence the "don't modify prompt mid-session" policy)

#### 5d. Periodic session hygiene

Auto-compress or reset sessions that exceed token thresholds:

```python
# Gateway already implements:
# - Auto-compression at 50% context
# - Warning at 80% context
# - Suggest /reset at 90% context
```

Enhancement: auto-summarize and reset when session exceeds N turns:

```python
MAX_SESSION_TURNS = 40
if turn_count > MAX_SESSION_TURNS:
    # Summarize entire session
    # Store summary as initial message in new session
    # Reset conversation
```

**Savings: Prevents unbounded growth**
**Risk: Loss of fine-grained history**

---

### Layer 6: Model Routing

Not every query needs the most capable (and most expensive) model.

#### 6a. Tiered model selection

```python
QUERY_CLASSIFICATION = {
    "simple": {  # greetings, small talk, simple lookups
        "model": "anthropic/claude-haiku-4.5",  # cheap, fast
        "max_iterations": 5,
    },
    "normal": {  # file reads, web searches, routine tasks
        "model": "anthropic/claude-sonnet-4",
        "max_iterations": 20,
    },
    "complex": {  # coding, debugging, multi-step analysis
        "model": "anthropic/claude-opus-4.6",
        "max_iterations": 90,
    },
}
```

Routing via the same rule-based or embedding classifier from Layer 2.

**Savings: 50-90% cost on simple queries (not tokens, but dollars)**
**Risk: Haiku may fail on tasks that seem simple but aren't.** Use escalation: if Haiku fails, retry with Sonnet.

#### 6b. Small model for tool routing, big model for reasoning

Two-stage pipeline:
1. Cheap model classifies the query and selects tools/skills
2. Expensive model gets the trimmed context and selected tools

```python
# Stage 1: qwen2.5:0.5b or Haiku (local or API)
classification = small_model.call(
    messages=[{"role": "user", "content": f"Classify: {query}"}],
    tools=None,  # no tools for classifier
    response_format={"type": "json_object"}  # structured output
)
# Returns: {"category": "web_search", "skills": ["web"], 
#           "needs_browser": false, "needs_coding": false}

# Stage 2: Sonnet/Opus with trimmed context
result = full_agent.run_conversation(
    message=query,
    enabled_toolsets=classification["toolsets"],
    skills=classification["skills"],
)
```

**Savings: 40-60% total cost (fewer tokens in stage 1, trimmed stage 2)**
**Risk: Classification errors cascade. Latency: +200-500ms.**

---

### Layer 7: Architectural Patterns

#### 7a. Stateless micro-agents

Instead of one monolithic agent with 30 tools, deploy specialized agents:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Web Agent    │     │ File Agent   │     │ System Agent │
│ 4 tools      │     │ 5 tools      │     │ 4 tools      │
│ web_search   │     │ read_file    │     │ terminal     │
│ web_extract  │     │ write_file   │     │ process      │
│ browser_*    │     │ search_files │     │ cronjob      │
│ (10 tools)   │     │ patch        │     │ (4 tools)    │
└──────────────┘     └──────────────┘     └──────────────┘
       ↑                    ↑                    ↑
       └──────────── Router Agent ───────────────┘
                  (3 tools: delegate + clarify + memory)
```

Router Agent (3 tools, ~3K token schemas) classifies and delegates.
Each specialist gets only its relevant schemas (~3-5K tokens each).

**Total: ~8-10K tokens per call instead of 16.5K**
**Savings: 40-50%**
**Risk: Multi-hop latency, delegation overhead, context loss between agents**

#### 7b. Prompt caching optimization

Structure the system prompt for maximum cache stability:

```
[CACHED PREFIX — stable across all turns]
1. Identity
2. Behavioral guidance  
3. Tool schemas
4. Platform hint
5. Skills index

[VARIABLE — changes per turn]
6. Memory (only changes on /memory updates)
7. Current timestamp
8. Ephemeral system prompt
9. Conversation history
```

With Anthropic's `cache_control`, mark the boundary at point 5. Everything above is cached for 5 minutes.

**Already partially implemented.** Enhancement: move Memory into the variable section only when it changes, not every turn.

**Savings: 75-90% cost reduction on the cached portion**
**Risk: Cache invalidation on any change above the breakpoint**

#### 7c. Streaming + early termination

For simple queries, stream the response and terminate tool calls early:

```python
# If streaming shows the model is just saying "Hi! How can I help?"
# without calling any tools, we can:
# 1. Skip sending tool schemas entirely
# 2. Use a cheaper model for the next turn
```

**Savings: Prevents unnecessary tool call iterations**
**Risk: Complex to implement correctly**

#### 7d. Local embedding model for classification (no GPU)

Use a CPU-optimized embedding model loaded in-process:

```python
# Dependencies: onnxruntime (~15MB) + model weights (~80MB)
# Latency: ~3ms on modern CPU
# Memory: ~200MB peak

from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

class LocalClassifier:
    def __init__(self):
        self.model = ORTModelForFeatureExtraction.from_pretrained(
            "sentence-transformers/all-MiniLM-L6-v2",
            export=True  # auto-convert to ONNX
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            "sentence-transformers/all-MiniLM-L6-v2"
        )
    
    def embed(self, text: str) -> np.ndarray:
        inputs = self.tokenizer(text, return_tensors="pt", 
                                truncation=True, max_length=128)
        outputs = self.model(**inputs)
        return outputs.last_hidden_state.mean(dim=1).detach().numpy()
```

This runs on a $5/mo VPS with no GPU. Handles ~200 classifications/second.

**Savings: Enables Layer 2b, 3d at near-zero runtime cost**
**Risk: None — purely additive capability**

#### 7e. Provider independence (resilience layer)

Critical for deployments in jurisdictions with potential API access restrictions. Design for graceful degradation:

```
Priority 1: OpenRouter (broad model selection, pay-as-you-go)
Priority 2: Direct provider API (Anthropic, OpenAI, Google)  
Priority 3: Local models via Ollama/vLLM (full offline)
Priority 4: Cached responses + rule-based fallbacks (emergency)
```

**Multi-provider router:**
```python
PROVIDER_CHAIN = [
    {"provider": "openrouter", "model": "anthropic/claude-sonnet-4", "fallback_on": ["403", "451"]},
    {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "fallback_on": ["rate_limit"]},
    {"provider": "local", "model": "qwen2.5:14b", "fallback_on": ["oom"]},
    {"provider": "local", "model": "qwen2.5:3b", "fallback_on": []},  # always works
]
```

**Local models for offline processing:**
| Model | RAM | Use case | Latency |
|-------|-----|----------|---------|
| qwen2.5:3b (Q4) | ~2GB | Classification, routing, simple tasks | 5-15 tok/s CPU |
| qwen2.5:7b (Q4) | ~4GB | Summarization, moderate reasoning | 3-8 tok/s CPU |
| qwen2.5:14b (Q4) | ~8GB | Complex tasks, code generation | 1-4 tok/s CPU |
| all-MiniLM-L6-v2 | ~250MB | Embeddings, semantic search | ~3ms/query |

**Savings: Not about tokens — about survival.** Local models cost $0/token.
**Risk: Quality significantly lower than frontier models. Use for batch/offline only.**

---

## Harness Quality (Indirect Token Savings)

Not all token waste comes from oversized prompts. A significant portion comes from **tool execution failures** that force retry loops — each retry is a full API round-trip.

### Hashline-Enhanced File Editing

Current file editing tools require the model to reproduce content character-perfectly to identify what to change. This fails frequently on:

- Whitespace/indentation mismatches
- Multi-match ambiguity (same string appears twice)
- Large files where the model "forgets" exact content

**Hashline approach:** When the model reads a file, every line gets a content hash:

```
# read_file output with hashlines:
  1:a3f|# Config
  2:b12|DEBUG = True
  3:c8e|PORT = 8080
  4:d91|HOST = "0.0.0.0"
```

The model edits by referencing hashes instead of reproducing content:

```
# patch_hashline call:
patch_hashline(path="/app/config.py", operations=[
  {"action": "replace", "line": "b12", "content": "DEBUG = False"},
  {"action": "insert_after", "line": "d91", "content": "WORKERS = 4"},
])
```

**Benefits:**
- No whitespace reproduction needed → fewer failures
- File-change detection: if hash doesn't match → file was modified → reject safely
- Works across all models uniformly (no format bias)

**Token savings:** Indirect. Each failed patch retry costs ~16.5K tokens (full API call). With 20% failure rate on edit tasks, hashline eliminates ~3.3K tokens per editing task on average.

### TTSR (Time Traveling Streaming Rules)

Rules that inject themselves into the conversation only when triggered by the model's output — zero upfront context cost.

**Traditional approach (expensive):**
```
System prompt: "Do not use deprecated API X. Follow pattern Y. 
Remember constraint Z. Always check condition W..."
→ All rules cost tokens on EVERY call, regardless of relevance
```

**TTSR approach (free until triggered):**
```python
TTSR_RULES = [
    {
        "name": "no-deprecated-api",
        "trigger": r"import.*deprecated_module",  # regex on output stream
        "inject": "System: The model is using deprecated API. Use new_api instead.",
        "once_per_session": True,
    },
    {
        "name": "test-required",
        "trigger": r"def test_|class Test",
        "inject": "System: When writing tests, use pytest fixtures.",
        "once_per_session": True,
    },
]
```

Rules are watched client-side on the output stream. When a pattern matches:
1. Stream aborts mid-response
2. Rule injects as a system reminder
3. Request retries with the new context
4. Rule deactivates for the session

**Token savings:** Rules that never trigger = 0 tokens. Only relevant rules activate. Typical saving: 500-2,000 tokens per session for coding tasks.

### Workspace Files (from OpenClaw anatomy)

Hermes Agent already supports workspace files. Optimization strategy:

| File | Current behavior | Optimized behavior | Savings |
|------|-----------------|-------------------|---------|
| AGENTS.md | Always loaded (14K chars) | Gate on coding tasks only | -3,500 tok on messaging |
| SOUL.md | Always loaded (537 chars) | Keep — tiny, always relevant | — |
| MEMORY.md | Always loaded (2.8K chars) | Keep — core continuity | — |
| USER.md | Always loaded (395 chars) | Keep — tiny | — |
| IDENTITY.md | Not exists | Create (~200 chars), extract from AGENTS.md | Enables AGENTS.md skip |
| TOOLS.md | Not exists | Create (~200 chars), paths to local scripts | -1 tool call per system query |
| YYYY-MM-DD.md | Not exists | Cron writes daily summary | Free context on next day |
| HEARTBEAT.md | Not exists | Optional, <500 chars, periodic tasks only | Adds context, use sparingly |

**New files to create:**

```markdown
# IDENTITY.md (~100 chars)
My name is Hermes, AI assistant. Concise, technical, efficient.

# TOOLS.md (~200 chars)  
Trading: /opt/trading-system/scripts/
VPN: /opt/xray-subscription/
Security: /opt/security-cam/
Cron: /opt/hermes-agent/cron/

# 2026-03-17.md (daily log, written by cron)
## Completed
- Optimized token consumption analysis
- Added Hashline research to guide
## In progress
- Token optimization Phase 1
## Decisions
- Skip AGENTS.md for messaging platforms
- Platform-gate mlops skills to CLI only
```

---

## Offline Batch Processing (No API Costs)

For workloads like backtesting, news aggregation, or bulk file processing, running entirely offline eliminates API costs and provider dependency risks.

### Architecture

```
┌──────────────────────────────────────────────────────┐
│                OFFLINE PIPELINE                       │
│                                                       │
│  Data Source          Processing         Output       │
│  ──────────          ──────────         ──────       │
│  MOEX CSV files  →   Local LLM      →   Signals      │
│  RSS/Telegram    →   T5 Summarizer  →   Digest       │
│  Git history     →   Classifier     →   Changelog    │
│  Log files       →   Embedder       →   Anomalies    │
│                                                       │
│  All on local CPU, no API calls, $0 runtime cost     │
└──────────────────────────────────────────────────────┘
```

### Scenario: MOEX Backtesting with Local Models

```python
# Pipeline: fetch → process → analyze → report
# All local, no API dependency

# Step 1: Data fetching (already have cron jobs)
# fetch_moex.sh → /opt/trading-system/data/

# Step 2: Local analysis
# qwen2.5:7b on CPU processes 1000 tickers in ~30 minutes
# Cost: $0 (vs ~$5-10 via API for same volume)

# Step 3: Result storage
# Structured JSON → dashboard / Telegram digest
```

**Model selection for batch workloads:**

| Task | Model | Hardware | Speed | Cost |
|------|-------|----------|-------|------|
| News summarization (RU) | T5-small (Russian) | 2GB RAM | 2-3s/article | $0 |
| Ticker classification | qwen2.5:3b (Q4) | 2GB RAM | 5 tok/s | $0 |
| Pattern analysis | qwen2.5:7b (Q4) | 4GB RAM | 3 tok/s | $0 |
| Full backtesting pipeline | qwen2.5:14b (Q4) | 8GB RAM | 1-4 tok/s | $0 |
| Embedding + search | all-MiniLM-L6-v2 | 250MB RAM | 3ms/query | $0 |

### When Offline Wins vs API

| Criterion | API (OpenRouter) | Local (CPU) |
|-----------|-----------------|-------------|
| Cost per token | $0.003-0.015 | $0 |
| Latency | 500-2000ms | 2000-50000ms |
| Quality | Frontier | 60-80% of frontier |
| Availability | Depends on internet | Always |
| Privacy | Sent to provider | Stays local |
| Volume limits | Rate limits | Only RAM/CPU |
| **Best for** | Interactive chat | Batch processing, backtesting |

### Hybrid Strategy

```
Interactive (user messages):
  → Frontier model via API (quality matters)

Batch processing (cron jobs):
  → Local model (cost matters, time doesn't)

Emergency (API down):
  → Local model for basic tasks
  → Cache + rules for everything else
```

---

## Use Case Matrix

| Scenario | Primary Cost | Best Optimizations | Expected Savings |
|----------|-------------|-------------------|-----------------|
| **Telegram small talk** | Tool schemas + skills | 0a + 1a + 4a | -75% |
| **Telegram file ops** | Tool schemas + history | 0a + 2a + 5b | -60% |
| **Telegram web search** | Browser schemas + results | 1b + 4b + 5b | -55% |
| **Telegram coding help** | Everything needed | 3c + 5a | -25% |
| **CLI development** | Context files + full tools | 3c + 5b | -15% |
| **Cron job (trading)** | Tool schemas + history | 1b (minimal toolset) | -70% |
| **Discord team chat** | Skills + schemas | 0a + 1a + 4a | -70% |
| **Subagent delegation** | Tool schemas passed down | 7a (micro-agents) | -50% |
| **Long session (50+ turns)** | History accumulation | 5a + 5d | -60% of history |
| **Batch processing** | Repeated system prompts | 7b (caching) | -80% cost |
| **Offline backtesting** | Zero (local models) | Layer 7e + offline pipeline | -100% API cost |
| **Emergency (API down)** | Zero (local models) | Layer 7e fallback chain | Resilience |
| **Russian news digest** | Zero (T5 local) | Offline pipeline | -100% API cost |
| **Edit-heavy coding** | Retry loops | Hashline (Harness section) | -20% retries |

---

## Implementation Roadmap

### Phase 1: Free wins (1-2 hours, zero risk)
- [ ] `skip_context_files=True` for all messaging platforms
- [ ] Platform-gate skills: add `platforms: ["cli"]` to mlops/gaming/github/research skills
- [ ] Shorten tool descriptions for messaging mode
- [ ] Trim MEMORY.md and USER.md to <2KB combined

**Expected: -50% tokens, no behavioral changes**

### Phase 2: Toolset optimization (half day, low risk)
- [ ] Define `hermes-telegram-lite` toolset (no browser, no execute_code, no patch)
- [ ] Add `/tools browser on/off` toggle for when browser is needed
- [ ] Tool result truncation (2K token cap per result with head+tail)
- [ ] Short parameter descriptions (remove rarely-used params from schemas)

**Expected: Additional -20% tokens**

### Phase 3: Smart routing (1-2 days, medium risk)
- [ ] Rule-based tool router (regex classifier)
- [ ] Compact skills index format (category summaries instead of per-skill)
- [ ] ONNX embedding model for skill matching (optional, server-side)
- [ ] Context gate: skip AGENTS.md/SOUL.md based on query classification

**Expected: Additional -15% tokens, better relevance**

### Phase 4: Harness improvements (1-2 days, low risk)
- [ ] Hashline-enhanced `read_file`: tag each line with `N:hash|content`
- [ ] Hashline-aware `patch` tool: accept `line_hash` instead of `old_string`
- [ ] TTSR (Time Traveling Streamed Rules): regex-triggered rule injection on output stream
- [ ] TOOLS.md: short paths file for local scripts (~200 chars)
- [ ] Daily logs (YYYY-MM-DD.md): cron writes summary, loads next day
- [ ] IDENTITY.md: extract from AGENTS.md for platform-gated loading

**Expected: -retries (saves ~20% extra API calls on edit tasks), zero context cost for TTSR rules**

### Phase 5: Provider independence (2-3 days, medium risk)
- [ ] Local ONNX embedding model (~250MB, no GPU) for skill/tool routing
- [ ] Local T5/rubert for offline text summarization (Russian market data)
- [ ] Direct Anthropic API fallback (bypass OpenRouter)
- [ ] Multi-provider routing: OpenRouter primary → Anthropic direct → local models
- [ ] Offline batch processing pipeline (backtesting, news aggregation)

**Expected: Resilience to provider outages, zero-cost offline processing for batch jobs**

### Phase 6: Architectural (1 week, higher risk)
- [ ] Micro-agent architecture with router
- [ ] Two-stage model routing (cheap classifier + expensive executor)
- [ ] Automatic session hygiene with summarization
- [ ] Prompt caching optimization pass

**Expected: -40-50% cost (tokens + model tier)**

---

## Anti-Patterns

### ❌ Don't: Remove tools the user might need
The agent without `terminal` can't run commands. The user has to re-enable it mid-session, which is confusing. Instead, use a "lite" toolset with a clear `/tools` toggle.

### ❌ Don't: Over-trim MEMORY.md
Memory is the agent's continuity. Trimming too aggressively causes the agent to "forget" environment details, re-ask about preferences, and make repeated mistakes. Keep it under 2KB but keep it accurate.

### ❌ Don't: Use keyword-only routing without fallback
A regex classifier will misclassify queries. Always include a "core" toolset (terminal, memory, read_file, web_search, clarify, send_message) regardless of routing.

### ❌ Don't: Compress context too aggressively
Setting compression threshold below 40% causes frequent summarization calls, which themselves cost tokens and introduce latency. 50% is the sweet spot.

### ❌ Don't: Cache-bust the system prompt
Modifying the system prompt mid-conversation (changing tools, adding/removing memory, rebuilding skills) invalidates the prefix cache. Do all setup before the first API call. The only permitted mid-conversation change is context compression.

### ❌ Don't: Assume one size fits all
A trading bot needs finance skills, not mlops. A coding assistant needs AGENTS.md, not platform hints. Optimize per-platform, not globally.

---

## Quick Reference: Token Costs

| Content | Approximate tokens |
|---------|-------------------|
| 1 character (English) | ~0.25 tokens |
| 1 character (Russian) | ~0.5-0.7 tokens |
| 1 character (code) | ~0.3 tokens |
| 1 tool schema (avg) | ~300 tokens |
| 1 skill description line | ~30 tokens |
| AGENTS.md (dev guide) | ~3,500 tokens |
| Skills index (113 skills) | ~3,000 tokens |
| Tool schemas (30 tools) | ~8,750 tokens |
| 1 terminal tool result | 200-5,000 tokens |
| 1 web_extract result | 500-3,000 tokens |

---

## License

This document is a reference guide. Use freely in your Hermes Agent deployments.
