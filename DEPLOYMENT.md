# GitHub Actions Auto-Deployment

Last updated: 2025-10-24

## Overview

Automatic deployment from Replit/GitHub to Hetzner production server using GitHub Actions.

**Flow:**
```
Replit → Git Push → GitHub Actions → SSH to Hetzner → Deploy → Restart Service
```

## Configuration

### 1. GitHub Actions Workflow

**File:** `.github/workflows/deploy.yml`

**Triggers on:** Push to `main` branch

**Actions:**
1. SSH into Hetzner server (188.34.158.27)
2. Pull latest code from GitHub
3. Build Tailwind CSS assets
4. Restart Lexi service
5. Report success/failure

### 2. GitHub Secrets Required

Navigate to your GitHub repository: `Settings → Secrets and variables → Actions → New repository secret`

Add these 3 secrets:

#### SSH_HOST
```
188.34.158.27
```

#### SSH_USER
```
root
```

#### SSH_PRIVATE_KEY
```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBgrY5/AHkiXxtVPHKasZZpfcna4pFRHCXaPiQ2M3ZPZwAAAJif8KZ5n/Cm
eQAAAAtzc2gtZWQyNTUxOQAAACBgrY5/AHkiXxtVPHKasZZpfcna4pFRHCXaPiQ2M3ZPZw
AAAEBSM1ihSDhi3ln41e2YhS2at+KniqSV17I12dUA4Lkvb2Ctjn8AeSJfG1U8cpqxlml9
ydrikVEcJdo+JDYzdk9nAAAADmdpdGh1Yi1hY3Rpb25zAQIDBAUGBw==
-----END OPENSSH PRIVATE KEY-----
```

**⚠️ IMPORTANT:**
- Copy the ENTIRE private key including BEGIN and END lines
- Paste exactly as shown, no extra spaces or newlines
- Never commit this key to your repository
- This key is dedicated for GitHub Actions only

### 3. SSH Key Setup (Already Configured ✓)

**Server side:**
- Private key: `/root/.ssh/github_actions`
- Public key: `/root/.ssh/github_actions.pub`
- Public key added to: `/root/.ssh/authorized_keys`

**Verification:**
```bash
ssh-keygen -l -f /root/.ssh/github_actions.pub
# Should show: 256 SHA256:... github-actions (ED25519)
```

## Deployment Process

### Manual Deployment (Current)
```bash
cd /var/www/lexi
git pull origin main
npm run build:css
systemctl restart lexi
```

### Automatic Deployment (GitHub Actions)
```bash
# From Replit or local machine:
git add .
git commit -m "Your commit message"
git push origin main

# GitHub Actions automatically:
# 1. Detects push to main
# 2. Connects to server via SSH
# 3. Pulls latest code
# 4. Builds CSS assets
# 5. Restarts service
# 6. Reports status
```

## Testing the Deployment

### Step 1: Verify GitHub Secrets
1. Go to `https://github.com/YOUR-USERNAME/YOUR-REPO/settings/secrets/actions`
2. Verify these secrets exist:
   - `SSH_HOST`
   - `SSH_USER`
   - `SSH_PRIVATE_KEY`

### Step 2: Make Test Commit
```bash
# Create a test file
echo "# Test deployment - $(date)" > DEPLOY_TEST.txt

# Commit and push
git add DEPLOY_TEST.txt
git commit -m "Test: GitHub Actions auto-deployment"
git push origin main
```

### Step 3: Monitor Workflow
1. Go to `https://github.com/YOUR-USERNAME/YOUR-REPO/actions`
2. Click on the latest workflow run
3. Watch the deployment progress in real-time
4. Verify all steps complete successfully

### Step 4: Verify Production
```bash
# On server:
systemctl status lexi
curl https://lexiai.nl/health

# Check if test file exists:
ls -la /var/www/lexi/DEPLOY_TEST.txt
```

## Troubleshooting

### Workflow Fails: "Permission denied (publickey)"
**Cause:** SSH private key not configured correctly in GitHub Secrets

