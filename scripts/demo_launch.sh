#!/usr/bin/env bash
# Demo: launch FocusFlow with auto-approve (mocks for unpaid integrations)
set -euo pipefail
cd "$(dirname "$0")/.."

export AUTOCORP_DATA_DIR="${AUTOCORP_DATA_DIR:-./data}"
export AUTOCORP_DB_PATH="${AUTOCORP_DB_PATH:-./data/autocorp.db}"

echo "==> AutoCorp demo launch: FocusFlow"
autocorp launch "FocusFlow" \
  --budget 450 \
  --desc "AI Pomodoro + deep work tracker for freelancers" \
  --stack "Next.js + Supabase + Stripe + Vercel" \
  --tone "clean, professional" \
  --cycles 3 \
  --auto-approve \
  --yes

echo ""
echo "==> Status"
autocorp status focusflow

echo ""
echo "==> P&L"
autocorp pnl focusflow
