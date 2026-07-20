#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/data/.openclaw/workspace"
VAULT="$WORKSPACE/clients/hoverboard_store/obsidian_vault/Hoverboard Store Content System"
REPO="git@github.com:harirajbhattarai/hbs-content-system.git"
KEY="$HOME/.ssh/hbs_content_system_github"

echo "Syncing HBS Obsidian vault to GitHub..."
echo ""

cd "$WORKSPACE"

echo "1. Exporting latest Obsidian vault..."
python3 tools/obsidian/export_hoverboard_vault.py

echo ""
echo "2. Opening vault repo..."
cd "$VAULT"

cat > .gitignore <<'EOF'
.obsidian/
.DS_Store
*.env
*.json
*.key
*.pem
*gsc-token*
*gsc-oauth*
*secret*
*credential*
EOF

if [ ! -d ".git" ]; then
  echo "Git repo not found. Initialising..."
  git init
  git branch -M main
fi

git config user.name "HBS Content Bot"
git config user.email "hbs-content-system@users.noreply.github.com"

git remote remove origin 2>/dev/null || true
git remote add origin "$REPO"

echo ""
echo "3. Checking changes..."
git add .

if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi

echo ""
echo "4. Committing changes..."
git commit -m "Update HBS content system vault"

echo ""
echo "5. Pushing to GitHub..."
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes" git push -u origin main

echo ""
echo "Done. HBS vault pushed to GitHub."
