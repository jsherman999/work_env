# Using This Mock Environment Across Multiple Projects

This guide explains how to use this mock environment as a reusable testing foundation for developing production applications with fake data.

## Overview

This repository provides a complete mock Active Directory/LDAP testing environment with:
- Mock API server (FastAPI) with AD-like user data
- Fake `vastool` command-line tool
- File-backed mock endpoint system
- LDAP filter support
- Fault injection capabilities

## Architecture

### Recommended Setup

```
├── work_env/                    ← This repo (mock environment)
│   ├── mock_api/
│   ├── fake_users.csv
│   ├── vastool
│   └── docker-compose.yml
│
├── my-app-1/                    ← Your production app #1
│   ├── src/
│   ├── docker-compose.yml       ← References mock service
│   └── .env
│
├── my-app-2/                    ← Your production app #2
│   ├── src/
│   ├── docker-compose.yml
│   └── .env
```

---

## Creating Mock Endpoints

### Quick Start: File-Backed Mocks (Recommended)

For static responses that mimic production data:

#### Step 1: Capture Production Response
```bash
# Get data from your production endpoint and save it
curl https://prod-api.example.com/some/endpoint > response.json
```

#### Step 2: Register the Mock
```bash
# Using the CLI tool
python mock_api/add_mock.py add \
  --label my-endpoint \
  --src response.json \
  --type json
```

#### Step 3: Use Your Mock Endpoint
```bash
# Your mock is now available at:
curl http://localhost:8000/mocks/my-endpoint
```

### Advanced: Dynamic Endpoints

For endpoints that need logic, filtering, or query parameters:

#### Step 1: Save Production Data
Save the production response to `mock_api/mock_data/my_data.json`

#### Step 2: Add Endpoint to `mock_api/app.py`
```python
# Add this to mock_api/app.py

@app.get("/my-endpoint")
async def my_endpoint():
    """Mock endpoint that mimics prod"""
    import json
    with open("mock_data/my_data.json") as f:
        data = json.load(f)
    return data
```

#### Step 3: Restart Server
```bash
# The server will auto-reload if running with --reload
uvicorn mock_api.app:app --reload
```

---

## Integration Strategies

### Option 1: Docker Compose with Shared Network (Recommended)

Best for running multiple projects that all use the same mock environment.

#### In This Repo (`work_env`):

```yaml
# docker-compose.yml
version: '3.8'
services:
  mock-api:
    build: ./mock_api
    ports:
      - "8000:8000"
    volumes:
      - ./fake_users.csv:/app/fake_users.csv
    networks:
      - mock-network

networks:
  mock-network:
    name: mock-network
    driver: bridge
```

#### In Your App Repo (`my-app-1`):

```yaml
# docker-compose.yml
version: '3.8'
services:
  my-app:
    build: .
    environment:
      # Point to mock API instead of production
      API_BASE_URL: http://mock-api:8000
      VASTOOL_PATH: /usr/local/bin/vastool
    networks:
      - mock-network

networks:
  mock-network:
    external: true  # Use the mock network created by work_env
```

#### Usage:

```bash
# Terminal 1: Start mock environment (once)
cd work_env
docker compose up

# Terminal 2: Start your app (connects to running mock)
cd my-app-1
docker compose up

# For additional apps:
cd my-app-2
docker compose up
```

**Advantages:**
- ✅ Clean separation between mock environment and applications
- ✅ One mock instance serves all projects
- ✅ Easy to tear down and restart fresh
- ✅ Efficient resource usage

---

### Option 2: Git Submodule

Best for teams or when you need version control of the mock environment with your app.

```bash
# In your app repo
git submodule add https://github.com/you/work_env.git mock-env

# Your app structure:
my-app-1/
├── mock-env/          ← Submodule (this repo)
├── src/
└── docker-compose.yml
```

```yaml
# my-app-1/docker-compose.yml
version: '3.8'
services:
  mock-api:
    build: ./mock-env/mock_api
    ports:
      - "8000:8000"

  my-app:
    build: .
    environment:
      API_BASE_URL: http://mock-api:8000
    depends_on:
      - mock-api
```

**Advantages:**
- ✅ Mock environment versioned with your app
- ✅ Portable - entire setup in one repo
- ✅ Good for team collaboration

**Disadvantages:**
- ⚠️ Each app has its own copy of the mock environment
- ⚠️ More disk space usage

---

### Option 3: Standalone Background Service

Best for solo development with a single active project at a time.

```bash
# Start mock once, leave it running
cd work_env
docker compose up -d  # -d = detached mode

# Mock API now available at localhost:8000 for ALL projects

# In any app:
export API_BASE_URL=http://localhost:8000
npm run dev
```

**Advantages:**
- ✅ Simple and lightweight
- ✅ No Docker networking complexity

**Disadvantages:**
- ⚠️ Manual service management
- ⚠️ Need to remember if it's running

---

## Recommended Workflow

### 1. Initial Setup (One Time)

```bash
# Clone or set up this repo as a template
cd ~/projects
git clone https://github.com/you/work_env.git mock-env
cd mock-env

# Build and test
docker compose up --build
```

### 2. For Each New Project

