# Deploying to Azure (Local → Production)

This guide takes the AP Exception Agent from a working local setup to a production
deployment on Azure. It is written for **this** repo's stack, so every command and
variable matches what the code actually expects.

---

## 1. What we are deploying

The app is **two containers** plus a database:

| Component | Image source | Port | Role |
|-----------|--------------|------|------|
| **api** (FastAPI/uvicorn) | [Backend/Dockerfile](Backend/Dockerfile) | `8000` | REST API + AI pipeline |
| **web** (React/Vite → nginx) | [Frontend/Dockerfile](Frontend/Dockerfile) | `80` | SPA + reverse-proxy for `/v1`, `/healthz`, `/readyz` |
| **database** | Azure Database for PostgreSQL (or Supabase) | `5432` | Durable run/exception store |

Key design facts that shape the deployment (from [Frontend/nginx.conf](Frontend/nginx.conf)
and [Backend/docker-compose.yml](Backend/docker-compose.yml)):

- The browser talks to **one origin**. `nginx` serves the SPA and proxies API paths
  to the backend, so `VITE_API_BASE_URL` is built as `""` (same-origin). **No CORS**
  is needed between the two containers when the web container can reach the api by
  its internal hostname.
- Frontend build args (`VITE_*`) are **baked at image build time** — they are not
  runtime config. Changing the Clerk key or API base means rebuilding the web image.
- The backend picks its AI provider by precedence: **Anthropic → Gemini → Azure
  OpenAI → mock** (see [Backend/app/config.py](Backend/app/config.py)). Set the key
  for whichever you use.

### Recommended Azure service: **Azure Container Apps (ACA)**

ACA is the best fit here — it runs both containers, scales to zero, gives you managed
TLS + a public hostname, and handles internal service-to-service networking. This
guide uses ACA. (Alternatives: **App Service for Containers** if you prefer a single
web app per container, or **AKS** if you already run Kubernetes. The image build and
env-var steps are identical; only the "create the runtime" step differs.)

```
Internet ──HTTPS──▶ [web container : nginx :80] ──/v1 proxy──▶ [api container :8000] ──▶ PostgreSQL
                     (external ingress)              (internal ingress)          (private)
```

---

## 2. Prerequisites (one-time)

Install locally:

- **Docker Desktop** (to build/run images)
- **Azure CLI** — `az` — https://learn.microsoft.com/cli/azure/install-azure-cli
- The **containerapp** extension:
  ```bash
  az extension add --name containerapp --upgrade
  ```

Have ready:

- An **Azure subscription** with permission to create resources.
- Your **AI provider key** (Anthropic recommended — `ANTHROPIC_API_KEY`).
- A **Clerk** account if auth is enabled (publishable key for the frontend, issuer
  for the backend).

Log in and pick your subscription:

```bash
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"
```

Set shell variables reused throughout (bash / Git Bash / WSL):

```bash
RG=ap-agent-rg                 # resource group
LOC=eastus                     # region
ACR=apagentacr$RANDOM          # ACR name must be globally unique, lowercase, no dashes
ENVNAME=ap-agent-env           # Container Apps environment
```

---

## 3. Verify it works locally first

Never debug in the cloud what you can catch on your laptop. From `Backend/`:

```bash
cd Backend
export ANTHROPIC_API_KEY=sk-ant-...            # or leave unset to run in mock mode
export VITE_CLERK_PUBLISHABLE_KEY=pk_test_...  # if using Clerk auth
docker compose up --build
```

Then check:

- Web UI: http://localhost:8080
- API health: http://localhost:8000/readyz  → should return ready
- API docs: http://localhost:8000/docs

If this works, the images are good. Ctrl-C to stop.

> The compose file uses SQLite in a volume by default. Production should use
> Postgres (Section 6). Confirm the app boots in mock mode too, so a missing key
> in the cloud fails loud, not silent.

---

## 4. Create Azure resources

```bash
# Resource group
az group create --name $RG --location $LOC

# Azure Container Registry (holds your images)
az acr create --resource-group $RG --name $ACR --sku Basic --admin-enabled true

# Container Apps environment (shared network + logging for both apps)
az containerapp env create \
  --name $ENVNAME --resource-group $RG --location $LOC
```

