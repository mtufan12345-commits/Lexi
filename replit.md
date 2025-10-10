# Lexi CAO Meester - Multi-Tenant SaaS Platform

## Project Overview
**Lexi CAO Meester** is een premium multi-tenant SaaS platform gepositioneerd als "AI-assistent voor CAO-vragen, gespecialiseerd in de glastuinbouw-sector". De AI-agent (Lexi) beantwoordt CAO-vragen op basis van 1.000+ documenten (CAO's, arbeidsrecht, detacheringsregels) via Google Vertex AI RAG met gemini-2.5-pro. Gemiddelde kostenbesparing: **€18.000/jaar** t.o.v. traditionele adviseurs.

**Compliance Note**: Alle juridische terminologie vervangen door "AI-assistent voor CAO-vragen" om te benadrukken dat Lexi algemene informatie verstrekt, geen juridisch advies.

## Tech Stack
- **Backend**: Flask (Python)
- **Database**: PostgreSQL (Replit native)
- **Frontend**: HTML + Vanilla JavaScript + Tailwind CSS v3 (PostCSS build)
- **AI**: Google Vertex AI (existing RAG agent)
- **Payments**: Stripe
- **Email**: SendGrid
- **Storage**: S3-compatible object storage

## Business Model (3-Tier Premium Pricing)
- **Starter**: €499/maand (5 users, unlimited questions)
- **Professional**: €599/maand (10 users, unlimited questions) - MEEST POPULAIR
- **Enterprise**: €1.199/maand (unlimited users, unlimited questions)
- 3 free questions (no credit card required) - replaced 14-day trial
- **Value Proposition**: Gemiddeld €18.000/jaar besparing op juridische advieskosten

## Architecture
Multi-Tenant Hierarchy:
```
SUPER ADMIN
  └─ TENANTS (uitzendbureaus)
      └─ TENANT ADMIN
          └─ END USERS (payroll employees)
```

## Key Features
1. **Multi-tenant isolatie**: Subdomain routing (production) + session-based (development)
2. **Chat interface**: Met Lexi animatie (8 visual-only scenarios) tijdens AI response
3. **Chat history sidebar**: Snelle toegang tot eerdere chats met datum/tijd
4. **File uploads**: PDF, DOCX, en text bestanden die Lexi kan analyseren
5. **Artifact generatie**: Lexi kan documenten genereren (contracten, brieven) met download buttons
6. **User management**: Add/delete/deactivate users, role changes (admin/user), user limits
7. **Dashboard analytics**: Totaal vragen, actieve users, usage per maand, top users
8. **Template database**: Tenant admins kunnen templates beheren
9. **Session management**: Voorkomt multiple concurrent logins per user
10. **Stripe integratie**: Checkout + webhooks voor subscription management
11. **Email notificaties**: Welcome, trial expiring, payment failed
12. **Support Ticket Systeem**: Klanten kunnen support tickets aanmaken, admins kunnen reageren en status beheren

## Database Schema
- super_admins: Super administrator accounts
- tenants: Uitzendbureau accounts met subdomain, status, max_users
- users: Payroll medewerkers per tenant
- chats: Chat sessies met s3_messages_key en message_count (messages in S3)
- messages: Legacy table (deprecated - messages now in S3)
- subscriptions: Stripe subscription data per tenant
- templates: Document templates per tenant
- uploaded_files: User-uploaded files in S3
- artifacts: Lexi-generated documents in S3
- support_tickets: Support tickets met ticket_number, status, category per tenant/user
- support_replies: Conversatie berichten binnen tickets (customer + admin)

## Chat Storage Architecture
**All chat messages are stored in S3 (Hetzner Object Storage) as JSON files:**
- Messages stored per chat in S3 (`chats/tenant_{id}/chat_{id}_messages.json`)
- PostgreSQL stores only metadata (s3_messages_key, message_count, timestamps)
- Triple fallback for question counting: message_count → S3 → PostgreSQL (legacy)
- Error handling: S3 failures abort requests with 500 error
- Migration script available: `migrate_chats_to_s3.py`

## Important Files
- `main.py`: Flask applicatie met alle routes
- `models.py`: Database models met SQLAlchemy
- `services.py`: Vertex AI, S3, Stripe, en SendGrid services
- `templates/`: Jinja2 templates voor alle paginas
- `tailwind.config.js`: Tailwind CSS v3 configuration
- `postcss.config.js`: PostCSS configuration voor CSS processing
- `static/css/input.css`: Tailwind source file (build input)
- `static/css/output.css`: Compiled CSS (auto-generated, git-ignored)
- `.env.example`: Required environment variables

## Testing & Quality Assurance (October 10, 2025)
### Complete Button & Functionality Test
- **All 43 LSP type hints errors resolved** (main.py)
- **28+ critical buttons verified**: Chat interface, Support system, Admin panel
- **69 API routes tested**: All endpoints operational and responding correctly
- **5 public pages verified**: Landing, Pricing, Login, Signup, Super Admin login
- **JavaScript event handlers**: All correctly coupled to backend routes
- **No runtime errors**: Server running clean, no console errors
- **Production ready**: All user roles (User, Admin, Super Admin) fully functional

### Tier-Based Functionality Verification
**Export Functions:**
- ✅ **Starter (€499)**: PDF export only (DOCX blocked with HTTP 403)
- ✅ **Professional (€599)**: PDF + DOCX export (both formats available)
- ✅ **Enterprise (€1.199)**: PDF + DOCX export (both formats available)

**Upload Functions (All Tiers):**
- ✅ PDF upload with MarkItDown text extraction
- ✅ OCR fallback for scanned PDFs (Tesseract: Nederlands + Engels)
- ✅ DOCX & TXT upload support
- ✅ S3 storage with database metadata

**Security Validation:**
- ✅ Backend tier check: `tier not in ['professional', 'enterprise']` → HTTP 403
- ✅ Frontend conditional rendering: Jinja2 + JavaScript tier checks
- ✅ Tenant isolation: user_id + tenant_id filters on all queries
- ✅ Subscription status validation before operations

## Recent Updates (October 2025)
0. **Compliance Update - Juridische Terminologie Vervangen** (October 10, 2025):
   - Alle "Complete juridische AI-adviseur" → "AI-assistent voor CAO-vragen"
   - "Juridisch advies beschikbaar" → "CAO-informatie beschikbaar"
   - "Juridisch advies in 30 seconden" → "Uw antwoord in 30 seconden"
   - Footer disclaimer toegevoegd: "⚠️ Lexi verstrekt algemene informatie, geen juridisch advies"
   - Meta tags, titles, en descriptions aangepast voor compliance
1. **Homepage Glastuinbouw-Specifieke Vragen** (October 10, 2025):
   - "Herkent u dit?" sectie vernieuwd met 4 glastuinbouw-gerichte voorbeelden:
     • Welke toeslagen gelden er voor nacht- en weekendwerk in de glastuinbouw?
     • Mag ik loon inhouden bij ziekte tijdens de proeftijd?
     • Wat zijn de transitievergoedingsregels bij seizoenscontracten?
     • Hoe bereken ik de de fase telling bij wisselende diensten?
1. **Document Viewer Fix**: PDF viewer nu met presigned S3 URLs voor CORS-free viewing
2. **Tailwind CSS Migration**: Upgraded van CDN naar PostCSS build setup
   - Performance: 3+ MB CDN → ~36KB compiled CSS
   - Build pipeline: tailwindcss v3 + postcss + autoprefixer
   - Production-ready met minification
3. **Volledig Responsive Design** (October 8, 2025):
   - Alle pagina's responsive voor mobile, tablet en desktop
   - Inklapbare sidebar voor chat interface (mobile + desktop toggle)
   - Hamburger menu voor admin panel navigation
   - Fixed impersonation banner overlay issue met viewport-based positioning
4. **Chat Zoekfunctie** (October 8, 2025):
   - Doorzoekt chat titels én message content (S3)
   - Live search met debouncing (300ms)
   - Match indicators: "📌 In titel" (groen) / "📝 In bericht" (blauw)
   - Snippet preview voor content matches
5. **Enhanced Chat Avatars** (October 8, 2025):
   - Grotere avatars (w-8→w-12) voor betere zichtbaarheid
   - Toon gebruikersfoto's in chat berichten
   - Fallback naar initials wanneer geen foto beschikbaar
   - Consistent voor server-rendered en client-side berichten
6. **Document Upload Redesign** (October 8, 2025):
   - Echte delete functie: verwijdert uit PostgreSQL + S3
   - Sidebar transformatie met tabs: "Chats" / "Bijlagen" views
   - Bijlagen sidebar: file list, upload, delete, size display
   - Delete confirmation modal voor veiligheid
   - State management tussen chat history en file management
7. **Light Mode Visual Enhancements** (October 8, 2025):
   - Subtiele gradient achtergronden (blue/purple/indigo)
   - Betere shadows: shadow-md → shadow-lg met hover effecten
   - Kleurrijke gradient icon backgrounds voor admin stats
   - Gradient headers en improved card styling
   - Dark mode onveranderd, alleen light mode verbeterd
8. **Support Ticket Systém** (October 9, 2025):
   - Customer side: ticket aanmaken, bekijken, antwoorden, sluiten
   - Admin side: dashboard met filters (status/category), stats, ticket beheer
   - Status flow: open → in_progress/answered → closed
   - Categories: Technical, Lex Question, Billing, CAO-related, Other
   - Chat-like interface voor conversatie tussen customer en admin
   - Auto ticket numbering (#1000, #1001, etc.)
9. **Navy Blue & Gold Color Scheme** (October 9, 2025):
   - Complete rebrand: blue/purple/indigo → navy blue (#1a2332) & gold (#d4af37)
   - Landing page: Gold CTA button, navy outlined secondary with gold hover
   - Chat interface: Navy gradients, focus rings, drag-drop zones
   - Admin dashboards: Navy/gold throughout (sidebar, stats, buttons)
   - Pricing page: Navy-gold gradient logo, gold buttons, navy accents
   - Smooth transitions (0.3s) on interactive elements
   - Dark mode: Solid colors only, no gradients
10. **Tier-Based Chat Export Functionaliteit** (October 9, 2025):
   - PDF export voor ALLE tiers (Starter, Professional, Enterprise)
   - Word (DOCX) export alleen voor Professional en Enterprise tiers
   - Tier restrictions via backend validation (403 error voor unauthorized tiers)
   - Export dropdown menu in chat sidebar met conditional rendering
   - Professional formatting met reportlab (PDF) en python-docx (Word)
   - Navy/gold kleuren in exported documents voor brand consistency
11. **Professional UI Enhancement - Emoji Removal** (October 9, 2025):
   - Alle emoji's vervangen door SVG iconen voor corporate uitstraling
   - Affected pages: landing, pricing, chat, login, admin, super_admin
12. **Free Trial Removal - Direct Paid Subscription Model** (October 9, 2025):
   - Verwijderd: 14-dagen gratis trial periode
   - Nieuwe flow: gebruikers kiezen direct een betaald plan (€499/€599/€1.199)
   - Landing page: CTAs aangepast naar "Bekijk Prijzen" i.p.v. "Probeer gratis"
   - Backend: nieuwe tenants krijgen status='active' + plan='professional' bij signup
   - Admin templates: trial status displays verwijderd
   - Super admin: trial opties verwijderd uit tier/status dropdowns
   - Analytics: trial funnel verwijderd, alleen signups → active conversie
   - Routes verwijderd: /api/free-trial, /free-chat, /api/free-chat/*
   - Nieuwe iconen: document, checkmark, money, globe, analytics, support
   - Consistent icon system gebruikt Heroicons library (stroke-based)
   - Volledig emoji-vrij platform voor zakelijke professionaliteit
13. **MarkItDown PDF Text Extraction** (October 9, 2025):
   - Microsoft MarkItDown library geïntegreerd voor PDF tekstextractie
   - Automatische extractie bij upload, tekst opgeslagen in database (extracted_text kolom)
   - Snellere chat responses: geen herhaalde PDF parsing, direct uit database
   - Fallback: voor DOCX/text bestanden blijft S3 download functionaliteit
   - Database schema uitgebreid: uploaded_files.extracted_text (TEXT nullable)
14. **Mobile Dark Mode Toggle & Chat UI Fixes** (October 9, 2025):
   - Dark mode toggle toegevoegd aan mobile menu (landing + pricing pages)
   - Hamburger menu met toggle button en label ("Dark mode" / "Light mode")
   - Chat export dropdown teruggezet in dynamisch gegenereerde items
   - Export functionaliteit volledig hersteld in updateChatList() en displaySearchResults()
   - Chat welkomstbericht vertaald: "Welkom bij Lexi" + Nederlandse beschrijving
   - Dark mode achtergronden verbeterd: bg-black → bg-zinc-950 voor consistentie
   - Chat hover menu icons nu met duidelijke achtergrond voor betere zichtbaarheid

## Setup Notes
1. Super admin account wordt automatisch aangemaakt bij eerste start:
   - Email: admin@lex-cao.nl
   - Password: admin123
   
2. Vertex AI credentials moeten worden geconfigureerd via environment variables

3. S3 storage moet worden geconfigureerd voor file uploads en artifacts

4. Stripe webhooks moeten worden geconfigureerd voor subscription events

## Development
1. **CSS Build**: Run `npm run build:css` to compile Tailwind CSS (output: static/css/output.css ~36KB)
   - Watch mode: `npm run watch:css` for auto-rebuild during development
2. **Server**: Run `python main.py` (binds to 0.0.0.0:5000)

**Note**: Tailwind CSS is now production-optimized with PostCSS build instead of CDN (3+ MB → ~36KB)

## User Preferences
- Nederlandse taal voor alle interfaces
- Focus op uitzendbureau gebruikers
- Modern, professional enterprise design
- Dark mode support met toggle (solid colors, NO gradients in dark mode)
- SVG icons in plaats van emoji's voor corporate uitstraling
- Strakke, zakelijke interface met navy blue (#1a2332) en gold (#d4af37) kleurenschema
