from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
import os, time, random, json, base64
from typing import List, Dict, Any
from . import db

app = FastAPI(title="Fake Prod API (mock)")

# Initialize SQLite DB and seed from CSV if needed
db.init_db()
REQUEST_LOG = []
MOCKS_JSON = os.path.join(os.path.dirname(__file__), 'mocks.json')
MOCK_DATA_DIR = os.path.join(os.path.dirname(__file__), 'mock_data')


def load_mappings():
    try:
        with open(MOCKS_JSON) as f:
            return json.load(f)
    except Exception:
        return {}


def save_mappings(mappings: dict):
    try:
        with open(MOCKS_JSON, 'w') as f:
            json.dump(mappings, f, indent=2)
        return True
    except Exception:
        return False


def resolve_mock(label: str):
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
    meta['abs_path'] = abs_path
    return meta


def _to_int_safe(val):
    try:
        return int(val)
    except Exception:
        return None


def parse_ldap_filter(s):
    # Lightweight parser copied/adapted from the vastool script
    s = (s or '').strip()
    if not s:
        return lambda r: True
    pos = 0

    def skip_ws():
        nonlocal pos
        while pos < len(s) and s[pos].isspace():
            pos += 1

    def get_val(rec, attrname):
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
        if pos < len(s) and s[pos] == '!':
            pos += 1
            p = parse()
            skip_ws()
            if pos >= len(s) or s[pos] != ')':
                raise ValueError('expected ) after !')
            pos += 1
            return lambda r: not p(r)

        # attr op value
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

        if op == '=' and val == '*':
            return lambda rec, a=attr: bool(get_val(rec, a))
        if op == '=' and '*' in val:
            pat = val.replace('*', '').lower()
            return lambda rec, a=attr, p=pat: p in (str(get_val(rec, a)) or '').lower()
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
    return {"status": "ok"}


@app.get("/inspect")
def inspect_logs():
    return {"recent_requests": REQUEST_LOG[-50:]}


@app.get("/users")
def list_users(filter: str = Query(None), delay_ms: int = Query(0), error_rate: float = Query(0.0)):
    if delay_ms:
        time.sleep(delay_ms / 1000.0)
    if random.random() < float(error_rate):
        raise HTTPException(status_code=500, detail="injected error")
    results = []
    if filter:
        filter = filter.strip()
        if filter.startswith('('):
            try:
                pred = parse_ldap_filter(filter)
                for u in db.get_all_users():
                    if pred(u):
                        results.append(u)
            except Exception:
                raise HTTPException(status_code=400, detail="bad filter")
        elif '=' in filter:
            k, v = filter.split('=', 1)
            k = k.strip(); v = v.strip()
            # use DB helper for key=value searches
            results = db.find_users_by_kv(k, v)
        else:
            results = db.get_all_users()
    else:
        results = db.get_all_users()
    return results


@app.get('/mocks/{label}')
def serve_mock(label: str, delay_ms: int = Query(0)):
    meta = resolve_mock(label)
    if not meta:
        raise HTTPException(status_code=404, detail='mock not found')
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
        return FileResponse(path, status_code=status, media_type='text/csv', headers=headers)
    else:
        # treat as raw/text/binary
        ctype = meta.get('content_type') or 'application/octet-stream'
        return FileResponse(path, status_code=status, media_type=ctype, headers=headers)


@app.get('/admin/mocks')
def admin_list_mocks():
    """List registered mock mappings."""
    return load_mappings()


@app.post('/admin/mocks')
def admin_register_mock(payload: Dict[str, Any]):
    """Register a new mock via JSON body.

    Expected JSON fields:
      - label (str) required
      - filename (str) optional, name to store under mock_data
      - content (string) OR content_b64 (base64 string) required
      - type (json|csv|raw) default json
      - status (int) default 200
      - headers (object) optional
      - content_type (string) optional for raw
    """
    label = payload.get('label')
    if not label:
        raise HTTPException(status_code=400, detail='label required')
    mappings = load_mappings()
    if label in mappings:
        raise HTTPException(status_code=409, detail='label exists; delete first or use another label')

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

    mtype = payload.get('type', 'json')
    status = int(payload.get('status', 200))
    headers = payload.get('headers') or {}
    content_type = payload.get('content_type')

    if mtype == 'json':
        try:
            json.loads(content.decode('utf-8'))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'invalid json: {e}')

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
