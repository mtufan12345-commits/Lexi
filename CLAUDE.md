# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# LEXI CAO MEESTER - Architecture Overview

**Build Context**: This is a comprehensive B2B SaaS platform for Dutch staffing agencies, providing AI-powered support for labor law (CAO/collective agreement) questions. Last updated: October 2025.

---

## DEVELOPMENT COMMANDS

### Running the Application

**Development (Replit):**
```bash
# Run with Flask dev server
python main.py

# Run with Gunicorn (production-like)
gunicorn --config gunicorn.conf.py main:app
```

**Production (Systemd):**
```bash
# Check status
systemctl status lexi
lexi-status              # Quick health check
lexi-status full         # Comprehensive status

# Manage service
systemctl restart lexi
systemctl stop lexi
systemctl start lexi

# View logs
journalctl -u lexi -f                      # Live logs
journalctl -u lexi -n 100                  # Last 100 lines
journalctl -u lexi --since "1 hour ago"    # Recent logs
```

### Database Operations

```bash
# Initialize database (creates all tables)
python -c "from main import app, init_db; init_db()"

# Test database connection
python3.11 -c "from dotenv import load_dotenv; load_dotenv(); from main import app; from models import db; app.app_context().__enter__(); db.session.execute(db.text('SELECT 1')); print('DB OK')"

# Database is PostgreSQL (Neon.tech in production)
# Connection string in DATABASE_URL env var
```

### Testing Key Services

```bash
# Test S3 service
python3.11 << 'EOF'
from dotenv import load_dotenv; load_dotenv()
from services import s3_service
print('S3 Enabled:', s3_service.enabled)
EOF

# Test Vertex AI service
python3.11 << 'EOF'
from dotenv import load_dotenv; load_dotenv()
from services import vertex_ai_service
print('Vertex AI Enabled:', vertex_ai_service.enabled)
EOF

# Test health endpoint
curl http://localhost:5000/health | python3.11 -m json.tool
```

### Deployment

```bash
# Pull latest code and deploy
cd /var/www/lexi
git pull origin main

# Install/update dependencies
pip install -r requirements.txt
npm install                    # If package.json changed
npm run build:css             # Rebuild Tailwind CSS

# Restart service
systemctl restart lexi

# Use automated deploy script (production)
./deploy.sh
```

### Frontend Development

```bash
# Install dependencies
npm install

# Build Tailwind CSS
npm run build:css

# Watch mode (auto-rebuild on changes)
npm run watch:css
```

### Troubleshooting

```bash
# Check if port 5000 is in use
lsof -i :5000

# Check gunicorn workers
ps aux | grep gunicorn

# Check memory usage
free -h

# Check disk usage
df -h
du -h /var/www/lexi | sort -rh | head -20

# Clean journal logs if disk full
journalctl --vacuum-size=100M
```

---

## CRITICAL PATTERNS FOR DEVELOPMENT

### Multi-Tenancy: ALL queries MUST filter by tenant_id
```python
# ❌ WRONG - Security vulnerability, leaks data between tenants
user = User.query.filter_by(id=user_id).first()

# ✅ CORRECT - Always include tenant_id
user = User.query.filter_by(id=user_id, tenant_id=g.tenant.id).first()
```

### Vertex AI Service: MUST use Singleton Pattern
- **Never** create new `genai.Client()` instances directly
- Use `vertex_ai_service` singleton from `services.py`
- Worker crashes occur from multiple client initializations
- `preload_app=True` in gunicorn.conf.py is critical

### Message Storage: Hybrid S3 + Database
- Messages stored in S3 at: `chats/tenant_{id}/chat_{id}_messages.json`
- Chat.s3_messages_key points to S3 JSON file
- Legacy Message table exists but deprecated
- Always update Chat.message_count when adding messages

### CAO-Aware System Instructions
- System instruction MUST be generated per-request based on `tenant.cao_preference`
- Use `cao_config.get_system_instruction(tenant.cao_preference)`
- Never hardcode system instructions
- NBBU vs ABU CAOs cannot be mixed (conflicting Dutch labor law rules)

### File Uploads: OCR Fallback Pattern
```python
# 1. Try MarkItDown for PDFs
# 2. If empty/scanned PDF, fallback to pytesseract OCR (lang='nld+eng')
# 3. Cache extracted_text in UploadedFile.extracted_text (database)
# 4. Upload original file to S3 with UUID prefix
```

### Decorator Stack Order (Always use in this order)
```python
@app.route('/path')
@login_required        # 1. Check authentication
@tenant_required       # 2. Load tenant (g.tenant)
@admin_required        # 3. Check role (if needed)
def handler():
    # Now safe to access: current_user, g.tenant, role
    pass
```

