"""mock_api.app

Lightweight FastAPI application used to serve fake production-like
endpoints for local testing. The app loads/seeds a small SQLite-backed
dataset (users), provides search endpoints with LDAP-style filters,
and serves file-backed mocks registered via mappings in `mocks.json`.

This file intentionally keeps behavior simple and deterministic so
tests and local tooling can rely on stable responses.
"""

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
import os, time, random, json, base64
from typing import List, Dict, Any
from . import db

app = FastAPI(title="Fake Prod API (mock)")

# Ensure the persistent DB is initialized on import. `db.init_db()` will
# create `mock_api/data.db` and seed it with `../fake_users.csv` when the
# database is empty. This keeps the server deterministic across restarts.
db.init_db()

# In-memory recent request log used by `/inspect` for simple debugging
REQUEST_LOG: List[Dict[str, Any]] = []

# File-backed mapping state and storage directory. Mappings are stored in
# `mock_api/mocks.json` and files are kept under `mock_api/mock_data/`.
MOCKS_JSON = os.path.join(os.path.dirname(__file__), 'mocks.json')
MOCK_DATA_DIR = os.path.join(os.path.dirname(__file__), 'mock_data')


def load_mappings():
    """Load persistent mock mappings from `mocks.json`.

    Returns a dict mapping label -> metadata. If the file is missing or
    malformed this returns an empty dict to keep the server operational.
    """
    try:
        with open(MOCKS_JSON) as f:
            return json.load(f)
    except Exception:
        return {}


def save_mappings(mappings: dict):
    """Persist the provided mappings dictionary to `mocks.json`.

    Returns True on success, False on any write error. We keep this
    tolerant because mapping persistence is convenient but should not
    crash the whole server if the filesystem is temporarily readonly.
    """
    try:
        with open(MOCKS_JSON, 'w') as f:
            json.dump(mappings, f, indent=2)
        return True
    except Exception:
        return False


def resolve_mock(label: str):
    """Resolve a mapping label to its metadata and absolute file path.

    This validates that the mapped path lives under `mock_data/` to
    avoid directory traversal or accidental file exposures. If the
    mapping does not exist or the path is invalid, returns None.
    """
    mappings = load_mappings()
    meta = mappings.get(label)
    if not meta:
        return None

    # Ensure path is inside mock_data dir
    path = meta.get('path')
    if not path:
        return None
    abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), path))
    if not abs_path.startswith(os.path.abspath(MOCK_DATA_DIR)):
        return None

    # attach computed absolute path for callers
    meta['abs_path'] = abs_path
    return meta


def _to_int_safe(val):
    try:
        return int(val)
    except Exception:
        return None


