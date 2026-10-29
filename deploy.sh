#!/usr/bin/env bash
#
# One-shot deploy of the Daily AI News interactive phone agent to Google Cloud.
#
# The daily job (Cloud Run Job + Scheduler) runs `python -m agent.sync --call`:
#   1. builds today's curated briefing (sources -> agentic curate -> rewrite),
#   2. pushes it as the ElevenLabs agent's knowledge base + host persona,
#   3. places the outbound call to USER_PHONE_NUMBER so the agent rings you each morning.
# The old email/MP3 path (main.py) is retired — this overwrites the same job/scheduler names.
#
# Prereqs:
#   - gcloud CLI installed and authenticated (`gcloud auth login`)
#   - A GCP project with billing / free credits
#   - A Gmail App Password ready (still read by config.py) and an ElevenLabs API key
#   - A Twilio number already imported into ElevenLabs (phone_number_id below)
#   - USER_PHONE_NUMBER exported in your shell (PII — never hardcoded here):
#       export USER_PHONE_NUMBER='+1...'
#
# Edit the CONFIG block below, then run:  bash deploy.sh
set -euo pipefail

# ----------------------------- CONFIG --------------------------------------- #
PROJECT_ID="${PROJECT_ID:-dailynews-507123}"
REGION="${REGION:-us-central1}"              # runs job + scheduler; matches Gemini region
JOB_NAME="${JOB_NAME:-daily-news}"
SCHEDULER_NAME="${SCHEDULER_NAME:-daily-news-trigger}"
SCHEDULE="${SCHEDULE:-30 11 * * *}"           # 11:30 AM daily
TIMEZONE="${TIMEZONE:-America/New_York}"     # <-- set to your timezone
REPO="${REPO:-daily-news}"                   # Artifact Registry repo
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/daily-news:latest"

# Dedicated runtime identity (keyless): the job runs AS this SA; Scheduler triggers AS this SA.
RUNTIME_SA="${RUNTIME_SA:-vertex-ai-runner@${PROJECT_ID}.iam.gserviceaccount.com}"

# Runtime env (non-secret). Secrets are wired via --set-secrets below.
# The feed catalog (sources, topics, budgets) lives in feeds.yaml, baked into the image.
GMAIL_ADDRESS="${GMAIL_ADDRESS:-godavartivinaykumar@gmail.com}"  # still required by config.py
RECIPIENT="${RECIPIENT:-$GMAIL_ADDRESS}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"
GEMINI_REWRITE_MODEL="${GEMINI_REWRITE_MODEL:-gemini-2.5-pro}"
GEMINI_REGION="${GEMINI_REGION:-us-central1}"
CURATOR="${CURATOR:-agentic}"                # the strategy you built + evaluated

# Realtime phone agent (ElevenLabs Conversational AI). The API key is a secret (below).
REALTIME_PROVIDER="${REALTIME_PROVIDER:-elevenlabs}"
ELEVENLABS_AGENT_ID="${ELEVENLABS_AGENT_ID:-agent_9801m2xxq5enecd8p03w4w5zzvmv}"
ELEVENLABS_PHONE_NUMBER_ID="${ELEVENLABS_PHONE_NUMBER_ID:-phnum_8201m477tk64ejnsnkmt2dea3yzt}"
ELEVENLABS_VOICE_ID="${ELEVENLABS_VOICE_ID:-}"   # empty = use the agent's configured voice
USER_PHONE_NUMBER="${USER_PHONE_NUMBER:-}"       # who to call — export in your shell (PII)

GCS_BUCKET="${GCS_BUCKET:-}"                  # optional: archive + agentic memory store
# ---------------------------------------------------------------------------- #

if [[ -z "$USER_PHONE_NUMBER" ]]; then
  echo "ERROR: USER_PHONE_NUMBER is empty — the daily job places an outbound call and needs it." >&2
  echo "       export USER_PHONE_NUMBER='+1...' and re-run." >&2
  exit 1
fi

echo ">> Setting project: $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

echo ">> Enabling APIs"
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  aiplatform.googleapis.com \
  cloudtrace.googleapis.com \
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
  echo "Paste the Gmail App Password (16 chars, no spaces), then press Ctrl-D:"
  gcloud secrets create gmail-app-password --data-file=- --replication-policy=automatic
fi

echo ">> Creating ElevenLabs API-key secret (if missing)"
if ! gcloud secrets describe elevenlabs-api-key >/dev/null 2>&1; then
  echo "Paste the ElevenLabs API key, then press Ctrl-D:"
  gcloud secrets create elevenlabs-api-key --data-file=- --replication-policy=automatic
fi

echo ">> Building & pushing image via Cloud Build"
gcloud builds submit --tag "$IMAGE" .

echo ">> Granting the runtime service account least-privilege roles"
#   aiplatform.user              -> call Gemini on Vertex (rewrite + agentic curator via ADK)
#   secretmanager.secretAccessor -> read the Gmail + ElevenLabs secrets
#   run.developer                -> let Cloud Scheduler trigger the job (run.jobs.run)
#   cloudtrace.agent             -> ship OpenTelemetry GenAI spans to Cloud Trace
for role in \
  roles/aiplatform.user \
  roles/secretmanager.secretAccessor \
  roles/run.developer \
  roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${RUNTIME_SA}" --role="$role" --condition=None >/dev/null
done

echo ">> Deploying Cloud Run Job: $JOB_NAME (runs as ${RUNTIME_SA})"
# The image ENTRYPOINT is `python main.py` (the old MP3 path); override it to run the phone agent.
gcloud run jobs deploy "$JOB_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA" \
  --tasks=1 \
  --max-retries=1 \
  --task-timeout=900s \
  --command="python" \
  --args="^@^-m@agent.sync@--call" \
  --set-env-vars="GMAIL_ADDRESS=${GMAIL_ADDRESS},RECIPIENT=${RECIPIENT},GEMINI_MODEL=${GEMINI_MODEL},GEMINI_REWRITE_MODEL=${GEMINI_REWRITE_MODEL},GEMINI_REGION=${GEMINI_REGION},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},CURATOR=${CURATOR},REALTIME_PROVIDER=${REALTIME_PROVIDER},ELEVENLABS_AGENT_ID=${ELEVENLABS_AGENT_ID},ELEVENLABS_PHONE_NUMBER_ID=${ELEVENLABS_PHONE_NUMBER_ID},ELEVENLABS_VOICE_ID=${ELEVENLABS_VOICE_ID},USER_PHONE_NUMBER=${USER_PHONE_NUMBER},GCS_BUCKET=${GCS_BUCKET}" \
  --set-secrets="GMAIL_APP_PASSWORD=gmail-app-password:latest,ELEVENLABS_API_KEY=elevenlabs-api-key:latest"

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
  --oauth-service-account-email="$RUNTIME_SA" \
  --max-retry-attempts=3 \
  --min-backoff=60s \
  --max-backoff=300s
# Retries: the default is zero, so one transient 503 from the Cloud Run API (as on 2026-10-29)
# skipped the whole day's call. A failed attempt never created an execution, so retrying can't
# double-ring; at worst the call lands a few minutes late (60s, 120s, 240s).

echo ">> Done."
echo "   Test now:   gcloud run jobs execute $JOB_NAME --region $REGION   # refreshes + calls you"
echo "   Logs:       gcloud run jobs executions list --job $JOB_NAME --region $REGION"
echo "   Schedule:   ${SCHEDULE} (${TIMEZONE})  ->  rings ${USER_PHONE_NUMBER}"
