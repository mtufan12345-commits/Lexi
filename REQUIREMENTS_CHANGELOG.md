# Requirements.txt Changelog

## Changes Made (October 2025)

### ✅ Fixed Issues:

1. **Removed Duplicates:**
   - `mailersend` was listed 3 times (lines 9, 26, 29)
   - `docx` was unnecessary (we use `python-docx`)
   - Kept only: `mailersend==2.0.0`

2. **Pinned All Versions:**
   - `google-genai` → `google-genai==1.41.0`
   - `pypdf2` → `pypdf==6.1.1` (upgraded to pypdf)
   - `markitdown` → `markitdown==0.0.2`
   - `pdf2image` → `pdf2image==1.17.0`
   - `Pillow` → `Pillow==11.3.0`
   - `pytesseract` → `pytesseract==0.3.13`
   - `Flask-Limiter` → `Flask-Limiter==4.0.0`
   - `flask-compress` → `flask-compress==1.18`
   - `requests` → `requests==2.32.5`

3. **Organized by Category:**
   - Web Framework
   - Database
   - Google Cloud & Vertex AI
   - Payments & Email
   - Object Storage
   - Security & Authentication
   - File Processing
   - Utilities

### 📊 Package Count:
- **Before:** 30 lines (with duplicates)
- **After:** 27 packages (clean, organized)

### 🎯 Benefits:

✅ **Reproducible builds** - Exact same versions in dev, staging, production
✅ **Security** - Pin versions to prevent unexpected updates with vulnerabilities
✅ **Stability** - No breaking changes from automatic upgrades
✅ **Audit trail** - Know exactly what versions are deployed

### ⚠️ Maintenance:

Update dependencies periodically:
```bash
# Check for security updates
python3 -m pip list --outdated

# Update specific package
pip install package-name==new-version

# Test thoroughly before deploying!
```

### 📝 Notes:

- **PyPDF2 → pypdf:** Modern package name (PyPDF2 is legacy)
- **google-genai 1.41.0:** Latest version with Vertex AI RAG support
- **Python 3.11.13:** Current Replit environment version