### Environment Variables Hierarchy
```python
# Production keys take precedence:
STRIPE_SECRET_KEY_PROD > STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET_PROD > STRIPE_WEBHOOK_SECRET

# Critical required vars (app won't start without these):
SESSION_SECRET         # Must be 32+ chars
DATABASE_URL          # PostgreSQL connection
GOOGLE_APPLICATION_CREDENTIALS  # Vertex AI auth
```

### Cache Busting
- BUILD_VERSION is appended to all static files (CSS/JS)
- In production: BUILD_VERSION = git commit hash
- In development: BUILD_VERSION = timestamp
- Always use `{{ url_for('static', filename='...')}}?v={{ build_version }}` in templates

---

## 1. OVERALL APPLICATION ARCHITECTURE

### Technology Stack
- **Backend**: Flask 3.0.0 (Python 3.11.13)
- **Database**: PostgreSQL 2.9.9 (via SQLAlchemy 2.0.23)
- **Web Server**: Gunicorn 21.2.0 with worker pool
- **Frontend**: Jinja2 templates with Tailwind CSS + HTMX
- **LLM/AI**: Google Vertex AI (Gemini 2.5 Pro) via google-genai SDK
- **Storage**: S3-compatible object storage (MinIO/AWS S3)
- **Payment**: Stripe (via HTTP API + SDK)
- **Email**: MailerSend HTTP API
- **Security**: Flask-Login, Flask-WTF (CSRF), bcrypt password hashing

### Deployment Architecture
- **Hosting**: Replit (development) / Production deployment ready
- **Environment**: Multi-tenant SaaS with subdomain-based isolation
- **Port**: Gunicorn workers on port 8080 (nginx proxy frontend)
- **Session**: Flask session with 8-hour timeout, secure cookies
- **Build System**: Version caching via BUILD_VERSION (git hash in prod, timestamp in dev)

### Core Design Pattern: Request Pipeline
```
Request → Host Header Validation → Tenant Loading (via subdomain/session) → 
Authentication Check → Decorator Stack (@login_required, @tenant_required, @admin_required) → 
Route Handler → Database Operation / External Service Call → JSON Response
```

---

## 2. DATABASE ARCHITECTURE & MULTI-TENANCY

### Multi-Tenancy Strategy: Full Tenant Isolation
The application implements **strict per-tenant data isolation**:

- **Tenant Identification Method**: 
  - Production: Extract subdomain from Host header (e.g., `companyx.lex-cao.app`)
  - Development: Store tenant_id in Flask session
  - Host header validation prevents header injection attacks (validate_host_header middleware)

- **Data Isolation Pattern**: Every data model includes `tenant_id` foreign key
  - All queries filter by `tenant_id` at application level (no database row-level security)
  - Example: `Chat.query.filter_by(tenant_id=g.tenant.id, user_id=current_user.id)`

### Database Schema (PostgreSQL)

**Core Entity Models:**
```
SuperAdmin (platform admins, separate from tenant admins)
  ├── id, email, password_hash, name, created_at

Tenant (company accounts, primary isolation unit)
  ├── id, company_name, subdomain (unique), contact_email, contact_name
  ├── status (active/suspended/archived)
  ├── subscription_tier (starter/professional/enterprise)
  ├── subscription_status (active/trial/trialing/cancelled)
  ├── max_users (per tier: starter=5, professional=20, enterprise=unlimited)
  ├── cao_preference (NBBU/ABU - for Dutch labor law context)
  ├── custom_branding_enabled, api_access_enabled (feature flags)
  └── trial_ends_at, created_at, updated_at

User (tenant members)
  ├── id, tenant_id, email (unique per tenant), password_hash
  ├── first_name, last_name, role (admin/user), is_active
  ├── disclaimer_accepted_at, first_chat_warning_seen_at
  ├── reset_token (for password resets), reset_token_expires_at
  └── avatar_url, session_token, created_at
  └── CONSTRAINT: unique(tenant_id, email)

Chat (conversation sessions)
  ├── id, tenant_id, user_id
  ├── title (auto-generated from first message)
  ├── s3_messages_key (pointer to S3 JSON file with all messages)
  ├── message_count (total user + assistant messages)
  └── created_at, updated_at

Message (legacy schema - mostly migrated to S3)
  ├── id, tenant_id, chat_id
  ├── role (user/assistant), content, created_at
  ├── feedback_rating (1-5), feedback_comment
  └── NOTE: Largely deprecated in favor of S3 storage

Subscription (Stripe integration)
  ├── id, tenant_id, plan, status
  ├── stripe_customer_id, stripe_subscription_id
  ├── payment_method (card/ideal/sepa_debit)
  ├── current_period_start, current_period_end, created_at

UploadedFile (user documents in chat)
  ├── id, tenant_id, user_id, chat_id
  ├── filename, original_filename, s3_key
  ├── file_size, mime_type (pdf/docx/txt)
  ├── extracted_text (OCR results cached in DB)
  └── created_at

Artifact (AI-generated documents)
  ├── id, tenant_id, chat_id, message_id
  ├── title, content, artifact_type (document), s3_key
  └── created_at

Template (admin-created response templates)
  ├── id, tenant_id, name, category, content, s3_key
  └── created_at, updated_at

SupportTicket (customer support)
  ├── id, ticket_number (unique, auto-increment), tenant_id, user_id
  ├── user_email, user_name, subject, category
  ├── status (open/in_progress/answered/closed)
  ├── created_at, updated_at, closed_at

SupportReply (ticket responses)
  ├── id, ticket_id, message, is_admin, sender_name, created_at

PendingSignup (temporary during Stripe checkout)
  ├── id, checkout_session_id (unique), email, company_name
  ├── contact_name, password_hash, tier, billing, cao_preference
  ├── created_at (cleaned up after 24 hours)
```

