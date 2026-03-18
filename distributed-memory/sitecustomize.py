"""
Distributed Memory Hooks for Hermes Agent
"""
import os
import sys

# Load .env
for p in ["/home/<USER>/hermes/.env", "/root/<USER>/.env"]:
    if os.path.exists(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    os.environ.setdefault(k.strip(), v.strip())
        break

_NODE_ID = os.getenv("NODE_ID", "unknown")
_SESSION_ID = "{}_{}".format(_NODE_ID, os.urandom(4).hex())
_SB_URL = "https://<SUPABASE_URL>"
_SB_KEY = "<SUPABASE_KEY>"

def _sb_headers():
    return {'apikey': _SB_KEY, 'Authorization': 'Bearer ' + _SB_KEY, 
            'Content-Type': 'application/json', 'Prefer': 'return=minimal'}

def get_memory_context():
    try:
        import requests
        from datetime import datetime, timezone
        r = requests.get(
            _SB_URL + '/rest/v1/agent_state?select=node_id,status,current_task,summary,updated_at&node_id=neq.' + _NODE_ID + '&order=updated_at.desc',
            headers=_sb_headers(), timeout=5
        )
        if r.status_code != 200: return ""
        nodes = r.json()
        if not nodes: return ""
        lines = ["\n🌐 DISTRIBUTED STATE (other nodes):"]
        for n in nodes:
            try:
                then = datetime.fromisoformat(n.get('updated_at','').replace('Z','+00:00'))
                delta = datetime.now(timezone.utc) - then
                age = "{}d".format(delta.days) if delta.days else "{}h".format(delta.seconds//3600) if delta.seconds>=3600 else "{}m".format(delta.seconds//60)
            except: age = "?"
            lines.append("  * {}: {} | {} | {} | {} ago".format(
                n.get('node_id','?'), n.get('status','?'),
                n.get('current_task','-'), (n.get('summary','') or '')[:50], age))
        return "\n".join(lines)
    except: return ""

def save_message(role, content):
    try:
        import requests
        from datetime import datetime, timezone
        r = requests.post(_SB_URL + '/rest/v1/session_history', headers=_sb_headers(), json={
            'node_id': _NODE_ID, 'session_id': _SESSION_ID,
            'role': role, 'content': str(content)[:4000],
            'created_at': datetime.now(timezone.utc).isoformat()
        }, timeout=10)
        if r.status_code not in (200, 201, 204):
            print("[Memory Hooks] save_message failed: {} {}".format(r.status_code, r.text[:100]))
    except Exception as e:
        print("[Memory Hooks] save_message error: {}".format(e))

def update_state(status='active', task=None, summary=None):
    try:
        import requests
        from datetime import datetime, timezone
        r = requests.patch(
            _SB_URL + '/rest/v1/agent_state?node_id=eq.' + _NODE_ID,
            headers=_sb_headers(),
            json={'node_id': _NODE_ID, 'status': status, 'current_task': task or 'idle',
                  'summary': (summary or '')[:500], 'updated_at': datetime.now(timezone.utc).isoformat()},
            timeout=10
        )
        if r.status_code not in (200, 201, 204):
            print("[Memory Hooks] update_state failed: {} {}".format(r.status_code, r.text[:100]))
    except Exception as e:
        print("[Memory Hooks] update_state error: {}".format(e))

print("[Memory Hooks] ✅ Loading (node: {})".format(_NODE_ID))

# Patch AIAgent via run_agent module
_patched = False
_orig_init = None
_orig_run = None

def _do_patch():
    global _patched, _orig_init, _orig_run
    if _patched:
        return
    
    try:
        import run_agent
        
        _orig_init = run_agent.AIAgent.__init__
        _orig_run = run_agent.AIAgent.run_conversation
        
        def new_init(self, *args, **kwargs):
            print("[Memory Hooks] new_init called")
            existing = kwargs.get('ephemeral_system_prompt') or ''
            kwargs['ephemeral_system_prompt'] = existing + get_memory_context()
            _orig_init(self, *args, **kwargs)
            update_state('active', 'ready', 'Agent started')
        
        def new_run(self, *args, **kwargs):
            print("[Memory Hooks] new_run called, args count: {}".format(len(args)))
            if args:
                msg = args[0]
                if isinstance(msg, str):
                    print("[Memory Hooks] saving user message: {}".format(msg[:50]))
                    save_message('user', msg)
                elif isinstance(msg, dict):
                    content = str(msg.get('content', msg))
                    print("[Memory Hooks] saving user dict content: {}".format(content[:50]))
                    save_message('user', content)
            
            result = _orig_run(self, *args, **kwargs)
            
            if result:
                print("[Memory Hooks] saving assistant result: {}".format(str(result)[:50]))
                save_message('assistant', str(result)[:4000])
                update_state('active', 'ready', str(result)[:80])
            return result
        
        run_agent.AIAgent.__init__ = new_init
        run_agent.AIAgent.run_conversation = new_run
        _patched = True
        print("[Memory Hooks] ✅ Agent patched! (node: {})".format(_NODE_ID))
    except Exception as e:
        print("[Memory Hooks] ⚠️ Patch failed: {}".format(str(e)[:60]))

# Try to patch now
try:
    _do_patch()
except: pass

# Hook import for later patching
try:
    import builtins
    _orig_import = builtins.__import__
    _importing = False
    
    def hooked_import(name, *args, **kwargs):
        global _importing
        if _importing:
            return _orig_import(name, *args, **kwargs)
        result = _orig_import(name, *args, **kwargs)
        if name == 'run_agent' and not _patched:
            _importing = True
            try:
                _do_patch()
            finally:
                _importing = False
        return result
    
    builtins.__import__ = hooked_import
    print("[Memory Hooks] ✅ Import hook installed")
except Exception as e:
    print("[Memory Hooks] ⚠️ Hook error: {}".format(str(e)[:50]))