---

## 5. Build and push the images to ACR

`az acr build` builds **in the cloud** (no local Docker push needed) and is the
simplest path. Run from the repo root.

```bash
# Backend image
az acr build --registry $ACR --image ap-agent-api:latest ./Backend

# Frontend image — VITE_* must be passed as BUILD ARGS (baked in).
# VITE_API_BASE_URL="" keeps it same-origin (nginx proxies /v1 to the api app).
az acr build --registry $ACR --image ap-agent-web:latest \
  --build-arg VITE_API_BASE_URL="" \
  --build-arg VITE_CLERK_PUBLISHABLE_KEY="pk_live_xxx" \
  --build-arg VITE_TENANT_ID="default" \
  ./Frontend
```

> ⚠️ If you rotate the Clerk key or change the API base, **rebuild the web image** —
> these are compile-time, not runtime, values.

---

## 6. Provision the database (production)

Do **not** ship SQLite to production (it lives in a single container's filesystem and
is lost on redeploy). Two supported options:

### Option A — Azure Database for PostgreSQL (recommended)

```bash
az postgres flexible-server create \
  --resource-group $RG \
  --name ap-agent-db \
  --location $LOC \
  --admin-user apadmin \
  --admin-password '<STRONG_PASSWORD>' \
  --sku-name Standard_B1ms --tier Burstable \
  --version 16 --storage-size 32 \
  --public-access 0.0.0.0   # allow Azure services; tighten to VNet for real prod

az postgres flexible-server db create \
  --resource-group $RG --server-name ap-agent-db --database-name apagent
```

Your `DATABASE_URL` will be:

```
postgresql+psycopg://apadmin:<PASSWORD>@ap-agent-db.postgres.database.azure.com:5432/apagent?sslmode=require
```

Set `DB_PERSISTENCE_ENABLED=true` and `RUN_STORE_BACKEND=db` so the normalized tables
and durable run store are used (see the run-store notes in
[Backend/app/config.py](Backend/app/config.py)). Run migrations once after the app can
reach the DB (Section 9).

### Option B — Supabase

If you already use Supabase, set `SUPABASE_URL` and `SUPABASE_KEY` (**service_role**
key, server-side only) and leave `RUN_STORE_BACKEND=auto`. Apply the SQL in
[Backend/supabase/](Backend/supabase/) to your project first.

---

## 7. Deploy the API container app

Grab the ACR login server and credentials:

```bash
ACR_SERVER=$(az acr show -n $ACR --query loginServer -o tsv)
ACR_USER=$(az acr credential show -n $ACR --query username -o tsv)
ACR_PASS=$(az acr credential show -n $ACR --query 'passwords[0].value' -o tsv)
```

Create the API app with **internal** ingress on port 8000 (only the web app needs to
reach it):

```bash
az containerapp create \
  --name ap-agent-api \
  --resource-group $RG \
  --environment $ENVNAME \
  --image $ACR_SERVER/ap-agent-api:latest \
  --registry-server $ACR_SERVER \
  --registry-username $ACR_USER \
  --registry-password $ACR_PASS \
  --target-port 8000 \
  --ingress internal \
  --min-replicas 1 --max-replicas 3 \
  --cpu 1.0 --memory 2.0Gi
```

Set the runtime secrets and env vars (secrets first, then reference them):

```bash
az containerapp secret set --name ap-agent-api --resource-group $RG --secrets \
  anthropic-key="sk-ant-..." \
  database-url="postgresql+psycopg://apadmin:<PASSWORD>@ap-agent-db.postgres.database.azure.com:5432/apagent?sslmode=require" \
  clerk-issuer="https://<your>.clerk.accounts.dev"

az containerapp update --name ap-agent-api --resource-group $RG \
  --set-env-vars \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO \
    ANTHROPIC_API_KEY=secretref:anthropic-key \
    DATABASE_URL=secretref:database-url \
    DB_PERSISTENCE_ENABLED=true \
    RUN_STORE_BACKEND=db \
    RUN_QUEUE_ENABLED=true \
    AUTH_ENABLED=true \
    CLERK_ISSUER=secretref:clerk-issuer \
    COMMS_DRYRUN=true \
    ARTIFACT_DIR=/app/artifacts
```

