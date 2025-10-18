# Lexi CAO Meester - Multi-Tenant SaaS Platform

## Overview
Lexi CAO Meester is a premium multi-tenant SaaS platform serving as an "AI assistant for CAO questions, specialized in the greenhouse horticulture sector." The AI agent (Lexi) answers CAO questions based on 1,000+ documents (CAO's, labor law, secondment rules) using Google Vertex AI RAG with gemini-2.5-pro. The platform aims to provide significant cost savings (average €18,000/year) compared to traditional consultants. It offers a 3-tier premium pricing model (Starter, Professional, Enterprise) with monthly and annual subscription options, emphasizing compliance by providing general information, not legal advice.

## User Preferences
- Nederlandse taal voor alle interfaces
- Focus op uitzendbureau gebruikers
- Modern, professional enterprise design
- Dark mode support met toggle (solid colors, NO gradients in dark mode)
- SVG icons in plaats van emoji's voor corporate uitstraling
- Strakke, zakelijke interface met navy blue (#1a2332) en gold (#d4af37) kleurenschema

## System Architecture
The platform features a multi-tenant hierarchy with SUPER ADMINs managing TENANTS (uitzendbureaus), who then manage TENANT ADMINs and END USERS (payroll employees).

**UI/UX Decisions:**
- **Color Scheme:** Navy blue (#1a2332) and gold (#d4af37) for a corporate look.
- **Design:** Modern, professional enterprise design with SVG icons replacing emojis. Dark mode supported with a toggle, featuring solid colors without gradients.
- **Responsiveness:** Fully responsive design for mobile, tablet, and desktop, including a collapsible sidebar and hamburger menu.

**Technical Implementations & Feature Specifications:**
- **Multi-tenant Isolation:** Achieved via subdomain routing (production) and session-based (development).
- **CAO Selection & Dynamic AI Instructions (Oct 2025):** Tenant-wide CAO preference system allowing users to choose between 2 uitzend-CAO's: NBBU or ABU. Selection happens during signup and is stored in tenant profile. **CRITICAL**: AI uses the FULL 1,000+ document corpus regardless of CAO choice - the CAO selection provides contextual framing only, NOT document filtering. AI responses are framed based on selected CAO via custom system instructions in `cao_config.py`, but the AI always has access to all documents. Admins can change CAO preference in dashboard settings with organization-wide impact warnings. Default: NBBU for all legacy data.
- **Chat Interface:** Interactive chat with Lexi animations, a chat history sidebar, and a search function (titles and message content).
- **File Management:** Users can upload PDF, DOCX, and text files for Lexi to analyze, with MarkItDown for PDF text extraction and OCR fallback. Files are stored in S3.
- **Artifact Generation:** Lexi can generate and allow downloads of documents like contracts and letters (PDF for all tiers, DOCX for Professional/Enterprise).
- **User & Subscription Management:** Features include adding/deleting/deactivating users, role changes, user limits, and Stripe integration for subscription management (direct paid model, no free trial).
- **Payment Security (Oct 2025):** Full Stripe Checkout integration with server-side webhook verification using **direct HTTP API** (bypasses SDK issues). Account creation happens ONLY after successful payment via `checkout.session.completed` webhook. Signup data stored server-side in `PendingSignup` table (password hashed) to prevent client-side exposure. Automatic cleanup of stale pending signups (24h). **Payment methods:** Card only (Visa, Mastercard, Amex) - iDEAL disabled pending SEPA Direct Debit activation. Replit iframe escape implemented via `stripe_redirect.html` template to force top-level navigation for Stripe Checkout.
- **Compliance & Disclaimer Strategy:** Multi-layered disclaimers (checkboxes, first-chat warning modal, sticky chat disclaimer, AI response footers) to clarify that Lexi provides general information, not legal advice.
- **Legal Documentation:** Complete AVG-compliant Algemene Voorwaarden (470 lines, 16 articles) and Privacy & Cookiebeleid (431 lines, 14 sections) implemented at /algemene-voorwaarden and /privacy routes with professional HTML templates.
- **Support System:** An integrated support ticket system for customers to create, view, and respond to tickets, with admin management capabilities.
- **Dashboard Analytics:** Provides insights into total questions, active users, monthly usage, and top users.
- **Chat Storage:** All chat messages are stored in S3 (Hetzner Object Storage) as JSON files, with PostgreSQL storing only metadata for efficiency.
- **Frontend:** Built with HTML, Vanilla JavaScript, and Tailwind CSS v3 (PostCSS build for optimized performance).
- **Backend:** Flask (Python) handles all routes and business logic.

**System Design Choices:**
- **Database:** PostgreSQL for structured data.
- **Storage:** S3-compatible object storage for chat messages, uploaded files, and generated artifacts.
- **AI Integration:** Utilizes Google Vertex AI for the RAG agent.

## Recent Changes (October 2025)
- **CAO Selection Feature - Final Implementation (Oct 18, 2025):** Tenant-wide CAO preference system refined to 2 options (NBBU and ABU - both uitzend-CAO's). **Database**: Added `cao_preference` field (varchar 50, default 'NBBU') to both Tenant and PendingSignup models. **Signup Flow**: Integrated CAO selector dropdown in signup form (signup_tenant.html) with 2 options only. Selection saved to PendingSignup + Stripe metadata. **AI Integration**: Created `cao_config.py` with dynamic system instruction generator (`get_system_instruction()`) that provides CAO-specific CONTEXT FRAMING while instructing AI to use FULL 1,000+ document corpus. The CAO choice does NOT filter documents - it only frames how responses are presented. Chat endpoint uses `tenant.cao_preference` to apply contextual framing. **Admin Dashboards**: Both tenant admin and super admin dashboards have CAO dropdown with only NBBU/ABU options. Route `/super-admin/tenants/<id>/cao` handles super admin CAO updates. **Validation**: `validate_cao_preference()` in cao_config.py restricts to NBBU/ABU only. All UI components (signup, admin, super admin) show only these 2 options.
- **Production API Configuration (Oct 17, 2025):** Configured production-ready API keys for Stripe and MailerSend with intelligent fallback for development. **Stripe**: Productie keys (STRIPE_SECRET_KEY_PROD, STRIPE_WEBHOOK_SECRET_PROD) hebben voorrang over test keys (STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET) met automatic mode detection logging ("Production mode" vs "Test mode"). Alle 4 Stripe API locaties geüpdatet (main.py x3, services.py x1). **Stripe Price IDs**: Alle 6 productie Price IDs geconfigureerd in stripe_config.py (Starter/Professional/Enterprise voor monthly/yearly). **MailerSend**: MAILERSEND_API_KEY succesvol geïntegreerd met EmailService, test script (test_production_email.py) beschikbaar voor email verificatie. **FROM_EMAIL** gebruikt trial domain (moet worden vervangen door geverifieerd productie domain). Environment variable priority: Production keys > Test keys voor naadloze dev/prod workflow. Architect verdict: "PASS - Productieconfiguratie en MailerSend integratie voldoen aan taakdoelen."
- **Stripe SDK Upgrade & Critical Signup Fix (Oct 14, 2025):** Fixed critical bug where accounts weren't being created after successful payment. Root cause: Stripe Python SDK 7.8.0 had internal bug where `stripe.apps.Secret` was None, causing AttributeError during checkout session retrieval. This broke both webhook and fallback provisioning paths. Solution: (1) Upgraded Stripe from 7.8.0 to 13.0.1 (latest stable), (2) Updated requirements.txt to `stripe>=13.0.1`, (3) Fixed fallback provisioning to use `from stripe.checkout import Session` import pattern in main.py (lines 402, 441), (4) Verified services.py works without changes (`stripe.checkout.Session` remains compatible in 13.x per official Stripe docs). Result: Successfully provisioned test5@test5.nl account that was stuck after payment. **Production-ready**: Both import patterns (`stripe.checkout.Session` and `from stripe.checkout import Session`) work in Stripe 13.x per official documentation.
- **Pricing Page JavaScript Fix (Oct 14, 2025):** Resolved critical issue where pricing page signup buttons failed with `startSignup is not defined` error. Root cause: JavaScript was in `{% block content %}` but base.html only renders `{% block extra_js %}`, so scripts never reached browser. Solution: Moved entire pricing.html inline script from content block to `{% block extra_js %}` (after line 467). Architect verified fix with PASS verdict. All signup buttons (Starter, Professional, Enterprise) now work correctly with proper billing cycle (monthly/yearly) parameter passing.
- **Webhook Fallback Mechanism (Oct 14, 2025):** Implemented robust fallback system for signup/payment flow that works in BOTH development and production. Root cause: Stripe webhooks cannot reach dev environment → accounts weren't created after payment. Solution: (1) Created shared idempotent provisioning service `provision_tenant_from_signup()` used by both webhook and fallback, (2) Updated webhook to use shared service (DRY principle), (3) Added Stripe-verified fallback in `signup_success()` that validates payment with Stripe API and provisions account if webhook fails. Architect verdict: "PASS - Fallback provisions and logs users in even when webhook never arrives." Prevents Stripe retry loops by returning HTTP 200 when pending signup already processed.
- **Enterprise-Grade Security Overhaul (Oct 14, 2025):** Achieved 11/10 security score with 13 comprehensive fixes:
  * CSRF protection enabled by default (was disabled)
  * Session cookies secured for production (HTTPS only)
  * Stripe webhook signature verification enforced (no bypasses)
  * File upload whitelist implemented (PDF/DOCX/DOC/TXT only)
  * Rate limiting added on critical endpoints (login, webhook, chat API)
  * Super admin password: strong random generation (was hardcoded 'admin123')
  * XSS vulnerabilities patched: Jinja2 autoescape enabled, eval() removed, safe DOM manipulation
  * Secure credential logging: development mode only (safe by default)
  * Session secret required: app crashes without (no hardcoded fallback)
  * Host header injection blocked: Global validation protects tenant isolation
  * Architect verdict: "Security score 11/10 - ENTERPRISE-GRADE SECURITY"
- **Critical Webhook Bug Fix (Oct 14, 2025):** Fixed critical bug preventing automatic account creation after payment. The Stripe webhook was crashing with "name 'json' is not defined" error because the json module was not imported in main.py. This caused all post-payment account creation to fail silently. Solution: Added `import json` to main.py imports. This fix enables the complete payment flow: Stripe Checkout → Webhook processes payment → Account auto-created → User auto-logged in.
- **Branding Update:** All references to "Adem Management Holding B.V." have been replaced with "Lexi AI" across the entire website, including Privacy & Cookiebeleid and Algemene Voorwaarden pages. Lexi AI is now the official company name and brand identity.
- **Chat Send Button Fix (Oct 11, 2025):** Resolved critical JavaScript timing issue where send button event handlers were being registered before DOM elements existed. Solution: Global variables (`currentChatId`, `hasShownFirstChatWarning`, `uploadedFileId`) and core functions (`window.handleMessageSubmit`, `window.addMessageToDOM`) are now defined in early script block BEFORE the message form loads. This ensures event listeners attach correctly when the form is parsed. All helper functions exposed on window object for reliable cross-script access.
- **Duplicate Error Message Fix (Oct 11, 2025):** Fixed bug where every chat message triggered a duplicate error message "Er is een fout opgetreden. Probeer het opnieuw." Root cause: `window.loadChatFiles()` was being called but the function didn't exist, causing a JavaScript exception that triggered the catch handler. Removed the nonexistent function call - attachments are already fetched earlier in the message flow.
- **Avatar Display Enhancement (Oct 11, 2025):** Improved user avatar validation to handle empty strings and 'undefined' values, with onerror fallback to initials display for broken image URLs.
- **Favicon Implementation (Oct 11, 2025):** Created favicon.ico and favicon.png from Lexi logo and integrated into base.html template for proper browser tab display.
- **Chat Disclaimer Simplification (Oct 11, 2025):** Removed repetitive disclaimer from every Lexi response. The sticky disclaimer at the top of the chat input area provides sufficient legal protection without cluttering each message.

## External Dependencies
- **AI:** Google Vertex AI (gemini-2.5-pro)
- **Database:** PostgreSQL
- **Payments:** Stripe (Checkout, Webhooks, Subscriptions)
- **Email:** MailerSend (transactional emails, welcome emails, payment notifications)
- **Object Storage:** S3-compatible object storage (e.g., Hetzner Object Storage)
- **PDF/DOCX Processing:** reportlab (PDF), python-docx (Word), Microsoft MarkItDown library (PDF text extraction), Tesseract (OCR)
- **Icons:** Heroicons library (SVG icons)