### Message Storage Strategy: Hybrid S3 + Database
- **User/Assistant Messages**: Stored in S3 as JSON files (path: `chats/tenant_{id}/chat_{id}_messages.json`)
- **Metadata**: Chat record references S3 key via `s3_messages_key` column
- **Message Count**: Tracked in Chat.message_count for quick access
- **Fallback**: Legacy Message table still queried if no S3 key present
- **Artifacts**: Generated documents stored in S3 (`artifacts/tenant_{id}/{uuid}_{title}.txt`)

### Session Management
- Flask session stores: `tenant_id`, `user_id`, `is_super_admin`, `impersonating_*` state
- Session cookie: Secure (HTTPS only), HttpOnly, SameSite=Lax, 8-hour timeout
- Super admin impersonation: Allows super admin to test as tenant admin without password

---

## 3. AUTHENTICATION & USER MANAGEMENT

### Authentication Flow

**Signup Flow (Tenant Creation):**
1. User fills signup form with company name, email, password, tier, billing cycle, CAO preference
2. Form validates inputs and calls Stripe HTTP API directly to create checkout session
3. PendingSignup record created server-side with hashed password (idempotent via checkout_session_id)
4. Redirect to Stripe Checkout (iframe-safe redirect to escape Replit preview)
5. **On Payment Success**: Stripe webhook → provision_tenant_from_signup()
6. **Fallback Path**: If webhook delays, signup_success endpoint polls for webhook completion (max 15 retries, 1s delay), then calls fallback provisioning
7. Auto-login newly created admin user

**Login Flow:**
- User logs in with email + password → checks User table
- Password verified with bcrypt.check_password_hash()
- Flask-Login session created, tenant_id stored in session
- current_user accessed via login_manager.user_loader callback

**Password Reset (Token-Based):**
- User requests reset → generate secrets.token_urlsafe(32) reset token
- Store in User.reset_token with 1-hour expiration
- Send secure link via email (NO password in email)
- Token verified on reset page before allowing new password

**Super Admin Access:**
- Separate SuperAdmin table for platform administrators
- session['is_super_admin'] flag separates super admin flow
- Can impersonate tenant admins for testing (session state preserved for return)

### Authorization Model

**Tenant Level:**
- `@tenant_required` decorator: Ensures g.tenant is loaded, returns 404 if missing
- All tenant-scoped routes verify tenant ownership via tenant_id filter

**User Role-Based:**
- `admin` role: Full tenant management (users, billing, templates, support)
- `user` role: Can only create chats, upload files, view own data

**Admin-Only Routes:**
- `/admin/*` - Tenant admin dashboard (users, templates, billing, support)
- Enforced via `@admin_required` decorator (checks current_user.role == 'admin')

**Super Admin Routes:**
- `/super-admin/*` - Platform management (tenants, analytics, impersonation, support)
- Enforced via `@super_admin_required` decorator (checks session['is_super_admin'])

### User Invitation System
- Admin creates new user: POST `/admin/users/create`
- Generates activation token (one-time use, 24h expiration)
- Sends invitation email with secure activation link (NO password)
- User activates account and sets own password via activation URL

---

## 4. AI/LLM INTEGRATION ARCHITECTURE

### Google Vertex AI Service (Singleton Pattern)

