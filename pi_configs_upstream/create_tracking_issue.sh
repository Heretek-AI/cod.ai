#!/usr/bin/env bash
set -euo pipefail
# One-click script to open the tracking issue on https://github.com/Heretek-AI/pi-configs
REPO="Heretek-AI/pi-configs"
TITLE="feat(cod.ai): Upgrade pi-configs to 100% cod.ai Architectural Invariant Compliance (Layer-3 Charter Switch, Mode-A Architect Loop, 60-80% Attention Governor & Adversarial Verifier)"
BODY_FILE="$(dirname "$0")/../docs/02_pi_configs_tracking_issue.md"

if command -v gh >/dev/null 2>&1; then
  echo "[+] Creating tracking issue on ${REPO} via GitHub CLI..."
  gh issue create --repo "${REPO}" --title "${TITLE}" --body-file "${BODY_FILE}"
elif [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "[+] Creating tracking issue on ${REPO} via GitHub REST API..."
  python3 -c '
import json, os, urllib.request
body = open(os.environ["BODY_FILE"], "r", encoding="utf-8").read()
payload = json.dumps({"title": os.environ["TITLE"], "body": body, "labels": ["enhancement", "architecture"]}).encode("utf-8")
req = urllib.request.Request(
    f"https://api.github.com/repos/{os.environ["REPO"]}/issues",
    data=payload,
    headers={
        "Authorization": f"Bearer {os.environ["GITHUB_TOKEN"]}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print("Created Issue URL:", data.get("html_url"))
'
else
  echo "[!] Neither authenticated gh CLI nor GITHUB_TOKEN found in current shell."
  echo "    Run with: GITHUB_TOKEN=ghp_xxx ./pi_configs_upstream/create_tracking_issue.sh"
fi
