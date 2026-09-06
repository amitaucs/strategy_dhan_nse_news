# 🐳 ST15_LargeCap — Docker Operations Guide

This guide covers running and managing the **ST15_LargeCap Positional Momentum Strategy** in Docker.

---

## 🚀 Quick Commands

```bash
# 1. Start in detached mode on port 8015
./infra/scripts/docker.sh up -d --build

# 2. View live logs
./infra/scripts/docker.sh logs

# 3. Check container status
./infra/scripts/docker.sh ps

# 4. Stop container
./infra/scripts/docker.sh down
```

Dashboard URL: **http://localhost:8015**

---

## 🔒 Security & Volumes
* `.dockerignore` excludes all `.env` files and local database files.
* Secrets are loaded at runtime from `strategies/st15_largecap/.env`.
* Runtime SQLite database is mounted at `data/:/app/data`.

