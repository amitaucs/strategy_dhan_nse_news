# Docker Infrastructure & Deployment

This directory contains containerization files for the **NSE Catalyst Trading Terminal**.

## Security Architecture

Secrets in `.env` (Gemini API keys, Dhan credentials, database passwords) are **strictly isolated** from the Docker image:
1. **`.dockerignore`**: Excludes `.env`, `.pem`, and `data/` from the build context. The image contains only source code and Python dependencies.
2. **Runtime Secret Injection**: Secrets are read from the host's `.env` and injected into container memory (RAM) when the container boots.
3. **Volume Persistence**: The `./data` folder is mounted to `/app/data` to preserve your SQLite database, session states, and trade audit logs across container restarts or image rebuilds.

---

## Quick Start with Docker Helper Script (Recommended)

From the project root:

```bash
# 1. Start in background on default port 8000
./infra/docker/docker.sh up -d

# 2. Start on custom port 9000 with image rebuild
./infra/docker/docker.sh up -d -p 9000 --build

# 3. Start in foreground (streaming live logs directly in terminal)
./infra/docker/docker.sh up -p 9000

# 4. View / follow live streaming logs
./infra/docker/docker.sh logs

# 5. Check container status & health
./infra/docker/docker.sh ps

# 6. Stop the container
./infra/docker/docker.sh down
```

The web dashboard is accessible at: **http://localhost:8000** (or your custom `-p <PORT>`).

---

## Viewing Console Output & Logs in Docker

Because `PYTHONUNBUFFERED=1` is set in the container, all console output (`print()`, NSE poller cycles, Gemini AI sentiment reasoning, order executions, and errors) streams in real-time.

### 1. Follow Live Logs in Real-Time (Follow Mode)
```bash
# With Docker Compose:
docker compose -f infra/docker/docker-compose.yml logs -f

# With Docker CLI:
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
docker compose -f infra/docker/docker-compose.yml up
```
*(Press `Ctrl+C` to gracefully shut down the container).*

---

## Changing the Port Number

You can easily map any host port (e.g. `9000`, `8080`) when running the command:

### With Docker Compose:
```bash
# Option A: Pass inline during command
PORT=9000 docker compose -f infra/docker/docker-compose.yml up -d

# Option B: Add to your .env file
echo "PORT=9000" >> .env
docker compose -f infra/docker/docker-compose.yml up -d
```
Access dashboard at: **http://localhost:9000**

### With Docker CLI:
Change the first number in the `-p` flag (`-p <HOST_PORT>:8000`):
```bash
docker run -d \
  --name nse_catalyst_terminal \
  -p 9000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart unless-stopped \
  nse-catalyst-terminal
```

---

## Manual Docker CLI Commands

```bash
# 1. Build Docker image from project root
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

---

## Running Pure Console Poller in Docker (Without Web GUI)

If you wish to run the interactive CLI terminal poller inside Docker:

```bash
docker run -it --rm \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  nse-catalyst-terminal \
  python3 -m news_based_strategy.main
```

