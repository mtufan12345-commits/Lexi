# LEX CAO Expert - Multi-Tenant SaaS Platform

## Project Overview
LEX CAO Expert is een multi-tenant SaaS platform voor uitzendbureaus in Nederland. Het biedt een AI-agent (LEX) die CAO-vragen beantwoordt op basis van 70+ CAO documenten via Google Vertex AI.

## Tech Stack
- **Backend**: Flask (Python)
- **Database**: PostgreSQL (Replit native)
- **Frontend**: HTML + Vanilla JavaScript + Tailwind CSS
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
- `.env.example`: Required environment variables

## Setup Notes
1. Super admin account wordt automatisch aangemaakt bij eerste start:
   - Email: admin@lex-cao.nl
   - Password: admin123
   
2. Vertex AI credentials moeten worden geconfigureerd via environment variables

3. S3 storage moet worden geconfigureerd voor file uploads en artifacts

4. Stripe webhooks moeten worden geconfigureerd voor subscription events

## Development
Run: `python main.py` (binds to 0.0.0.0:5000)

## User Preferences
- Nederlandse taal voor alle interfaces
- Focus op uitzendbureau gebruikers
- Modern, professional enterprise design
- Dark mode support met toggle
- SVG icons in plaats van emoji's voor corporate uitstraling
- Strakke, zakelijke interface met gradient accents
