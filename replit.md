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
- **Chat Interface:** Interactive chat with Lexi animations, a chat history sidebar, and a search function (titles and message content).
- **File Management:** Users can upload PDF, DOCX, and text files for Lexi to analyze, with MarkItDown for PDF text extraction and OCR fallback. Files are stored in S3.
- **Artifact Generation:** Lexi can generate and allow downloads of documents like contracts and letters (PDF for all tiers, DOCX for Professional/Enterprise).
- **User & Subscription Management:** Features include adding/deleting/deactivating users, role changes, user limits, and Stripe integration for subscription management (direct paid model, no free trial).
- **Payment Security (Oct 2025):** Full Stripe Checkout integration with server-side webhook verification using **direct HTTP API** (bypasses SDK issues). Account creation happens ONLY after successful payment via `checkout.session.completed` webhook. Signup data stored server-side in `PendingSignup` table (password hashed) to prevent client-side exposure. Automatic cleanup of stale pending signups (24h). **Payment methods:** Card (Visa, Mastercard, Amex) and iDEAL (Dutch banks). Replit iframe escape implemented via `stripe_redirect.html` template to force top-level navigation for Stripe Checkout.
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
- **Complete Security Overhaul (Oct 14, 2025):** Achieved 10/10 security score with comprehensive fixes:
  * CSRF protection enabled by default (was disabled)
  * Session cookies secured for production (HTTPS only)
  * Stripe webhook signature verification enforced (no bypasses)
  * File upload whitelist implemented (PDF/DOCX/DOC/TXT only)
  * Rate limiting added on critical endpoints (login, webhook, chat API)
  * Super admin password: strong random generation (was hardcoded 'admin123')
  * XSS vulnerabilities patched: Jinja2 autoescape enabled, eval() removed, safe DOM manipulation
  * Secure credential logging: development mode only (safe by default)
  * Architect verdict: "Security score 10/10 - APPROVED FOR PRODUCTION"
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