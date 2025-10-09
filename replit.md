# LEX CAO Expert - Multi-Tenant SaaS Platform

## Project Overview
LEX CAO Expert is een multi-tenant SaaS platform voor uitzendbureaus in Nederland. Het biedt een AI-agent (LEX) die CAO-vragen beantwoordt op basis van 70+ CAO documenten via Google Vertex AI.

## Tech Stack
- **Backend**: Flask (Python)
- **Database**: PostgreSQL (Replit native)
- **Frontend**: HTML + Vanilla JavaScript + Tailwind CSS v3 (PostCSS build)
- **AI**: Google Vertex AI (existing RAG agent)
- **Payments**: Stripe
- **Email**: SendGrid
- **Storage**: S3-compatible object storage

## Business Model
- Professional: €499/maand (5 users, unlimited questions)
- Enterprise: €1.199/maand (unlimited users, unlimited questions)
- 3 free questions (no credit card required) - replaced 14-day trial

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
2. **Chat interface**: Met LEX animatie (8 visual-only scenarios) tijdens AI response
3. **Chat history sidebar**: Snelle toegang tot eerdere chats met datum/tijd
4. **File uploads**: PDF, DOCX, en text bestanden die LEX kan analyseren
5. **Artifact generatie**: LEX kan documenten genereren (contracten, brieven) met download buttons
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
- artifacts: LEX-generated documents in S3
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

## Recent Updates (October 2025)
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
8. **Support Ticket Systeem** (October 9, 2025):
   - Customer side: ticket aanmaken, bekijken, antwoorden, sluiten
   - Admin side: dashboard met filters (status/category), stats, ticket beheer
   - Status flow: open → in_progress/answered → closed
   - Categories: Technical, Lex Question, Billing, CAO-related, Other
   - Chat-like interface voor conversatie tussen customer en admin
   - Auto ticket numbering (#1000, #1001, etc.)

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
- Dark mode support met toggle
- SVG icons in plaats van emoji's voor corporate uitstraling
- Strakke, zakelijke interface met gradient accents