**Initialization (services.py):**
```python
class VertexAIService:
    _instance = None  # Singleton pattern
    _lock = threading.Lock()  # Thread-safe initialization
    
    def __init__(self):
        # Load credentials from GOOGLE_APPLICATION_CREDENTIALS env var
        # Can be JSON string (parsed to temp file) or file path
        # Initialize google-genai Client with project + location
        # Model: "gemini-2.5-pro"
        # RAG corpus: VERTEX_AI_AGENT_ID (knowledge base endpoint)
```

**Why Singleton?**
- Gunicorn spawns multiple worker processes
- Creating new genai.Client per request = crashes ("_api_client AttributeError")
- Singleton ensures single client instance per worker process
- Thread-safe double-check locking prevents race conditions

**Chat Flow:**
```
send_message(chat_id) 
  → Load conversation history from S3 JSON
  → Collect uploaded files + extract text (PDFs via MarkItDown + OCR fallback)
  → Build system instruction from cao_config.get_system_instruction()
  → Call vertex_ai_service.chat(message, conversation_history, system_instruction)
  → Stream response via client.models.generate_content_stream()
  → Parse artifacts from response (markdown code blocks with special syntax)
  → Save assistant message + artifacts to S3
```

**System Instruction (Dynamic, CAO-Aware):**
- Generated per-request in cao_config.py based on tenant.cao_preference (NBBU or ABU)
- Instructs AI to use chosen CAO + all other documents (excluding alternative CAO)
- Prevents AI from mixing conflicting labor law rules
- Fallback instruction if tenant has no preference: defaults to NBBU

**Vertex AI Capabilities Used:**
1. **Retrieval (RAG)**: VertexRagStore with corpus lookup (similarity_top_k=20)
2. **Extended Thinking**: thinking_config with thinking_budget=-1 (unlimited)
3. **Streaming**: generate_content_stream for chunked responses
4. **Multi-turn**: Conversation history passed as Content objects

**Response Parsing:**
- Extract plain text response from chunk.text
- Search for artifact patterns: `` `artifact:TYPE title:TITLE\ncontent` ``
- Types: 'document', 'contract', 'brief', etc.
- Create Artifact records + S3 uploads automatically

**Error Handling:**
- Credential validation on init (required fields check)
- Graceful degradation if Vertex AI unavailable (enabled=False)
- __del__ cleanup catches AttributeError from genai internals (critical for gunicorn)

---

## 5. BACKGROUND JOB PROCESSING & ASYNC TASK HANDLING

### Current Approach: Synchronous with Polling/Webhooks
The application does NOT use a background job queue (Celery/RQ). Instead:

**Email Sending (Blocking but Resilient):**
- EmailService.send_email() calls MailerSend HTTP API synchronously
- timeout=10s per request
- Failures logged but don't block user response
- TEST_EMAIL_OVERRIDE env var routes all emails to single address (testing)

**Stripe Webhook Handling:**
- Webhook endpoint: `/webhook/stripe` (POST, rate-limited 100/hour)
- Signature verification mandatory (Stripe-Signature header checked)
- Processing:
  - `checkout.session.completed`: Trigger tenant provisioning
  - `customer.subscription.updated`: Update subscription status
  - `invoice.payment_failed`: Send failure email
  - `invoice.finalized`: Send iDEAL payment links (manual invoices)

**Webhook to Live User Flow:**
1. Webhook processes checkout completion → creates Tenant + User + Subscription
2. User waiting on `/signup/success` endpoint polls database (max 15 retries)
3. Polling detects PendingSignup deletion (webhook success indicator)
4. User auto-logged in, redirected to `/chat`
5. If webhook doesn't fire: fallback provisioning validates with Stripe directly

**Periodic Tasks:**
- Cleanup stale pending signups: via `@app.before_request` middleware
  - Called on every request, deletes PendingSignup older than 24 hours
  - Prevents accumulation of incomplete signups

### Why No Celery/RQ?
- Simple use cases (email, webhook processing are I/O-bound, not CPU-intensive)
- Replit/small deployment constraints
- Synchronous approach acceptable for current scale
- Alternative: Could add background worker process if needed

---

## 6. PAYMENT & SUBSCRIPTION SYSTEM ARCHITECTURE

### Stripe Integration (Production/Test Keys)

**Configuration Hierarchy:**
```python
stripe.api_key = os.getenv('STRIPE_SECRET_KEY_PROD') or os.getenv('STRIPE_SECRET_KEY')
# Production keys always used if set, falls back to test keys
```

