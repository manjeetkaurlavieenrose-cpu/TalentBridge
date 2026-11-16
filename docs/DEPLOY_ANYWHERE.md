# Putting TalentBridge online

GitHub stores the code; it cannot run the app (GitHub Pages only serves static pages). A hosting service runs it. The files in
this folder make that a one-click job on Render and a one-command job on any server with Docker.

| Where | How | Good for | Limits |
|---|---|---|---|
| **Render** (free plan) | "Deploy to Render" button in README.md (reads `render.yaml`) | a demo link to share | sleeps after ~15 min idle (first visit then ~1 min); data is wiped on each restart, so it runs in demo mode with fresh fictional data |
| **Render** (paid "Starter" plan + disk) | same button, then in Render: plan *Starter*, add a disk mounted at `/data`, set `DEMO_SEED=0`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | a small real pilot | costs money; set up privacy notice and consent first (AUDIT_REPORT.md) |
| **Any server with Docker** (university VM, VPS) | `docker compose -f compose.simple.yaml up -d`, or `docker run` with the image from GitHub (`ghcr.io/<owner>/<repo>:latest`) | full control, data kept in a volume | you need https in front for real use (Caddy; see docs/DEPLOY.md) |
| **Full set-up** (PostgreSQL, separate worker, local AI model, https) | `compose.yaml` + docs/DEPLOY.md | institutional deployment | needs a server with 8+ GB RAM |

The app adapts by itself to Render, Fly.io, Railway, Google Cloud Run, Heroku and GitHub Codespaces (listening address, https cookies,
proxy headers and its own public address; see `backend/app/hosting.py`). On any other host behind https, set `TB_BEHIND_HTTPS=1`.

**AI on a hosting service.** Free hosting plans have too little memory to run the local AI model, so there the built-in rule-based
engine does the work (every result says which engine produced it). To use a model online, point the app at an OpenAI-compatible
service with these settings in the host's environment: `AI_PROVIDER=openai`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`.
Some providers have free tiers; CV text is then sent to that provider, so check its terms and your privacy rules first.

**The container image** is published by `.github/workflows/docker.yml` to GitHub's registry after it has been started and checked.
New GitHub packages are private: to let any server pull it without signing in, open the package on GitHub → *Package settings* →
*Change visibility* → *Public*.
