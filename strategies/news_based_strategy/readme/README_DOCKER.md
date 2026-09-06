# 🐳 Docker Infrastructure & Operations Guide

This guide covers containerization, secret management, port binding, and logging for the **NSE Catalyst Trading Terminal** (`news_based_strategy`).

---

## 🔒 Security & Secrets Isolation

Secrets in `.env` (Gemini API keys, Dhan credentials, database passwords) are **strictly isolated** from the Docker image:
1. **`.dockerignore`**: Excludes `.env`, `.pem`, and `data/` from the build context. The image contains only Python source code and runtime dependencies.
2. **Runtime Secret Injection**: Secrets are read from the host's `.env` and injected into container memory (RAM) when the container boots.
3. **Volume Persistence**: The host `./data` directory is mounted to `/app/data` inside the container to preserve SQLite records, session states, and trade audit logs across restarts.

---

## 🚀 Docker Management Script (`infra/scripts/docker.sh`)

All Docker operations are managed via the dedicated script:

```bash
# 1. Start in background on default port 8000
./infra/scripts/docker.sh up -d

# 2. Start on custom port 9000 with image rebuild
./infra/scripts/docker.sh up -d -p 9000 --build

# 3. Start in foreground (streaming live logs directly in terminal)
./infra/scripts/docker.sh up -p 9000

# 4. View / follow live streaming logs
./infra/scripts/docker.sh logs

# 5. Check container status & health
./infra/scripts/docker.sh ps

# 6. Open bash shell inside container
./infra/scripts/docker.sh shell

# 7. Run interactive CLI poller inside Docker
./infra/scripts/docker.sh poller

# 8. Stop the container
./infra/scripts/docker.sh down
```

The web dashboard is accessible at: **http://localhost:8000** (or your custom port `-p <PORT>`).

---

## 📜 Viewing Console Output & Logs in Docker

Because `PYTHONUNBUFFERED=1` is set in the container, all console output (`print()`, NSE poller cycles, Gemini AI sentiment reasoning, order executions, and errors) streams in real-time.

### 1. Follow Live Logs in Real-Time (Follow Mode)
```bash
# With the helper script:
./infra/scripts/docker.sh logs

# Or directly with Docker CLI:
docker logs -f nse_catalyst_terminal
```
*(Press `Ctrl+C` to exit log stream — the container continues running in the background).*

### 2. View Recent Lines + Follow
```bash
# View last 100 log lines and stream new ones
docker logs --tail 100 -f nse_catalyst_terminal
```

### 3. Run in Foreground (Direct Console Attachment)
To see console output directly printed in your active shell window:
```bash
./infra/scripts/docker.sh up
```
*(Press `Ctrl+C` to gracefully shut down the container).*

---

## 🔌 Changing the Port Number

You can easily map any host port (e.g. `9000`, `8080`):

```bash
# Option A: Using helper script
./infra/scripts/docker.sh up -d -p 9000

# Option B: With Docker Compose
PORT=9000 docker compose -f infra/docker/docker-compose.yml up -d
```
Access dashboard at: **http://localhost:9000**

---

## 🛠️ Direct Docker CLI Commands (Without Compose)

```bash
# 1. Build Docker image from strategy root
docker build -f infra/docker/Dockerfile -t nse-catalyst-terminal .

# 2. Run Web GUI container (default port 8000)
docker run -d \
  --name nse_catalyst_terminal \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  nse-catalyst-terminal

# 3. View logs
docker logs -f nse_catalyst_terminal

# 4. Stop and remove container
docker stop nse_catalyst_terminal && docker rm nse_catalyst_terminal
```

