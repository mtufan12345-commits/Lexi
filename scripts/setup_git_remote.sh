#!/bin/bash
# Git Remote Setup Script
# Run this once to configure GitHub remote with Personal Access Token

echo "🔧 Git Remote Setup voor Lexi CAO Meester"
echo "=========================================="
echo ""

# Check if git is configured
if ! git config user.email > /dev/null 2>&1; then
    echo "📝 Configureer git gebruiker..."
    git config --global user.email "autopush@lexi-ai.nl"
    git config --global user.name "Lexi Autopush"
    echo "✅ Git gebruiker geconfigureerd"
fi

# Prompt for GitHub details
echo ""
echo "Voer je GitHub details in:"
echo ""
read -p "GitHub username: " GITHUB_USER
read -p "Repository naam: " REPO_NAME
read -sp "Personal Access Token (PAT): " GITHUB_TOKEN
echo ""
echo ""

# Construct remote URL
REMOTE_URL="https://${GITHUB_TOKEN}@github.com/${GITHUB_USER}/${REPO_NAME}.git"

# Remove old origin if exists
if git remote | grep -q "^origin$"; then
    echo "🗑️  Verwijder oude origin remote..."
    git remote remove origin
fi

# Add new origin
echo "➕ Voeg GitHub remote toe..."
git remote add origin "$REMOTE_URL"

# Set upstream
echo "🔗 Configureer upstream branch..."
git branch -M main
git push -u origin main

echo ""
echo "✅ Git remote succesvol geconfigureerd!"
echo ""
echo "Test de verbinding met: git push origin main"
