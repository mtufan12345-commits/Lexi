# 🔄 Git Autopush - Automatische Backup Setup

Deze folder bevat scripts voor automatische git backup elke 5 minuten via Replit Scheduled Deployment.

## 📁 Bestanden

- `setup_git_remote.sh` - Eenmalige setup voor GitHub remote met PAT
- `git_autopush.sh` - Hoofdscript voor git sync (pull → commit → push)
- `run_git_autopush.py` - Python wrapper met logging (entry point voor scheduled deployment)

## 🚀 Setup Instructies

### Stap 1: GitHub Personal Access Token (PAT) Aanmaken

1. Ga naar GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Klik **"Generate new token (classic)"**
3. Geef token een naam: `Lexi Replit Autopush`
4. Selecteer scopes:
   - ✅ `repo` (alle sub-opties)
5. Klik **"Generate token"**
6. **Kopieer de token** (je kunt deze maar 1x zien!)

### Stap 2: Git Remote Configureren

Run het setup script:

```bash
bash scripts/setup_git_remote.sh
```

Het script vraagt om:
- GitHub username (bijv. `jouwusername`)
- Repository naam (bijv. `lexi-cao-meester`)
- Personal Access Token (plak de PAT die je zojuist hebt gemaakt)

### Stap 3: Scheduled Deployment Activeren

**BELANGRIJK:** De deployment configuratie is al klaar! Je hoeft alleen nog te deployen:

1. **Klik op "Deploy" knop** (rechtsboven in Replit)
2. **Selecteer "Scheduled"** deployment type
3. **Configureer de schedule:**
   - **Schedule:** `*/5 * * * *` (elke 5 minuten)
   - Of gebruik natural language: `Every 5 minutes`
   - **Job timeout:** `120` seconden
4. **De run/build commands zijn al geconfigureerd** - laat deze zoals ze zijn
5. **Klik "Deploy"**

## ✅ Verificatie

Na deployment:

1. Wacht 5 minuten
2. Ga naar je GitHub repository
3. Check of er nieuwe commits zijn met message: `autopush: YYYY-MM-DD HH:MM:SS from Replit`

## 📊 Logs Bekijken

- Ga naar **Deployments** tab in Replit
- Klik op je scheduled deployment
- Bekijk **Logs** voor elke run

## ⚙️ Werking

**Elke 5 minuten:**
1. 📥 Pull laatste wijzigingen van GitHub
2. 📝 Check voor lokale wijzigingen
3. ✍️ Commit wijzigingen (als die er zijn)
4. 🚀 Push naar GitHub

**Veilig door:**
- ✅ Draait los van web app (geen interference)
- ✅ Error handling (crasht niet bij conflicts)
- ✅ Skip als geen wijzigingen
- ✅ Credentials veilig opgeslagen via GitHub PAT

## 🛠️ Handmatig Testen

Test de autopush voordat je scheduled deployment activeert:

```bash
python3 scripts/run_git_autopush.py
```

Verwachte output:
```
============================================================
Git Autopush Started: 2025-10-16 15:30:00
============================================================

🔄 Starting git autopush at Wed Oct 16 15:30:00 UTC 2025
📥 Pulling latest changes...
📝 Adding changes...
🚀 Pushing to remote...
✅ Git autopush completed successfully at Wed Oct 16 15:30:05 UTC 2025

============================================================
✅ Git Autopush Completed Successfully
============================================================
```

## ❓ Troubleshooting

**Push fails met authentication error:**
- Check of PAT nog geldig is
- Verifieer dat PAT `repo` scope heeft
- Run `bash scripts/setup_git_remote.sh` opnieuw

**Merge conflicts:**
- Script detecteert dit en skipped automatisch
- Los conflicts handmatig op in Replit
- Volgende run zal automatisch doorgang

**Scheduled deployment draait niet:**
- Check of deployment status "Active" is
- Verifieer cron schedule: `*/5 * * * *`
- Bekijk deployment logs voor errors

## 🔐 Beveiliging

- PAT wordt veilig opgeslagen in git remote URL (lokaal)
- Token is **niet zichtbaar** in logs of code
- Gebruik alleen in development/staging environment
- Voor production: gebruik GitHub Actions of GitLab CI
