#!/usr/bin/env bash
set -euo pipefail

echo "[postCreate] Installing base utilities (tmux, jq)..."
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends tmux jq

echo "[postCreate] Verifying/Installing GitHub CLI (gh)..."
if ! command -v gh >/dev/null 2>&1; then
  # Fallback: install from distro if the devcontainer feature isn't available for any reason.
  sudo apt-get install -y --no-install-recommends gh
fi

echo "[postCreate] Verifying/Installing Google Cloud SDK (gcloud + bq)..."
if ! command -v gcloud >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends apt-transport-https ca-certificates gnupg curl

  sudo mkdir -p /usr/share/keyrings
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor --batch --yes -o /usr/share/keyrings/cloud.google.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null

  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends google-cloud-cli
fi
if ! command -v bq >/dev/null 2>&1; then
  echo "[postCreate] WARNING: bq CLI not found. Install BigQuery CLI (bq) or ensure your Cloud SDK includes it."
fi

echo "[postCreate] Installing/Updating Codex CLI..."
npm i -g @openai/codex@latest

echo "[postCreate] gh: $(gh --version | head -n 1 || true)"
echo "[postCreate] gcloud: $(gcloud --version | head -n 1 || true)"
echo "[postCreate] bq: $(bq version 2>/dev/null | head -n 1 || true)"

echo "[postCreate] Done."