**Price Configuration (stripe_config.py):**
```python
STRIPE_PRICES = {
    'starter': {
        'monthly': 'price_1SGiKZD8m8yYEAVBSAdF32kZ',  # €499/month
        'yearly': 'price_1SGiM5D8m8yYEAVB0ynuVjvl'
    },
    'professional': {
        'monthly': 'price_1SGiNlD8m8yYEAVBVtUAS1f4',  # €599/month
        'yearly': 'price_1SGiOrD8m8yYEAVBoAzWBMO9'
    },
    'enterprise': {
        'monthly': 'price_1SGiPXD8m8yYEAVBMSOSV5Dz',  # €1,199/month
        'yearly': 'price_1SGiQGD8m8yYEAVBQCSMOClc'
    }
}
```

### Subscription Lifecycle

**Checkout Session Creation:**
- Route: `/signup/tenant` (POST)
- Method: Stripe HTTP API (not SDK) to avoid session ID parsing issues
- Payment methods: Card + iDEAL (ideal temporarily disabled pending SEPA setup)
- Metadata: signup_email, tier, billing, cao_preference (not stored on session)

**Subscription State Machine:**
```
PendingSignup (checkout initiated)
  ↓ (Stripe charges card)
checkout.session.completed (webhook)
  ↓ (provision_tenant_from_signup)
Tenant + User + Subscription created (status='active')
  ↓
customer.subscription.updated (webhook when status changes)
  ├─ active/trialing → subscription.status='active', tenant.status='active'
  ├─ past_due/unpaid → subscription.status='past_due'
  └─ canceled/incomplete_expired → subscription.status='canceled', tenant.status='inactive'
```

**Trial Period:**
- 14 days default (Tenant.trial_ends_at = utcnow() + 14 days)
- subscription_status = 'trial'
- Can be extended via super-admin dashboard

**Payment Methods:**
- Card (recurring)
- iDEAL (single-use, paid manually per invoice, via hosted_invoice_url)
- SEPA Direct Debit (planned, requires Stripe setup)
- Detection via payment_intent or subscription's default_payment_method

### Billing Portal
- Route: `/admin/billing`
- Shows current subscription status, plan, next billing date
- "Manage Billing" button redirects to Stripe Customer Portal
- StripeService.create_customer_portal_session(customer_id, return_url)

### Usage Monitoring
- Super admin dashboard: MRR (Monthly Recurring Revenue) calculated from active subscriptions
- ARR (Annual Recurring Revenue) = MRR × 12
- Growth tracking: MRR history last 12 months
- Tier breakdown: Count of active tenants per tier
- Conversion tracking: Trial → Active → Churned

---

## 7. FILE STORAGE ARCHITECTURE

### S3 Object Storage (MinIO/AWS S3 Compatible)

**Service: S3Service (Singleton)**
- Initialization: Create boto3 S3 client once per worker process
- Configuration: endpoint_url, bucket_name, access_key, secret_key from env
- Enabled flag: Returns false if any credential missing

**Storage Structure:**
```
{bucket}/
  ├─ chats/
  │   └─ tenant_{tenant_id}/
  │       └─ chat_{chat_id}_messages.json (all messages as JSON array)
  ├─ uploads/
  │   └─ tenant_{tenant_id}/
  │       └─ {uuid}_{filename} (uploaded PDFs, DOCs, TXTs)
  ├─ artifacts/
  │   └─ tenant_{tenant_id}/
  │       └─ {uuid}_{title}.txt (AI-generated documents)
  └─ templates/
      └─ tenant_{tenant_id}/
          └─ {uuid}_{name}.txt (admin templates)
```

### File Operations

**Upload Flow:**
1. File validation: whitelist extensions (pdf/docx/doc/txt), MIME type check
2. Extract text: 
   - PDFs: Try MarkItDown first, fallback to OCR (pytesseract on converted images)
   - DOCX: Extract paragraphs + tables via python-docx
   - TXT: Decode UTF-8 or Latin-1
3. Upload to S3 with unique filename: `{uuid}_{original_name}`
4. Create UploadedFile record with extracted_text cached in DB
5. Associate with chat_id (or NULL if pending)

**Message Context:**
- When sending message, load all chat-associated files
- Concatenate file content to user message for AI context
- Only newly uploaded files shown as "attachments" in UI
- Legacy files still used for AI context but not shown as new attachments

**Download Flow:**
- PDFs: Return S3 presigned URL (browser direct access, 1-hour expiration)
- Text/DOCX: Download content, extract text, return in JSON response
- Artifacts: Generate presigned URL, return in download response

**Export Flow:**
- PDF export: ReportLab generates styled document from all chat messages
- DOCX export: python-docx generates formatted document (Professional/Enterprise tiers only)
- Available for all subscription levels (PDF) or tier-restricted (DOCX)