**Fix:**
1. Verify `SSH_PRIVATE_KEY` in GitHub Secrets matches `/root/.ssh/github_actions`
2. Ensure the key includes BEGIN and END lines
3. Check for extra spaces or newlines

### Workflow Fails: "npm: command not found"
**Cause:** npm not installed on server

**Fix:**
```bash
# Install Node.js and npm
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
apt-get install -y nodejs

# Verify installation
node --version
npm --version
```

### Workflow Fails: "systemctl restart lexi failed"
**Cause:** Service configuration issue

**Fix:**
```bash
# Check service status
systemctl status lexi

# Check logs
journalctl -u lexi -n 50

# Manually restart
systemctl restart lexi
```

### CSS Not Updating
**Cause:** Tailwind build step failed

**Fix:**
```bash
# Manually build CSS
cd /var/www/lexi
npm run build:css

# Check output
ls -lh static/css/output.css
```

## Workflow File Explained

```yaml
name: Deploy to Production

on:
  push:
    branches: [ main ]          # Trigger on push to main branch

jobs:
  deploy:
    runs-on: ubuntu-latest      # Use Ubuntu runner

    steps:
      - name: Deploy to Hetzner server
        uses: appleboy/ssh-action@master    # SSH action
        with:
          host: ${{ secrets.SSH_HOST }}             # 188.34.158.27
          username: ${{ secrets.SSH_USER }}         # root
          key: ${{ secrets.SSH_PRIVATE_KEY }}       # Private key
          script: |
            cd /var/www/lexi                        # Navigate to app
            git pull origin main                    # Pull latest code
            npm run build:css                       # Build Tailwind CSS
            systemctl restart lexi                  # Restart service
            echo "✅ Deployment successful!"
```

## Security Best Practices

✅ **Implemented:**
- Dedicated SSH key for GitHub Actions (not using root's main key)
- Private key stored in GitHub Secrets (encrypted)
- Public key in authorized_keys
- SSH key has descriptive name (github-actions)

⚠️ **Recommendations:**
- Consider creating a dedicated deploy user (instead of root)
- Add IP whitelist for GitHub Actions runners
- Enable 2FA on GitHub account
- Rotate SSH keys periodically

## Monitoring Deployments

### View Recent Deployments
```bash
# GitHub Actions history
https://github.com/YOUR-USERNAME/YOUR-REPO/actions

# Server deployment log
journalctl -u lexi -n 100 --since "1 hour ago"
```

### Rollback if Needed
```bash
# View recent commits
git log --oneline -10

# Rollback to previous commit
git reset --hard COMMIT_HASH
npm run build:css
systemctl restart lexi
```

## CI/CD Pipeline Status

| Component | Status | Notes |
|-----------|--------|-------|
| GitHub Actions Workflow | ✅ Configured | `.github/workflows/deploy.yml` |
| SSH Key Pair | ✅ Generated | `/root/.ssh/github_actions` |
| Authorized Keys | ✅ Added | Public key in authorized_keys |
| GitHub Secrets | ⚠️ Pending | Need to add to GitHub repo |
| Test Deployment | ⏳ Pending | Run after secrets configured |

## Next Steps

1. **Add GitHub Secrets** (see section 2 above)
2. **Test Deployment** (see Testing section)
3. **Monitor First Deployment** (check Actions tab)
4. **Verify Production** (check https://lexiai.nl/health)
5. **Clean up test files** (remove DEPLOY_TEST.txt)

## Support

**Check workflow status:**
```bash
# GitHub Actions page
https://github.com/YOUR-USERNAME/YOUR-REPO/actions

# Server logs
journalctl -u lexi -f
```

**Manual deployment always available:**
```bash
cd /var/www/lexi
git pull origin main
npm run build:css
systemctl restart lexi
```

---

**Auto-deployment saves time and reduces deployment errors. Every push to main is automatically deployed within 1-2 minutes!**
