# GitHub Secrets Setup - Quick Guide

⚠️ **DO THIS FIRST** before auto-deployment will work!

## Step 1: Go to GitHub Secrets

Navigate to:
```
https://github.com/YOUR-USERNAME/lexi/settings/secrets/actions
```

Or: Repository → Settings → Secrets and variables → Actions → New repository secret

## Step 2: Add 3 Secrets

### Secret 1: SSH_HOST
**Name:** `SSH_HOST`
**Value:**
```
188.34.158.27
```

---

### Secret 2: SSH_USER
**Name:** `SSH_USER`
**Value:**
```
root
```

---

### Secret 3: SSH_PRIVATE_KEY
**Name:** `SSH_PRIVATE_KEY`
**Value:** (Copy everything below, including BEGIN and END lines)
```
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBgrY5/AHkiXxtVPHKasZZpfcna4pFRHCXaPiQ2M3ZPZwAAAJif8KZ5n/Cm
eQAAAAtzc2gtZWQyNTUxOQAAACBgrY5/AHkiXxtVPHKasZZpfcna4pFRHCXaPiQ2M3ZPZw
AAAEBSM1ihSDhi3ln41e2YhS2at+KniqSV17I12dUA4Lkvb2Ctjn8AeSJfG1U8cpqxlml9
ydrikVEcJdo+JDYzdk9nAAAADmdpdGh1Yi1hY3Rpb25zAQIDBAUGBw==
-----END OPENSSH PRIVATE KEY-----
```

## Step 3: Test Deployment

After adding all 3 secrets, test with:

```bash
# Create test commit
echo "Test: $(date)" > test.txt
git add test.txt
git commit -m "Test: GitHub Actions deployment"
git push origin main
```

Then watch the deployment at:
```
https://github.com/YOUR-USERNAME/lexi/actions
```

## Verification Checklist

- [ ] SSH_HOST secret added (188.34.158.27)
- [ ] SSH_USER secret added (root)
- [ ] SSH_PRIVATE_KEY secret added (full key with BEGIN/END lines)
- [ ] Test commit pushed to main branch
- [ ] Workflow runs successfully in Actions tab
- [ ] Production site updated (check https://lexiai.nl/health)

## What Happens When You Push to Main?

1. ✅ GitHub Actions detects push
2. ✅ Connects to 188.34.158.27 via SSH
3. ✅ Runs `git pull origin main`
4. ✅ Runs `npm run build:css` (Tailwind)
5. ✅ Runs `systemctl restart lexi`
6. ✅ Reports success ✨

**Total time: ~30-60 seconds**

## Troubleshooting

**If workflow fails with "Permission denied":**
- Verify SSH_PRIVATE_KEY includes BEGIN and END lines
- Check for extra spaces or newlines
- Ensure you copied the entire key

**If workflow fails at "npm run build:css":**
- SSH into server: `ssh root@188.34.158.27`
- Check npm: `npm --version`
- Install if needed: `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && apt-get install -y nodejs`

**Need help?**
- Check workflow logs: GitHub repo → Actions → Click failed run
- Check server logs: `journalctl -u lexi -n 50`

---

**Once configured, every git push to main automatically deploys to production!**
