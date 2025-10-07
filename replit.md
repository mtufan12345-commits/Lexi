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
- 14-day free trial (no credit card required)

## Architecture
Multi-Tenant Hierarchy:
```
SUPER ADMIN
  └─ TENANTS (uitzendbureaus)
      └─ TENANT ADMIN
          └─ END USERS (payroll employees)
```

## Key Features
1. **Multi-tenant isolatie**: Subdomain routing (bedrijf.lex-cao.replit.app)
2. **Chat interface**: Met LEX animatie tijdens AI response (5 random scenarios)
3. **File uploads**: S3 storage voor documents die LEX kan analyseren
4. **Artifact generatie**: LEX kan documenten genereren en opslaan
5. **Template database**: Tenant admins kunnen templates beheren (arbeidsovereenkomsten, etc)
6. **Session management**: Voorkomt multiple concurrent logins per user
7. **Stripe integratie**: Checkout + webhooks voor subscription management
8. **Email notificaties**: Welcome, trial expiring, payment failed

## Database Schema
- super_admins: Super administrator accounts
- tenants: Uitzendbureau accounts met subdomain, status, max_users
- users: Payroll medewerkers per tenant
- chats: Chat sessies per user
- messages: Chat berichten (user/assistant)
- subscriptions: Stripe subscription data per tenant
- templates: Document templates per tenant
- uploaded_files: User-uploaded files in S3
- artifacts: LEX-generated documents in S3

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
- Clean, professional design met Tailwind CSS
