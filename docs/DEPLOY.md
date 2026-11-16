# Host TalentBridge for access from any device

The local launcher is for one computer. For a professor or candidate to open the same application from a Mac, Windows PC, iPhone, iPad, or Android phone, host it on an internet-reachable Linux server and give them its HTTPS address. The browser UI is responsive; there are no separate native apps.

This repository includes a Docker Compose deployment with a Flask web service, a separate background worker, PostgreSQL, persistent CV storage, Ollama with `qwen2.5:3b`, and Caddy for HTTPS. PostgreSQL, uploaded CVs, and Ollama are on private container networking/storage. Only Caddy publishes ports 80 and 443; Ollama's port 11434 is not published. The included stack keeps email in the file outbox until a real provider is configured.

## Free hosting reality

The preferred no-cost route is an existing lab/university server approved for the project. If none is available, Oracle OCI currently lists an Always Free Ampere VM allowance equivalent to **2 OCPUs and 12 GB RAM**, plus **200 GB combined block storage**. The qwen2.5:3b image is about 1.9 GB. This is a plausible small demo host for this Compose stack, but expect slower CPU inference than the development Mac. OCI account sign-up requires a phone and credit card for most users; Oracle says the card is not charged unless the account is upgraded. Always Free instance capacity can be unavailable, and Oracle may reclaim an instance it considers idle: over 7 days, CPU 95th percentile under 20%, network under 20%, and for A1, memory under 20%. That makes it a trial option, not a guaranteed permanent service. [OCI Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [sign-up/payment terms](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

For a free hostname, the owner may use a free DuckDNS subdomain; set its A record to the VM's public address and update that DNS entry if the address changes. [DuckDNS describes its service as free dynamic DNS](https://www.duckdns.org/faqs.jsp). Caddy can obtain public HTTPS when the hostname resolves to the VM and ports 80/443 reach it. The project owner must accept these third-party account and availability terms; no account is created by this repository.

Free public hosting plans are useful for disposable previews, but the current published limits conflict with reliable, persistent use here:

- Render's free web services sleep after 15 minutes idle and have an ephemeral filesystem; its free PostgreSQL database expires after 30 days. That risks slow first access and loss of uploaded files/local data or the database. [Render free service limits](https://render.com/docs/free)
- Hugging Face Spaces' free CPU runtime sleeps when idle, and its default disk is ephemeral. Its overview says Docker/Gradio compute requires a paid plan; free static Spaces cannot run this backend/model workflow. [Spaces overview](https://huggingface.co/docs/hub/spaces-overview) and [storage behavior](https://huggingface.co/docs/hub/main/spaces-storage)
- GitHub Pages or any static HTML host can publish the interface files only; it cannot run Flask, the database, background jobs, or Ollama.

So do not promise an always-available, data-persistent, fully AI-powered public app on a free cloud tier. If there is no institutional server, use an existing lab computer as the host for a supervised demo; it must stay powered on, and access will depend on the lab network/VPN. Don't expose a personal laptop or router to the internet for real CV data.

## What the server needs

- A Linux VPS, university VM, or Oracle Always Free A1 VM with Docker Engine plus the Compose plugin and persistent disk. For a smoother hosted experience, target 4+ vCPUs and 8+ GB RAM; the Oracle Always Free A1 limit is 2 OCPUs/12 GB RAM, so CPU AI may be slow.
- An institution-approved hostname/subdomain and HTTPS route. Caddy obtains and renews a public TLS certificate when the hostname resolves to the server and inbound TCP ports 80/443 reach it. [Caddy HTTPS requirements](https://caddyserver.com/docs/quick-starts/https). If university policy uses a central proxy, ask IT to configure TLS/reverse proxying and follow the trusted-proxy notes below instead of opening server ports yourself.
- A long unique administrator password and generated PostgreSQL password. Keep `.env.production` private and outside backups shared with the professor.

## First deployment

### Oracle Always Free VM setup

1. The project owner signs up for [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/), chooses a home region, and completes the provider's account verification themselves. Most sign-ups request a phone number and credit card; Oracle says the card is not charged unless the owner upgrades the account. Do not upgrade or provision anything that is not labeled **Always Free**. Oracle can report no A1 capacity in a region; do not choose a paid shape to work around that.
2. In Compute, create an Always Free eligible Ubuntu ARM64 `VM.Standard.A1.Flex` instance with **2 OCPUs and 12 GB memory**, and keep its boot volume within the Always Free block-volume allowance. Do not provision a paid load balancer or paid database. Current allowance and inactivity policy are listed in [Oracle's official resource page](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).
3. Use a public subnet with an internet gateway and public IP. In both the OCI security list/NSG and the Ubuntu firewall, allow TCP 80 and 443 from the internet. Allow SSH (TCP 22) only from the administrator's current public IP. Do **not** open 8000, 5432, or 11434. Oracle documents that public access also requires the public IP, route, and security rules ([public IP requirements](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingpublicIPs.htm)).
4. Create a free DuckDNS hostname and point its A record to the VM public IP. In `.env.production`, set `PUBLIC_HOST`, `PUBLIC_URL`, and `ALLOWED_ORIGINS` to that hostname as shown in `.env.production.example`. If the VM is recreated and its public IP changes, update DuckDNS. Never put a DuckDNS token in a public repository.
5. SSH to the VM using the key registered during instance creation, install Docker Engine and the Compose plugin using [Docker's official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/), then follow steps 2–8 below.

Before proceeding, confirm the OCI console shows only Always Free-eligible resources and a $0 estimate/usage for them. Oracle can reclaim an instance it classifies as idle over 7 days, so this is suitable for a free supervised demonstration, not a guaranteed always-on service. Keep backups of the database and uploads away from the VM.

1. Install Docker Engine and the Compose plugin using the [official Docker instructions](https://docs.docker.com/engine/install/). On a Mac or Windows workstation, Docker Desktop is suitable for a local trial; a Linux host is recommended for an always-on deployment.
2. Clone/copy this project onto the Linux host. Create a private environment file:

   ```sh
   cp .env.production.example .env.production
   chmod 600 .env.production
   ```

3. Edit `.env.production`: set `PUBLIC_HOST`, `PUBLIC_URL`, `ALLOWED_ORIGINS`, `ADMIN_EMAIL`, and a unique `ADMIN_PASSWORD`. Generate a database password using `openssl rand -hex 32` and place it in `POSTGRES_PASSWORD`. Use the generated hexadecimal value as-is; Compose builds the PostgreSQL URL from these values. Keep `DEMO_SEED=0`, `COOKIE_SECURE=1`, and `EMBEDDED_WORKER=0`.
4. Point the domain DNS A record to this server. Wait for DNS propagation and confirm ports 80/443 can reach it.
5. Build and start the services:

   ```sh
   docker compose --project-name talentbridge --env-file .env.production up -d --build
   docker compose --project-name talentbridge --env-file .env.production ps
   ```

6. Pull the model into the private Ollama service. This download can take several minutes:

   ```sh
   docker compose --project-name talentbridge --env-file .env.production exec ollama ollama pull qwen2.5:3b
   ```

7. Check service health and the AI status:

   ```sh
   curl --fail https://YOUR_DOMAIN/api/v1/health
   ```

   Confirm `ok` is true, `ai_model.reachable` and `ai_model.installed` are true, and `ai_model.model` is `qwen2.5:3b`. Do not invite candidates while the model is unavailable: the application labels its rule-based fallback, but this handover specifically expects working Ollama AI.
8. Sign in with the first admin account. Register one recruiter account and one fictional candidate, upload a fictional CV, and run through [DEMO_SCRIPT.md](../DEMO_SCRIPT.md). Do not use real CVs for the acceptance demo.

## Service layout and safety

- `web`: serves the same-origin responsive frontend and API; it is not published directly to the internet.
- `worker`: parses CVs and processes AI/email jobs using the same database and persistent upload volume as `web`.
- `db`: PostgreSQL, private, with a named persistent volume.
- `ollama`: local `qwen2.5:3b` runtime, private, with a named model volume. Do not add a public port mapping for 11434.
- `caddy`: public HTTPS entry point and reverse proxy. It forwards only to `web`.
- `app-data`: shared persistent uploaded files; `postgres-data`: application records; `ollama-data`: downloaded model. `docker compose down` preserves named volumes. **Do not run `docker compose down -v` on a live deployment**; `-v` removes stored data.

Secrets are environment variables and are not built into the image. Demo accounts are disabled. The cookie is marked Secure, request rate limits use the shared database, and one trusted reverse proxy is configured. Review `TRUSTED_PROXIES` if placing another CDN/proxy in front of Caddy. Keep OS and Docker updates current and restrict SSH access.

## Update and backup

Update code from the approved project revision, then run `docker compose --project-name talentbridge --env-file .env.production up -d --build`. Back up PostgreSQL and the uploads volume together; they contain linked application state. For example, from the project directory:

```sh
mkdir -p backups
docker compose --project-name talentbridge --env-file .env.production exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backups/talentbridge.sql
docker run --rm -v talentbridge_app-data:/source:ro -v "$PWD/backups:/backup" alpine sh -c 'cd /source && tar czf /backup/talentbridge-uploads.tgz uploads'
```

The commands above fix the Compose project name as `talentbridge`, so the uploads volume is `talentbridge_app-data`. Store encrypted copies away from the server; never include `.env.production` in a handover archive. Test restoring both the database and uploads to a separate instance before relying on the backup.

## Limitations to resolve before real candidate use

- Email delivery is unconfigured. The stack writes messages to the private outbox; assessments remain available inside the application.
- No OCR is available for scanned PDFs. Candidates and recruiters see extraction limitations.
- The model is decision support, not a hiring decision. Recruiters must inspect answers and evidence; do not use an automated score alone to accept or reject anyone.
- Confirm privacy notice, consent, retention/deletion schedule, data-processing terms, and applicable institutional/legal review before using real candidate data.
- Configure monitoring, a tested restore procedure, and any required institutional security review. This Compose stack has not been launched in this environment because Docker is not installed here.

## Local Docker smoke test

After installing Docker Desktop, use the same `.env.production` steps but set `PUBLIC_HOST=localhost`, `PUBLIC_URL=http://localhost`, `ALLOWED_ORIGINS=http://localhost`, and `COOKIE_SECURE=0`. For a local-only trial, use an HTTP Caddy address by changing the site label in `Caddyfile` to `http://localhost`. This local mode is for a private computer only; restore the real domain label and `COOKIE_SECURE=1` before public use.
