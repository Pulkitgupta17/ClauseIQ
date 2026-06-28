# Deployment

- **Backend** → Google **Cloud Run** (container; auto-scales to zero).
- **Frontend** → **Vercel** (static SPA).
- **Gemini** → **Vertex AI** (billed to your GCP project / credits) with automatic
  fallback to an **AI Studio API key** when Vertex is unavailable or credits run out.

The image **bakes the ChromaDB index at build time**, so there's no persistent disk
and no startup ingestion.

---

## Backend — Cloud Run

### One-time GCP setup

```bash
PROJECT=your-gcp-project
REGION=us-central1   # use a region with both Cloud Run and Vertex Gemini

gcloud config set project "$PROJECT"

# 1. Enable APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com

# 2. Store the AI Studio key (used only as the Vertex fallback)
printf '%s' "YOUR_AISTUDIO_KEY" | gcloud secrets create clauseiq-gemini-key --data-file=-

# 3. Runtime service account for the Cloud Run service (Vertex + secret access)
gcloud iam service-accounts create clauseiq-run --display-name="ClauseIQ Cloud Run"
RUN_SA="clauseiq-run@$PROJECT.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$RUN_SA" --role="roles/aiplatform.user"
gcloud secrets add-iam-policy-binding clauseiq-gemini-key \
  --member="serviceAccount:$RUN_SA" --role="roles/secretmanager.secretAccessor"
```

### First deploy (manual)

```bash
gcloud run deploy clauseiq-api --source . \
  --region "$REGION" --memory 2Gi --cpu 1 --allow-unauthenticated \
  --service-account "$RUN_SA" \
  --set-env-vars "^@@^CLAUSEIQ_ENVIRONMENT=prod@@CLAUSEIQ_GEMINI_BACKEND=vertex@@CLAUSEIQ_GCP_PROJECT=$PROJECT@@CLAUSEIQ_GCP_LOCATION=$REGION@@CLAUSEIQ_CORS_ALLOWED_ORIGINS=[\"https://clauseiq.vercel.app\"]" \
  --set-secrets "CLAUSEIQ_GEMINI_API_KEY=clauseiq-gemini-key:latest"
```

Verify: `curl https://<service-url>/healthz` → `{"status":"ok"}`.

### CI/CD (deploy.yml) — keyless via Workload Identity Federation

`deploy.yml` deploys on every green CI run on `main`. Configure once:

1. Create a Workload Identity Pool + provider for GitHub Actions and a **deployer**
   service account with `roles/run.admin`, `roles/cloudbuild.builds.editor`,
   `roles/artifactregistry.writer`, `roles/iam.serviceAccountUser` (to act as `$RUN_SA`).
2. In the GitHub repo, add:
   - **Variables:** `GCP_PROJECT`, `GCP_REGION`
   - **Secrets:** `GCP_WIF_PROVIDER` (the provider resource name), `GCP_DEPLOY_SA` (the deployer SA email)

The job no-ops if `GCP_PROJECT` is unset, so the rest of CI is unaffected until you wire it up.

### Switching off Vertex (after the credits expire)

The client auto-falls-back to the AI Studio key, so nothing breaks when credits run
out. To make AI Studio the **primary** (skip Vertex entirely), redeploy with
`CLAUSEIQ_GEMINI_BACKEND=ai_studio`. Fallback is controlled by
`CLAUSEIQ_GEMINI_FALLBACK_ENABLED` (default `true`).

---

## Frontend — Vercel

1. Import the repo in Vercel. The root `vercel.json` builds `frontend/`.
2. Set env var **`VITE_API_URL`** to the Cloud Run URL (e.g. `https://clauseiq-api-xxxx.run.app`).
3. Vercel auto-deploys on push to `main`. Update the backend's
   `CLAUSEIQ_CORS_ALLOWED_ORIGINS` to the final Vercel URL.

---

## Local Docker (optional)

```bash
docker build -t clauseiq-api .
docker run --rm -p 8000:8000 -e CLAUSEIQ_GEMINI_API_KEY=your_key clauseiq-api
# index is baked in; /healthz and /health/ready work immediately
```