### Text Extraction Strategy

**PDF Processing (Complex):**
```
MarkItDown.convert(pdf_path)
  ↓ (if successful and has text)
  return extracted_text
  ↓ (if empty, likely scanned PDF)
convert_from_path(pdf_path)  # PDF → images
  ↓
pytesseract.image_to_string(image, lang='nld+eng')  # Dutch + English OCR
  ↓
Return concatenated OCR text from all pages
```

**Error Handling:**
- Scanned PDF with no OCR text: "Kon PDF niet lezen (mogelijk scan of beveiligd)"
- Corrupted DOCX: "DOCX bevat geen leesbare tekst"
- Fallback to database extracted_text if S3 download fails (for legacy PDFs)

---

## 8. IMPORTANT PATTERNS & CONVENTIONS

### 1. Security Patterns

**HTTPS & Headers:**
- Force HTTPS in production (`@app.before_request` → force_https())
- Strict-Transport-Security header (1 year, preload ready)
- Content-Security-Policy: Inline scripts allowed (needed for app), Stripe iframe allowed
- X-Frame-Options: SAMEORIGIN (allow same-origin iframes)
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin

**Session Security:**
- Secure cookies (HTTPS only)
- HttpOnly (no JavaScript access)
- SameSite=Lax (compatible with Stripe redirects)
- 8-hour timeout
- Secret key: MUST be set via SESSION_SECRET env var (no fallback hardcoding)

**CSRF Protection:**
- Flask-WTF CSRF enabled by default
- Disable with ENABLE_CSRF=false env var (dev only)
- csrf_token() available in all templates

**Input Validation:**
- Filenames: secure_filename() + whitelist by extension + MIME type
- Host header: Validate against ALLOWED_HOSTS env var
- Stripe session IDs: Fetch from database server-side (not URL params)

**Rate Limiting:**
- Flask-Limiter per endpoint
- `/api/chat/{chat_id}/message`: 30 requests per minute
- `/webhook/stripe`: 100 requests per hour
- Memory-based storage (suitable for single/few workers)

**Webhook Security:**
- Stripe signature verification MANDATORY
- No bypasses allowed
- Webhook secret: STRIPE_WEBHOOK_SECRET or STRIPE_WEBHOOK_SECRET_PROD (prod first)
- Event type validation before processing

**Password Management:**
- bcrypt hashing (werkzeug.security)
- Never stored/transmitted in plaintext
- Reset tokens: 32-byte URL-safe tokens, 1-hour expiration, single-use
- Never send password in email (only reset link)

### 2. Data Access Patterns

**Tenant Isolation (Enforced Everywhere):**
```python
# WRONG (leaks data between tenants)
user = User.query.filter_by(id=user_id).first()

# CORRECT (multi-tenant safe)
user = User.query.filter_by(id=user_id, tenant_id=g.tenant.id).first()
```
- All queries include tenant_id filter
- g.tenant loaded in @app.before_request, available to all routes
- Decorator stack ensures g.tenant exists before accessing data

**S3 Fallback Pattern:**
```python
# Try database first (fast, cached extracted text)
if file.extracted_text:
    return file.extracted_text
# Fallback to S3 (for legacy files or if extraction failed)
else:
    return s3_service.download_file_content(file.s3_key, mime_type)
```

**Conversation History Assembly:**
```python
# Load all messages from S3 JSON file
messages = s3_service.get_chat_messages(chat.s3_messages_key)
# Build Content objects for Vertex AI
contents = [types.Content(role=msg['role'], parts=[types.Part.from_text(...)])]
```

### 3. Error Handling Patterns

**Graceful Degradation:**
```python
# If Vertex AI unavailable, still allow signup/login/file upload
if not vertex_ai_service.enabled:
    return "Lexi momenteel niet beschikbaar..."

# If S3 unavailable, functions return None/False
if not s3_service.enabled:
    return None
```

**Email Resilience:**
```python
# Email failures don't block operations
try:
    email_service.send_welcome_email(...)
except Exception as e:
    print(f"Email failed (non-blocking): {e}")
    # Continue - don't fail tenant provisioning
```

**Database Transaction Safety:**
```python
try:
    db.session.commit()
except Exception as e:
    db.session.rollback()
    raise  # OR return graceful error
```

### 4. Caching & Performance

**Static File Caching:**
- Cache-Control: public, max-age=31536000, immutable (1 year)
- BUILD_VERSION appended to JS/CSS in templates for cache busting
- Gzip compression enabled for text content (mimetypes list configured)

