# 🔧 Vertex AI Credentials Oplossen

## Probleem
**Foutmelding:** "Invalid JWT Signature"
**Oorzaak:** Google Vertex AI credentials zijn verlopen of incorrect

## Oplossing: Nieuwe Service Account Credentials Genereren

### Stap 1: Google Cloud Console
1. Ga naar: https://console.cloud.google.com
2. Selecteer je project: **${GOOGLE_CLOUD_PROJECT}**
3. Navigeer naar: **IAM & Admin → Service Accounts**

### Stap 2: Service Account Vinden/Maken
1. Zoek bestaande service account **OF** maak nieuwe aan
2. Klik op de service account email
3. Ga naar tab: **Keys**

### Stap 3: Nieuwe Key Genereren
1. Klik: **Add Key → Create new key**
2. Selecteer: **JSON**
3. Download het bestand (bijv. `lexi-credentials.json`)

### Stap 4: Vereiste Rollen Controleren
Zorg dat de service account deze rollen heeft:
- ✅ **Vertex AI User**
- ✅ **Generative AI Admin** (of Generative AI User)
- ✅ **Storage Object Viewer** (voor RAG corpus)

### Stap 5: Credentials Updaten in Hetzner

#### Optie A: Via Replit Secrets (voor development)
```bash
# Kopieer volledige inhoud van JSON bestand
GOOGLE_APPLICATION_CREDENTIALS='{"type":"service_account","project_id":"...","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",...}'
```

#### Optie B: Via Hetzner Environment Variables
1. SSH naar je Hetzner server
2. Edit je environment file (bijv. `.env` of systemd service file)
3. Voeg toe:
```bash
export GOOGLE_APPLICATION_CREDENTIALS='{"type":"service_account",...}'
export GOOGLE_CLOUD_PROJECT="je-project-id"
export VERTEX_AI_LOCATION="europe-west4"
export VERTEX_AI_AGENT_ID="je-rag-corpus-id"
```
4. Herstart je applicatie

### Stap 6: Testen
1. Herstart de applicatie
2. Log in op https://test.lexiai.nl
3. Stuur een test bericht aan Lexi
4. Controleer of je een antwoord krijgt ✅

## 🔍 Verificatie Commands

### Check of credentials geladen zijn:
```bash
python3 << 'EOF'
import os
import json
creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if creds:
    data = json.loads(creds)
    print(f"✅ Project: {data.get('project_id')}")
    print(f"✅ Email: {data.get('client_email')}")
else:
    print("❌ GOOGLE_APPLICATION_CREDENTIALS niet gevonden")
