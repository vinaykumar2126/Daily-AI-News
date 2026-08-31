#!/usr/bin/env bash
#
# One-shot deploy of the Daily AI News Briefing pipeline to Google Cloud.
#
# Prereqs:
#   - gcloud CLI installed and authenticated (`gcloud auth login`)
#   - A GCP project with billing / free credits
#   - A Gmail App Password ready
#
# Edit the CONFIG block below, then run:  bash deploy.sh
set -euo pipefail

# ----------------------------- CONFIG --------------------------------------- #
PROJECT_ID="${PROJECT_ID:-your-gcp-project-id}"
REGION="${REGION:-us-east5}"                 # region that offers Claude on Vertex
JOB_NAME="${JOB_NAME:-daily-news}"
SCHEDULER_NAME="${SCHEDULER_NAME:-daily-news-trigger}"
SCHEDULE="${SCHEDULE:-0 7 * * *}"            # 7:00 AM daily
TIMEZONE="${TIMEZONE:-America/Chicago}"      # <-- set to your timezone
REPO="${REPO:-daily-news}"                   # Artifact Registry repo
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/daily-news:latest"

# Runtime env (non-secret). Secrets are wired via --set-secrets below.
GMAIL_ADDRESS="${GMAIL_ADDRESS:-godavartivinaykumar@gmail.com}"
RECIPIENT="${RECIPIENT:-$GMAIL_ADDRESS}"
TLDR_SENDER="${TLDR_SENDER:-dan@tldrnewsletter.com}"
TTS_VOICE="${TTS_VOICE:-en-US-Neural2-D}"
# ---------------------------------------------------------------------------- #

echo ">> Setting project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

echo ">> Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  texttospeech.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

echo ">> Ensuring Artifact Registry repo exists"
gcloud artifacts repositories describe "$REPO" --location="$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker --location="$REGION" \
    --description="Daily AI news briefing images"

echo ">> Creating Gmail app-password secret (if missing)"
if ! gcloud secrets describe gmail-app-password >/dev/null 2>&1; then
  echo "Paste the Gmail App Password, then press Ctrl-D:"
  gcloud secrets create gmail-app-password --data-file=- --replication-policy=automatic
fi

# Optional: Anthropic API key fallback. Create it manually if you want the fallback:
#   printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-

echo ">> Building & pushing image via Cloud Build"
gcloud builds submit --tag "$IMAGE" .

echo ">> Granting the runtime service account access to secrets + Vertex + TTS"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/secretmanager.secretAccessor roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" --role="$role" --condition=None >/dev/null
done

echo ">> Deploying Cloud Run Job: $JOB_NAME"
SECRET_FLAGS="GMAIL_APP_PASSWORD=gmail-app-password:latest"
# Uncomment to wire the fallback key if you created the secret above:
# SECRET_FLAGS="${SECRET_FLAGS},ANTHROPIC_API_KEY=anthropic-api-key:latest"

gcloud run jobs deploy "$JOB_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --tasks=1 \
  --max-retries=1 \
  --task-timeout=600s \
  --set-env-vars="GMAIL_ADDRESS=${GMAIL_ADDRESS},RECIPIENT=${RECIPIENT},TLDR_SENDER=${TLDR_SENDER},LLM_PROVIDER=gemini,GEMINI_MODEL=gemini-2.5-flash,GEMINI_REGION=us-central1,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},TTS_VOICE=${TTS_VOICE}" \
  --set-secrets="$SECRET_FLAGS"

echo ">> Creating/updating Cloud Scheduler trigger: $SCHEDULER_NAME"
RUN_URL="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"
gcloud scheduler jobs describe "$SCHEDULER_NAME" --location="$REGION" >/dev/null 2>&1 && \
  SCHED_CMD=update || SCHED_CMD=create

gcloud scheduler jobs "$SCHED_CMD" http "$SCHEDULER_NAME" \
  --location="$REGION" \
  --schedule="$SCHEDULE" \
  --time-zone="$TIMEZONE" \
  --uri="$RUN_URL" \
  --http-method=POST \
  --oauth-service-account-email="$RUNTIME_SA"

echo ">> Done."
echo "   Test now:   gcloud run jobs execute $JOB_NAME --region $REGION"
echo "   Logs:       gcloud run jobs executions list --job $JOB_NAME --region $REGION"