**Chat Message Caching:**
- Message count stored in Chat.message_count (avoids S3/DB count query)
- S3 JSON format: compact, quick full-reload from single object
- Message search: Load all messages once, filter in Python (not Stripe-level)

**Database Connection Pooling:**
- SQLAlchemy pool_recycle: 300 seconds (recycle long-lived connections)
- pool_pre_ping: True (ping connection before use to detect stale connections)

### 5. Naming & Code Conventions

**Route Pattern:**
- User routes: `/chat`, `/api/chat/{id}/message`, `/user/*`
- Admin routes: `/admin/*` (require admin role)
- Super admin routes: `/super-admin/*` (require super admin session)
- Public routes: `/`, `/login`, `/pricing`, `/signup/tenant`
- Webhook routes: `/webhook/*`

**Variable Naming:**
- `g.tenant`: Current tenant (Flask g object)
- `current_user`: Currently logged-in user (Flask-Login)
- `chat_id`, `message_id`, `artifact_id`: Path parameters
- `s3_key`: Full path in S3 bucket
- `tenant_id`: Foreign key reference

**Decorator Stack Order:**
```python
@app.route('/path')
@login_required  # Check user is authenticated
@tenant_required  # Check tenant is loaded
@admin_required  # Check user is admin (if needed)
def handler():
    # Guaranteed: current_user, g.tenant, role='admin'
```

**Dutch Language in Code:**
- Comments and error messages in Dutch (for Dutch users)
- Email templates in Dutch
- System instructions in Dutch
- DB comments reference CAO regulations
- Python code in English (convention)

### 6. Configuration Management

**Environment Variables Required:**
```
# Database
DATABASE_URL=postgresql://user:pass@host/db

# Session
SESSION_SECRET={32-char min, auto-generated}

# Stripe
STRIPE_SECRET_KEY={test key, optional}
STRIPE_SECRET_KEY_PROD={production key, used if set}
STRIPE_WEBHOOK_SECRET={test webhook}
STRIPE_WEBHOOK_SECRET_PROD={prod webhook, used if set}

# Google Cloud/Vertex AI
GOOGLE_APPLICATION_CREDENTIALS={JSON string or file path}
GOOGLE_CLOUD_PROJECT={gcp-project-id}
VERTEX_AI_LOCATION={region, e.g., 'europe-west1'}
VERTEX_AI_AGENT_ID={RAG corpus ID}

# Email
MAILERSEND_API_KEY={api key, optional}
FROM_EMAIL={sender, default trial domain}
FROM_NAME={sender name}
TEST_EMAIL_OVERRIDE={override all emails to this address, for testing}

# S3
S3_ENDPOINT_URL={e.g., http://localhost:9000}
S3_BUCKET_NAME={bucket}
S3_ACCESS_KEY={key}
S3_SECRET_KEY={secret}

# Deployment
ENVIRONMENT={production|development}
ALLOWED_HOSTS={comma-separated domains}
BUILD_VERSION={auto-set, git hash in prod}
ENABLE_CSRF={true|false, default true}
```

**Secrets Handling:**
- Never hardcode secrets (enforced via runtime error if SESSION_SECRET missing)
- Use separate env files per environment
- Production uses vault/secrets manager (external)
- Backup .env via .env.backup (for recovery, still excluded from git)

### 7. Testing & Debugging

**Debug Logging:**
- Extensive print() statements in send_message (33 debug points!)
- Tracks execution flow, S3 calls, Vertex AI invocation
- Disabled in production but useful for troubleshooting
- Example: `[DEBUG] 1. Starting file query for chat_id=...`

**Error Tracking:**
- Exception traceback printed with `traceback.print_exc()`
- Database rollback on commit failure
- Graceful user-facing error messages (English + Dutch)

---

## 9. SPECIFIC ARCHITECTURAL DECISIONS

### Why Hybrid Storage (S3 + Database)?
- **Pros**: Fast chat loading (load once from S3), unlimited message count, scalable
- **Cons**: Eventual consistency (webhook delays), two systems to manage
- **Rationale**: Support scale without hitting database row limits; decouple message count from user experience

### Why Singleton Pattern for External Services?
- **Problem**: Gunicorn workers crash when creating new genai.Client per request
- **Solution**: Single instance per worker, thread-safe initialization
- **Why not global variable**: Race conditions between workers during import-time initialization
- **Why not per-request singleton**: Each request is handled by one worker thread, but requests can overlap

### Why No Celery/Background Queue?
- **Current scale**: Startup phase, few concurrent users
- **Simplicity**: Fewer dependencies, easier debugging
- **Constraints**: Replit environment, no persistent job store
- **Decision**: When needed, can spawn gunicorn worker with scheduler or migrate to external queue