**Option A: Use as External Service**
```bash
# Start the mock environment
cd ~/projects/mock-env
docker compose up -d

# Develop your app
cd ~/projects/my-new-app
export API_BASE_URL=http://localhost:8000
npm run dev
```

**Option B: Add as Submodule**
```bash
cd my-new-app
git submodule add https://github.com/you/work_env.git mock-env
# Configure docker-compose.yml to use ./mock-env
```

### 3. Environment Configuration

Each app should have environment files for different contexts:

**`.env.development` (use mocks):**
```bash
API_BASE_URL=http://localhost:8000
AD_LDAP_URL=http://localhost:8000/users
VASTOOL_PATH=/path/to/mock/vastool
AUTH_ENABLED=false
```

**`.env.production` (use real services):**
```bash
API_BASE_URL=https://api.prod.example.com
AD_LDAP_URL=ldaps://ad.corp.example.com
VASTOOL_PATH=/opt/quest/bin/vastool
AUTH_ENABLED=true
```

---

## Comparison Table

| Approach | Pros | Cons | Best For |
|----------|------|------|----------|
| **Shared Docker Network** | Clean separation, one mock instance, efficient | Requires Docker setup | Multiple concurrent projects |
| **Git Submodule** | Versioned, portable, team-friendly | Each app has own copy | Team collaboration, versioning |
| **Background Service** | Simple, lightweight, easy | Manual management, easy to forget | Solo development, single project |

---

## Helper Scripts

### Start Mock Environment

Create `scripts/start-mock.sh`:

```bash
#!/bin/bash
# Start mock environment for development
cd "$(dirname "$0")/.."
echo "Starting mock environment..."
docker compose down  # Clean slate
docker compose up --build
```

Make it executable:
```bash
chmod +x scripts/start-mock.sh
```

### Stop Mock Environment

Create `scripts/stop-mock.sh`:

```bash
#!/bin/bash
# Stop mock environment
cd "$(dirname "$0")/.."
echo "Stopping mock environment..."
docker compose down
```

Make it executable:
```bash
chmod +x scripts/stop-mock.sh
```

### Fresh Start (Clean Slate)

Create `scripts/fresh-start.sh`:

```bash
#!/bin/bash
# Complete fresh start - removes all containers, volumes, and data
cd "$(dirname "$0")/.."
echo "Performing fresh start..."
docker compose down -v  # Remove volumes
rm -f mock_api/data.db  # Remove SQLite database
rm -f mock_api/mocks.json  # Remove mock registry
docker compose up --build
```

Make it executable:
```bash
chmod +x scripts/fresh-start.sh
```

---

## Usage Examples

### Example 1: Develop Two Apps Simultaneously

```bash
# Terminal 1: Start shared mock environment
cd ~/projects/work_env
docker compose up

# Terminal 2: App 1
cd ~/projects/web-app
export API_BASE_URL=http://localhost:8000
npm run dev

# Terminal 3: App 2
cd ~/projects/cli-tool
export API_BASE_URL=http://localhost:8000
python app.py
```

### Example 2: Fresh Environment for Testing

```bash
# Get clean slate
cd work_env
./scripts/fresh-start.sh

# Add your test mocks
python mock_api/add_mock.py add --label test-data --src test.json --type json

# Run tests
cd ~/projects/my-app
npm test
```

### Example 3: Add Mock for New Service

```bash
# Capture production response
curl https://prod.example.com/api/v1/teams > teams.json

# Register mock
python mock_api/add_mock.py add --label teams --src teams.json --type json

# Mock available at http://localhost:8000/mocks/teams
```

---

## Tips and Best Practices

1. **Keep This Repo Updated**: Regularly add new mocks as you discover new services
2. **Version Your Mocks**: Tag releases when you add significant new endpoints
3. **Document Custom Endpoints**: Add comments in `app.py` for any dynamic endpoints
4. **Use Environment Variables**: Never hardcode URLs - always use env vars
5. **Test Locally First**: Validate mocks work before integrating with apps
6. **Clean Restarts**: Use `docker compose down && docker compose up` for fresh state
7. **Share Mock Data**: Commit mock response files to help teammates

---

## Troubleshooting

### Mock API Not Accessible

```bash
# Check if container is running
docker ps | grep mock-api

# Check logs
docker compose logs mock-api

# Verify port binding
netstat -an | grep 8000
```

### Network Issues Between Containers

```bash
# List networks
docker network ls

# Inspect mock network
docker network inspect mock-network

# Recreate network
docker compose down
docker compose up
```

### Mock Returns Stale Data

```bash
# Restart with fresh database
docker compose down
rm mock_api/data.db
docker compose up
```

### App Can't Connect to Mock

```bash
# Verify environment variable
echo $API_BASE_URL

# Test connectivity
curl http://localhost:8000/health

# Check Docker network (if using shared network)
docker network inspect mock-network
```

---

## Next Steps

1. **Set up your first app** - Try one of the integration strategies above
2. **Add production mocks** - Capture real API responses and register them
3. **Customize endpoints** - Add dynamic logic in `app.py` for complex scenarios
4. **Share with team** - Push this repo and document your custom mocks

---

## Support

- See `README.md` for mock API documentation
- See `vastool-cheatsheet.md` for vastool command reference
- Check `TODO.md` for planned features
- Review `mock_api/test_requests.sh` for example API calls