Get the API's **internal** hostname (used by nginx in the next step):

```bash
API_FQDN=$(az containerapp show -n ap-agent-api -g $RG \
  --query properties.configuration.ingress.fqdn -o tsv)
echo $API_FQDN   # e.g. ap-agent-api.internal.<env>.eastus.azurecontainerapps.io
```

---

## 8. Point the frontend proxy at the API, then deploy the web app

`nginx.conf` currently hardcodes `proxy_pass http://api:8000;` — the docker-compose
service name. In ACA there is no `api` host, so the proxy target must be the API app's
internal FQDN. Two ways:

**Option 1 (simplest): edit [Frontend/nginx.conf](Frontend/nginx.conf) before building.**
Replace the three `http://api:8000` targets with `http://$API_FQDN` (port 80 —
ACA internal ingress terminates on 80, not 8000), then rebuild the web image
(Section 5). For example:

```nginx
location /v1/ {
    proxy_pass http://ap-agent-api.internal.<env>.eastus.azurecontainerapps.io;
    ...
}
location = /healthz { proxy_pass http://ap-agent-api.internal.<env>.eastus.azurecontainerapps.io; }
location = /readyz  { proxy_pass http://ap-agent-api.internal.<env>.eastus.azurecontainerapps.io; }
```

**Option 2 (cleaner, optional): templatize the upstream** with an `envsubst` entrypoint
so the target is injected at container start instead of baked in. Not required for a
first deploy — do Option 1 to ship, refactor later.

Then create the web app with **external** ingress on port 80:

```bash
az containerapp create \
  --name ap-agent-web \
  --resource-group $RG \
  --environment $ENVNAME \
  --image $ACR_SERVER/ap-agent-web:latest \
  --registry-server $ACR_SERVER \
  --registry-username $ACR_USER \
  --registry-password $ACR_PASS \
  --target-port 80 \
  --ingress external \
  --min-replicas 1 --max-replicas 3 \
  --cpu 0.5 --memory 1.0Gi

# Public URL:
az containerapp show -n ap-agent-web -g $RG \
  --query properties.configuration.ingress.fqdn -o tsv
```

Open that URL — you should see the reviewer console, and it should reach the API
through the same origin.

---

## 9. Run database migrations (once)

The API image ships Alembic ([Backend/alembic](Backend/alembic)). Run migrations
against the production DB via a one-off ACA exec:

```bash
az containerapp exec -n ap-agent-api -g $RG --command "/bin/sh"
# then inside the container:
alembic upgrade head
exit
```

(Or run `python scripts/init_db.py` for a fresh schema — check
[Backend/scripts/init_db.py](Backend/scripts/init_db.py) for what it does before using
it against a real database.)

---

## 10. Production environment checklist

The code enforces stricter gates when `ENVIRONMENT` starts with `prod`/`stag`
(`is_protected_env` in [Backend/app/config.py](Backend/app/config.py)). Set these
deliberately:

| Variable | Production value | Why |
|----------|------------------|-----|
| `ENVIRONMENT` | `production` | Turns on the safety gates (auth, CORS, comms allow-list, durable store) |
| `ANTHROPIC_API_KEY` | your key (secret) | Selects the real AI provider (else falls back / mock) |
| `DATABASE_URL` | Postgres URL (secret) | Durable storage |
| `DB_PERSISTENCE_ENABLED` | `true` | Write normalized enterprise tables |
| `RUN_STORE_BACKEND` | `db` | Force the durable run store |
| `RUN_QUEUE_ENABLED` | `true` | Runs survive restarts / are retried |
| `AUTH_ENABLED` | `true` | Require Clerk JWT on `/v1/*` |
| `CLERK_ISSUER` | `https://<x>.clerk.accounts.dev` (secret) | JWT verification |
| `CORS_ALLOW_ORIGINS` | your web app URL | Only needed if the SPA is ever served cross-origin; same-origin nginx setup needs nothing |
| `COMMS_DRYRUN` | `true` until you're ready | Prevents accidental real vendor emails |
| `COMMS_ALLOWED_DOMAINS` | your test domains | Live-send allow-list once `COMMS_DRYRUN=false` |
| `CONFIG_ENC_KEY` | Fernet key (secret) | Only if `PER_ORG_CONFIG_ENABLED=true` |
| `SENTRY_DSN` | your DSN (optional) | Error tracking |