def parse_ldap_filter(s):
    """Parse a very small subset of LDAP filter syntax and return a
    predicate function that accepts a record (dict) and returns True/False.

    Supported features (enough for our tests):
      - Simple equality: (attr=value)
      - Presence: (attr=*)
      - Substring (prefix/suffix via '*')
      - Numeric comparisons: >=, >, <=, <
      - AND/OR groups: (&(...)(...)) and (|(...)(...))
      - NOT: (!(...))

    The parser is intentionally simple and defensive. It resolves
    attributes case-insensitively and supports multi-valued attributes
    (lists) when checking equality.
    """
    s = (s or '').strip()
    if not s:
        # empty filter means match everything
        return lambda r: True
    pos = 0

    def skip_ws():
        nonlocal pos
        while pos < len(s) and s[pos].isspace():
            pos += 1

    def get_val(rec, attrname):
        # case-insensitive attribute lookup
        for h in rec.keys():
            if h.lower() == attrname.lower():
                return rec.get(h)
        return None

    def parse():
        nonlocal pos
        skip_ws()
        if pos >= len(s) or s[pos] != '(':
            raise ValueError('expected (')
        pos += 1
        skip_ws()

        # Handle boolean group operators (AND/OR)
        if pos < len(s) and s[pos] in ('&', '|'):
            op = s[pos]; pos += 1
            parts = []
            while True:
                skip_ws()
                if pos < len(s) and s[pos] == '(':
                    parts.append(parse())
                else:
                    break
            skip_ws()
            if pos >= len(s) or s[pos] != ')':
                raise ValueError('expected )')
            pos += 1
            if op == '&':
                return lambda r: all(p(r) for p in parts)
            else:
                return lambda r: any(p(r) for p in parts)

        # NOT operator
        if pos < len(s) and s[pos] == '!':
            pos += 1
            p = parse()
            skip_ws()
            if pos >= len(s) or s[pos] != ')':
                raise ValueError('expected ) after !')
            pos += 1
            return lambda r: not p(r)

        # attr op value (basic comparison)
        j = pos
        while j < len(s) and s[j] not in ('=', '>', '<', ')'):
            j += 1
        attr = s[pos:j].strip()
        if j >= len(s):
            raise ValueError('unexpected end')
        if s[j] == '=':
            op = '='; j += 1
        elif s[j] == '>':
            if j+1 < len(s) and s[j+1] == '=': op = '>='; j += 2
            else: op = '>'; j += 1
        elif s[j] == '<':
            if j+1 < len(s) and s[j+1] == '=': op = '<='; j += 2
            else: op = '<'; j += 1
        else:
            raise ValueError('unknown op')
        k = j
        while k < len(s) and s[k] != ')': k += 1
        val = s[j:k].strip()
        pos = k + 1

        # Presence check
        if op == '=' and val == '*':
            return lambda rec, a=attr: bool(get_val(rec, a))

        # Simple substring matching (supports a single '*')
        if op == '=' and '*' in val:
            pat = val.replace('*', '').lower()
            return lambda rec, a=attr, p=pat: p in (str(get_val(rec, a)) or '').lower()

        # Numeric comparisons
        if op in ('>=', '>', '<=', '<'):
            try: cv = int(val)
            except: cv = None
            def cmp_pred(rec, a=attr, op=op, cv=cv):
                v = get_val(rec, a)
                vi = _to_int_safe(v)
                if vi is None or cv is None: return False
                if op == '>=': return vi >= cv
                if op == '>': return vi > cv
                if op == '<=': return vi <= cv
                if op == '<': return vi < cv
                return False
            return cmp_pred

        # Equality for single or multi-valued attributes
        def eq_pred(rec, a=attr, v=val):
            vv = get_val(rec, a)
            if vv is None: return False
            if isinstance(vv, (list, tuple)):
                return any(str(x).lower() == str(v).lower() for x in vv)
            return str(vv).lower() == str(v).lower()
        return eq_pred

    skip_ws()
    p = parse()
    return p


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Simple middleware that records basic request/response timing and
    # status into an in-memory list. This is helpful for debugging and
    # the `/inspect` endpoint; it's not intended as a production-grade
    # access log.
    start = time.time()
    resp = await call_next(request)
    elapsed = time.time() - start
    try:
        REQUEST_LOG.append({'method': request.method, 'path': request.url.path, 'status': resp.status_code, 'time_ms': int(elapsed*1000)})
    except Exception:
        pass
    return resp


@app.get("/health")
def health():
    # Lightweight healthcheck for orchestration and smoke tests
    return {"status": "ok"}


@app.get("/inspect")
def inspect_logs():
    # Return the most recent requests captured by the middleware for
    # quick debugging and inspection.
    return {"recent_requests": REQUEST_LOG[-50:]}


@app.get("/users")
def list_users(filter: str = Query(None), delay_ms: int = Query(0), error_rate: float = Query(0.0)):
    """List users with optional filtering, latency and fault injection.

    Query params:
      - filter: either a key=value pair or an LDAP-style expression
      - delay_ms: add artificial response delay (milliseconds)
      - error_rate: probability in [0..1] to return HTTP 500 (simulate errors)
    """
    # Optional latency injection for testing
    if delay_ms:
        time.sleep(delay_ms / 1000.0)
    # Optional transient error injection
    if random.random() < float(error_rate):
        raise HTTPException(status_code=500, detail="injected error")

    results = []
    if filter:
        filter = filter.strip()
        # LDAP-style expression (e.g. (memberOf=Admins) or complex AND/OR)
        if filter.startswith('('):
            try:
                pred = parse_ldap_filter(filter)
                for u in db.get_all_users():
                    if pred(u):
                        results.append(u)
            except Exception:
                raise HTTPException(status_code=400, detail="bad filter")
        # simple key=value searches (delegated to DB helper for efficiency)
        elif '=' in filter:
            k, v = filter.split('=', 1)
            k = k.strip(); v = v.strip()
            results = db.find_users_by_kv(k, v)
        else:
            results = db.get_all_users()
    else:
        results = db.get_all_users()
    return results


