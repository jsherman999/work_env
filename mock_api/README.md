# mock_api

This is a small FastAPI mock that serves an API backed by `../fake_users.csv`.

Usage (local dev):

Install deps and run with uvicorn:

```bash
python -m pip install -r mock_api/requirements.txt
uvicorn mock_api.app:app --host 0.0.0.0 --port 8000
```

Endpoints
- GET /health — returns {"status": "ok"}
- GET /inspect — recent request log
- GET /users — returns JSON array of users. Supports these query params:
  - `filter`: simple `key=value` or LDAP-like expression e.g. `(samaccountname=johndoe)` or `(&(memberOf=Admins)(userAccountControl>=512))`
  - `delay_ms`: simulate latency (milliseconds)
  - `error_rate`: probability [0..1] to return HTTP 500 for testing error handling
- GET /users/{username} — return single user by `sAMAccountName`
- POST /users — create user (in-memory)

Docker / compose

Build and run with docker-compose:

```bash
docker compose up --build
```

Test examples

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/users?filter=samaccountname=johndoe"
curl "http://localhost:8000/users?filter='(memberOf=Admins)'"
```

## How the mocked API works

This mock is a lightweight FastAPI app that serves deterministic JSON
responses backed by `../fake_users.csv`. Key design points:

- Data source: the server loads `fake_users.csv` at startup into an
  in-memory list `USERS`. Endpoints read from (and can append to) this
  list.
- Filters: `/users` supports both simple `key=value` filters and a
  small LDAP-style filter language (e.g. `(samaccountname=johndoe)` or
  `(&(memberOf=Admins)(userAccountControl>=512))`). The parser is
  implemented in `mock_api/app.py` (`parse_ldap_filter`).
- Fault injection: you can simulate latency or errors using the
  `delay_ms` and `error_rate` query params on `/users`.
- Logging: simple request logging is available at `/inspect` (last
  50 requests).

## Step-by-step: Adding a new mocked endpoint

Follow these steps to add more endpoints that mimic production APIs.

1. Identify the production behavior to mock
   - HTTP method and path (e.g. `GET /deployments`, `POST /deployments`).
   - Request shape: query params, path params, and request body JSON schema.
   - Response shape(s): successful response JSON schema and possible
     error responses (4xx/5xx) and status codes.
   - Authentication: what headers or tokens are required in prod? For
     the mock you can accept an `Authorization` header and optionally
     validate it against a test secret.
   - Statefulness: does the endpoint create/read/update/delete server
     state? If yes, decide whether in-memory storage is sufficient or
     if you need persistence (SQLite).

2. Add the route handler in `mock_api/app.py`
   - Open `mock_api/app.py` and add a new function decorated with the
     appropriate FastAPI decorator, e.g. `@app.get("/deployments")`
   - Reuse helpers: the file already contains `USERS`, `parse_ldap_filter`,
     `_to_int_safe`, and request logging middleware. Import or reuse
     those where useful.

Example: add `GET /groups` that returns group names found in
`fake_users.csv`.

```py
@app.get("/groups")
def list_groups():
    groups = set()
    for u in USERS:
        for g in u.get('memberOf', []):
            groups.add(g)
    return sorted(list(groups))
```

Example: add `POST /deployments` that accepts a JSON payload and
stores it in-memory.

```py
@app.post('/deployments')
def create_deployment(payload: Dict[str, Any]):
    # validate required fields
    if 'name' not in payload:
        raise HTTPException(400, 'name required')
    DEPLOYMENTS.append(payload)
    return JSONResponse(status_code=201, content=payload)
```

3. Add tests / examples
   - Update `mock_api/test_requests.sh` with a curl call that exercises
     the new endpoint. Example:

```bash
curl -sS -X POST -H 'Content-Type: application/json' \
  -d '{"name":"canary"}' http://127.0.0.1:8000/deployments | jq
```

4. Decide on persistence (optional)
   - In-memory lists are easy and reset on server restart. If you need
     persistence across runs, add a small SQLite DB (`sqlite3` or
     SQLModel) and persist created objects there. Use a minimal
     migration / table-creation step on startup.

5. Run the server and smoke-test
   - Start locally:
     ```bash
     uvicorn mock_api.app:app --host 0.0.0.0 --port 8000
     ```
   - Or with Docker Compose:
     ```bash
     docker compose up --build
     ```
   - Run `mock_api/test_requests.sh` or curl directly.

6. (Optional) Add OpenAPI examples
   - FastAPI auto-generates OpenAPI docs at `/docs` and `/openapi.json`.
   - You can add Pydantic request/response models to the handler
     signatures to make the schema and docs more useful for consumers.

7. (Optional) Add authentication emulation
   - Implement `/auth/token` that returns test JWTs signed with a
     local HMAC secret. Configure clients to accept that token in dev.

## What production information is useful to copy here
- Example requests and responses (JSON payloads) — these let you
  implement realistic shapes quickly.
- Status codes for error conditions.
- Any query semantics or filtering behavior (e.g. LDAP filters,
  pagination). If the production API supports complex filters,
  replicate only what your clients need.
- Authentication expectations: header names, token formats (JWT), and
  any scopes required.

## Best practices as you add endpoints
- Keep handlers small and deterministic; make it easy to inject
  latency and errors for resilience testing.
- Document each mocked endpoint in `mock_api/README.md` (or a new
  markdown file) so teammates can reuse them.
- Add simple smoke tests to `mock_api/test_requests.sh` so CI can
  validate the mock after changes.
- If multiple mocks share logic, factor it into helper functions in
  `mock_api/app.py` or a new `mock_api/utils.py`.

If you want, I can add a small example endpoint now (for example
`/groups` or `/deployments`) and add a test curl line to
`mock_api/test_requests.sh`. Which endpoint should I add first?

## File-backed mocks

You can register file-backed mocks that are served at `/mocks/{label}`. Mappings live in `mocks.json` and files live under `mock_data/`.

There's a helper CLI to register a mapping which will copy the file into `mock_data/` and add a mapping in `mocks.json`:

Example:

  python add_mock.py --label users-list --src ../fake_users.json --type json

This will copy the file into `mock_data/users-list__fake_users.json` and add a mapping like:

  {
    "users-list": {
      "path": "mock_data/users-list__fake_users.json",
      "type": "json",
      "status": 200,
      "headers": {}
    }
  }

After registration the mock will be available at:

  GET /mocks/users-list

The endpoint will return the content of the file with the HTTP status in the mapping. Supported types: `json`, `csv`, `raw`.

If you need to replace an existing mapping use `--overwrite`.

## Admin HTTP API

If you prefer to register mocks at runtime over HTTP (no CLI), the mock server exposes a small admin API under `/admin/mocks`:

- `GET /admin/mocks` — list current mappings (returns JSON object)
- `POST /admin/mocks` — register a mapping via multipart form upload. Form fields:
  - `label` (string) — label to register (required)
  - `file` (file upload) — file to be copied into `mock_data/` (required)
  - `type` (json|csv|raw) — response type (default: json)
  - `status` (int) — HTTP status to return (default: 200)
  - `headers` (JSON string) — optional response headers
  - `content_type` (string) — optional content-type for `raw` responses

  Example curl (register a JSON file):

  ```bash
  curl -sS -X POST \
    -F 'label=users-list' \
    -F 'file=@../fake_users.json' \
    -F 'type=json' \
    http://127.0.0.1:8000/admin/mocks | jq
  ```

- `DELETE /admin/mocks/{label}` — remove a mapping and its file (if stored under `mock_data/`).

These endpoints are intentionally minimal and unauthenticated for dev/testing; add auth in front of the mock in CI or local env if needed.