### Why CAO Preference in System Instruction?
- **Context**: Dutch labor law has two main staffing CAOs (NBBU vs ABU)
- **Problem**: Can't use both simultaneously (conflicting rules)
- **Solution**: Generate system instruction per request based on tenant.cao_preference
- **Why dynamic**: Different tenants use different CAOs, flexibility for future
- **Note**: AI still has access to all other documents (labor law, detaching rules)

### Why Server-Side Session Validation?
- **Problem**: Stripe checkout session ID could be tampered with in URL
- **Solution**: Fetch user email from PendingSignup record (server-side), not URL
- **Added security**: Verify checkout status directly with Stripe before creating account
- **Fallback**: If webhook doesn't fire, signup_success endpoint provisions account (idempotent)

---

## 10. DEPLOYMENT TOPOLOGY

### Development (Replit)
```
Replit Shell
  ↓
python main.py (Flask dev server OR gunicorn start)
  ↓
  ├─ PostgreSQL (local)
  ├─ MinIO S3 (local container)
  ├─ Stripe Test API
  └─ Vertex AI Test Project
```

### Production (Target)
```
Load Balancer (nginx)
  ↓
Gunicorn (8-worker pool, port 8080)
  ├─ Worker 1 (with VertexAIService singleton instance)
  ├─ Worker 2 (with separate singleton instance)
  └─ ... 8 workers total
  ↓
PostgreSQL (RDS/managed)
  ↓
S3 (AWS S3 or MinIO in production cluster)
  ↓
External Services:
  ├─ Google Vertex AI (API calls for LLM)
  ├─ Stripe (webhooks + payment processing)
  └─ MailerSend (email delivery)
```

### Subdomain Routing
```
Landing:     lex-cao.nl / www.lex-cao.nl (public signup, pricing)
Tenant A:    companya.lex-cao.nl (companya's isolated workspace)
Tenant B:    companyb.lex-cao.nl (companyb's isolated workspace)
Super Admin: admin.lex-cao.nl (optional, platform management)
```

---

## 11. KEY TRADE-OFFS & LIMITATIONS

| Aspect | Decision | Trade-off |
|--------|----------|-----------|
| Message Storage | S3 + DB | Complexity vs. scalability |
| Task Queue | None (sync) | Simplicity vs. async resilience |
| Auth | Session-based | Simplicity vs. API-first design |
| Tenant Isolation | App-level | Simplicity vs. DB-level RLS |
| File Extraction | OCR fallback | Performance vs. accuracy |
| Rate Limiting | In-memory | Simplicity vs. distributed deployment |
| Caching | None for data | Simplicity vs. performance |
| CORS | Not enabled | Frontend same-origin only |

---

## 12. FUTURE ARCHITECTURE CONSIDERATIONS

- **API-First Design**: Currently web-first, could expose REST API for integrations
- **Multi-Language Support**: Currently Dutch only, add i18n framework
- **Custom Branding**: Feature flag exists but not implemented
- **Rate Limiting Enhancements**: Move to Redis-backed for distributed deployment
- **Background Jobs**: Add Celery/RQ when async requirements grow
- **Database Sharding**: If tenant count scales, consider horizontal partitioning
- **CDN for Static Assets**: S3 + CloudFront for global content delivery
- **Observability**: Add structured logging (ELK/Datadog), distributed tracing

---

## 13. RUNNING THE APPLICATION

**Setup:**
```bash
# Install dependencies
pip install -r requirements.txt

# Create database
python -c "from main import app, init_db; init_db()"

# Environment variables (.env)
DATABASE_URL=postgresql://...
SESSION_SECRET={32-char random}
STRIPE_SECRET_KEY=sk_test_...
GOOGLE_APPLICATION_CREDENTIALS={path or JSON}
MAILERSEND_API_KEY=...
S3_ENDPOINT_URL=... (etc)

# Run
python main.py                      # Flask dev
gunicorn main:app -w 8 -b :8080   # Production
```

**Key Files:**
- `main.py`: 3000+ lines, all routes and Flask app setup
- `models.py`: SQLAlchemy models, database schema
- `services.py`: External service integrations (Vertex AI, S3, Email, Stripe)
- `cao_config.py`: Dynamic system instructions per tenant
- `provision_tenant.py`: Idempotent tenant provisioning from signup
- `stripe_config.py`: Stripe price mapping
- `templates/`: Jinja2 HTML templates (base.html + 20+ pages)
- `static/`: CSS (Tailwind), JS, images

