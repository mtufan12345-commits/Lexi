# Lexi CAO Meester - Multi-Tenant SaaS Platform

## Overview
Lexi CAO Meester is a premium multi-tenant SaaS platform that functions as an AI assistant for CAO (Collective Labor Agreement) questions, specifically tailored for the greenhouse horticulture sector in the Netherlands. The AI agent, Lexi, leverages Google Vertex AI with RAG (Retrieval Augmented Generation) using gemini-2.5-pro, drawing information from over 1,000 documents including CAOs, labor laws, and secondment rules. The platform aims to deliver significant cost savings to users compared to traditional consultancy. It offers a 3-tier premium pricing model (Starter, Professional, Enterprise) with monthly and annual subscriptions, and emphasizes compliance by providing general information, not legal advice. The official company name and brand identity is Lexi AI.

## User Preferences
- Nederlandse taal voor alle interfaces
- Focus op uitzendbureau gebruikers
- Modern, professional enterprise design
- Dark mode support met toggle (solid colors, NO gradients in dark mode)
- SVG icons in plaats van emoji's voor corporate uitstraling
- Strakke, zakelijke interface met navy blue (#1a2332) en gold (#d4af37) kleurenschema

## System Architecture
The platform is designed with a multi-tenant hierarchy where SUPER ADMINs manage TENANTS (uitzendbureaus), who in turn manage their TENANT ADMINs and END USERS (payroll employees).

**UI/UX Decisions:**
- **Color Scheme:** Navy blue (#1a2332) and gold (#d4af37) for a corporate aesthetic.
- **Design:** Modern, professional enterprise design, responsive for all device types, featuring SVG icons and a dark mode with solid colors.
- **Responsiveness:** Fully responsive design across mobile, tablet, and desktop, including a collapsible sidebar and hamburger menu.

**Technical Implementations & Feature Specifications:**
- **Multi-tenant Isolation:** Implemented via subdomain routing in production and session-based isolation in development.
- **CAO Selection & Dynamic AI Instructions:** Tenants select one of two uitzend-CAO's (NBBU or ABU) during signup. The AI dynamically uses the chosen CAO and all other relevant documents, explicitly excluding the alternative CAO. This ensures the AI never uses both ABU and NBBU simultaneously. Admins can change this preference with warnings about organization-wide impact.
- **Chat Interface:** Interactive chat with Lexi animations, a chat history sidebar, and search functionality.
- **File Management:** Users can upload PDF, DOCX, and text files for AI analysis, with text extraction and OCR fallback. Files are stored in S3.
- **Artifact Generation:** Lexi can generate downloadable documents like contracts and letters (PDF for all tiers, DOCX for Professional/Enterprise).
- **User & Subscription Management:** Features include user management (add/delete/deactivate), role changes, user limits, and Stripe integration for direct paid subscriptions.
- **Payment Security:** Full Stripe Checkout integration with server-side webhook verification using direct HTTP API. Account creation occurs only after successful payment via webhook. Signup data for pending payments is stored securely server-side. Card payments are supported, with iDEAL disabled.
- **Compliance & Disclaimer Strategy:** Multiple layers of disclaimers (checkboxes, modals, sticky chat disclaimers, AI response footers) clarify that Lexi provides general information, not legal advice.
- **Legal Documentation:** AVG-compliant Algemene Voorwaarden and Privacy & Cookiebeleid are accessible via dedicated routes.
- **Support System:** Integrated support ticket system for customers and admin management.
- **Dashboard Analytics:** Provides insights into usage, active users, and top queries.
- **Chat Storage:** Chat messages are stored as JSON files in S3-compatible object storage, with PostgreSQL storing only metadata.
- **Frontend:** Built with HTML, Vanilla JavaScript, and Tailwind CSS v3.
- **Backend:** Flask (Python) handles all routes and business logic.
- **Enterprise-Grade Password Reset:** Token-based password reset flow with time-limited, single-use links and strong security practices (no passwords sent via email, rate limiting, email enumeration protection).

**System Design Choices:**
- **Database:** PostgreSQL for structured data.
- **Storage:** S3-compatible object storage for large binary data (chat messages, uploaded files, generated artifacts).
- **AI Integration:** Google Vertex AI for the RAG agent.

## External Dependencies
- **AI:** Google Vertex AI (gemini-2.5-pro)
- **Database:** PostgreSQL
- **Payments:** Stripe (Checkout, Webhooks, Subscriptions)
- **Email:** MailerSend
- **Object Storage:** S3-compatible object storage (e.g., Hetzner Object Storage)
- **PDF/DOCX Processing:** reportlab, python-docx, MarkItDown, Tesseract (OCR)
- **Icons:** Heroicons library (SVG icons)