@app.get('/mocks/{label}')
def serve_mock(label: str, delay_ms: int = Query(0)):
    """Serve a file-backed mock registered under `label`.

    The mapping metadata describes the stored file path (relative to
    `mock_api/`), the response `type` and optional `status` and
    `headers`. For JSON mappings we parse the file and return a
    JSONResponse; for CSV and raw files we stream the file with an
    appropriate media type.
    """
    meta = resolve_mock(label)
    if not meta:
        raise HTTPException(status_code=404, detail='mock not found')

    # Optional per-request delay useful for simulating slow services
    if delay_ms:
        time.sleep(delay_ms/1000.0)

    mtype = meta.get('type', 'json')
    status = int(meta.get('status', 200))
    headers = meta.get('headers') or {}
    path = meta.get('abs_path')

    if mtype == 'json':
        try:
            with open(path) as f:
                data = json.load(f)
            return JSONResponse(status_code=status, content=data, headers=headers)
        except Exception:
            raise HTTPException(status_code=500, detail='failed to load mock json')
    elif mtype == 'csv':
        # Serve CSV as text/csv for convenience
        return FileResponse(path, status_code=status, media_type='text/csv', headers=headers)
    else:
        # treat as raw/text/binary and allow an optional content_type
        ctype = meta.get('content_type') or 'application/octet-stream'
        return FileResponse(path, status_code=status, media_type=ctype, headers=headers)


@app.get('/admin/mocks')
def admin_list_mocks():
    """Admin endpoint: list current mappings stored in `mocks.json`.

    This endpoint is intentionally unauthenticated for local testing and
    convenience. In shared environments you should add auth/ACLs.
    """
    return load_mappings()


@app.post('/admin/mocks')
def admin_register_mock(payload: Dict[str, Any]):
    """Register a new mock via JSON body.

    Expected JSON fields (one of `content` or `content_b64` must be
    provided):
      - label (str) required
      - filename (str) optional, name to store under mock_data
      - content (string) OR content_b64 (base64 string) required
      - type (json|csv|raw) default json
      - status (int) default 200
      - headers (object) optional
      - content_type (string) optional for raw

    The endpoint writes the uploaded content to `mock_data/` and
    persists the mapping in `mocks.json`. Returns 201 with the
    registered metadata on success.
    """

    label = payload.get('label')
    if not label:
        raise HTTPException(status_code=400, detail='label required')

    mappings = load_mappings()
    if label in mappings:
        raise HTTPException(status_code=409, detail='label exists; delete first or use another label')

    # Determine incoming content and filename
    fname = payload.get('filename') or f"{label}.bin"
    c = payload.get('content')
    cb64 = payload.get('content_b64')
    if c is None and cb64 is None:
        raise HTTPException(status_code=400, detail='content or content_b64 required')
    if cb64 is not None:
        try:
            content = base64.b64decode(cb64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'invalid base64: {e}')
    else:
        # treat content as UTF-8 text
        content = str(c).encode('utf-8')

    # metadata fields
    mtype = payload.get('type', 'json')
    status = int(payload.get('status', 200))
    headers = payload.get('headers') or {}
    content_type = payload.get('content_type')

    if mtype == 'json':
        try:
            json.loads(content.decode('utf-8'))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'invalid json: {e}')

    # persist the file under mock_data and record mapping
    os.makedirs(MOCK_DATA_DIR, exist_ok=True)
    dest_name = f"{label}__{os.path.basename(fname)}"
    dest_path = os.path.join(MOCK_DATA_DIR, dest_name)
    try:
        with open(dest_path, 'wb') as fh:
            fh.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'failed to write file: {e}')

    mappings[label] = {
        'path': os.path.join('mock_data', dest_name),
        'type': mtype,
        'status': status,
        'headers': headers,
    }
    if content_type:
        mappings[label]['content_type'] = content_type

    if not save_mappings(mappings):
        raise HTTPException(status_code=500, detail='failed to save mapping')

    return JSONResponse(status_code=201, content={label: mappings[label]})


@app.delete('/admin/mocks/{label}')
def admin_delete_mock(label: str):
    mappings = load_mappings()
    if label not in mappings:
        raise HTTPException(status_code=404, detail='not found')
    meta = mappings.pop(label)
    save_mappings(mappings)
    # try to remove file if it exists in mock_data
    try:
        p = os.path.abspath(os.path.join(os.path.dirname(__file__), meta.get('path', '')))
        if p.startswith(os.path.abspath(MOCK_DATA_DIR)) and os.path.exists(p):
            os.remove(p)
    except Exception:
        pass
    return JSONResponse(status_code=204, content={})


@app.get("/users/{username}")
def get_user(username: str):
    rec = db.get_user_by_sAMAccountName(username)
    if rec:
        return rec
    raise HTTPException(status_code=404, detail='not found')


@app.post("/users")
def create_user(payload: Dict[str, Any]):
    # Very small create: require sAMAccountName and dn
    if 'sAMAccountName' not in payload or 'dn' not in payload:
        raise HTTPException(status_code=400, detail='sAMAccountName and dn required')
    rec = db.create_user(payload)
    return JSONResponse(status_code=201, content=rec)