**Frontend (build-time, baked):** `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_BASE_URL=""`,
`VITE_TENANT_ID`.

> Keep `COMMS_DRYRUN=true` for the first production runs. Flip to `false` **only**
> after setting `COMMS_ALLOWED_DOMAINS` and verifying dry-run `.eml` output in
> `artifacts/sent/`.

---

## 11. Custom domain + TLS (optional)

ACA gives you a free `*.azurecontainerapps.io` HTTPS hostname out of the box. To use
your own domain on the **web** app:

```bash
az containerapp hostname add -n ap-agent-web -g $RG --hostname app.yourcompany.com
az containerapp hostname bind -n ap-agent-web -g $RG --hostname app.yourcompany.com \
  --environment $ENVNAME --validation-method CNAME
```

Add the CNAME/TXT records Azure asks for at your DNS provider. ACA manages the
certificate. Update `CLERK_ISSUER` allowed origins and, if you enabled it,
`PUBLIC_BASE_URL` to the new domain.

---

## 12. Redeploying after a change

```bash
# Backend code change:
az acr build --registry $ACR --image ap-agent-api:latest ./Backend
az containerapp update -n ap-agent-api -g $RG --image $ACR_SERVER/ap-agent-api:latest

# Frontend change (remember VITE_* build args!):
az acr build --registry $ACR --image ap-agent-web:latest \
  --build-arg VITE_API_BASE_URL="" \
  --build-arg VITE_CLERK_PUBLISHABLE_KEY="pk_live_xxx" ./Frontend
az containerapp update -n ap-agent-web -g $RG --image $ACR_SERVER/ap-agent-web:latest
```

### CI/CD (optional next step)

There is already a CI workflow at [.github/workflows/ci.yml](.github/workflows/ci.yml).
To auto-deploy on merge to `develop`, add a job that runs the `az acr build` +
`az containerapp update` commands above, authenticating with `azure/login` and a
service principal / OIDC. Store `ANTHROPIC_API_KEY`, DB URL, and Clerk keys as GitHub
Actions secrets — never in the repo.

---

## 13. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Web loads but `/v1` calls 502 | nginx still points at `http://api:8000` | Rebuild web image with the API's internal FQDN (Section 8) |
| API replica keeps restarting | `/readyz` failing — bad `DATABASE_URL` or missing migration | Check `az containerapp logs show -n ap-agent-api -g $RG`; run migrations |
| All AI output is placeholder | No provider key set → `mock` provider | Set `ANTHROPIC_API_KEY` secret |
| 401 on every `/v1` route | `AUTH_ENABLED=true` but Clerk token/issuer mismatch | Verify `CLERK_ISSUER` and the frontend publishable key are the same Clerk instance |
| Emails not sending | `COMMS_DRYRUN=true` (expected) | Set `COMMS_DRYRUN=false` + `COMMS_ALLOWED_DOMAINS` when ready |
| Data lost on redeploy | Still on SQLite | Move to Postgres (Section 6) |

Useful commands:

```bash
az containerapp logs show -n ap-agent-api -g $RG --follow
az containerapp revision list -n ap-agent-web -g $RG -o table
az containerapp show -n ap-agent-web -g $RG --query properties.configuration.ingress.fqdn -o tsv
```

---

## Quick reference — the whole flow

1. `az login` → create RG, ACR, ACA environment
2. `az acr build` both images (web needs `VITE_*` build args)
3. Create Postgres, get `DATABASE_URL`
4. Create **api** app (internal ingress :8000) + set secrets/env
5. Point `nginx.conf` at the api's internal FQDN → rebuild web image
6. Create **web** app (external ingress :80)
7. `alembic upgrade head`
8. Verify the public URL, keep `COMMS_DRYRUN=true`
9. (Optional) custom domain, CI/CD
