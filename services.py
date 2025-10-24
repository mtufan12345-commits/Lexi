import os
import json
import boto3
import stripe
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
import io
from PyPDF2 import PdfReader
from docx import Document
import threading

# Productie Stripe key heeft voorrang over test key
stripe.api_key = os.getenv('STRIPE_SECRET_KEY_PROD') or os.getenv('STRIPE_SECRET_KEY', '')

class VertexAIService:
    """
    Singleton Vertex AI Service
    
    CRITICAL for production deployment:
    - Uses thread-safe singleton pattern to prevent client recreation
    - Prevents AttributeError crashes in gunicorn workers
    - Ensures single client instance across all requests
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Thread-safe singleton implementation"""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    def __init__(self):
        """Initialize only once per process (singleton pattern)"""
        # Skip if already initialized
        if self._initialized:
            return
            
        credentials_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        self.client = None  # Initialize to None to prevent __del__ errors

        try:
            from google import genai
            from google.genai import types
            import tempfile

            self.genai = genai
            self.types = types

            # Enhanced credentials validation and error handling
            if not credentials_json:
                raise ValueError("GOOGLE_APPLICATION_CREDENTIALS environment variable is not set")
            
            if isinstance(credentials_json, str):
                # Defensive check: is it already a file path or JSON string?
                if credentials_json.strip().startswith('{'):
                    # It's a JSON string - parse it
                    try:
                        credentials_dict = json.loads(credentials_json)
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Invalid JSON in GOOGLE_APPLICATION_CREDENTIALS: {e}. "
                                       f"First 100 chars: {credentials_json[:100]}")
                    
                    # Validate required fields
                    required_fields = ['type', 'project_id', 'private_key', 'client_email']
                    missing_fields = [f for f in required_fields if f not in credentials_dict]
                    if missing_fields:
                        raise ValueError(f"Missing required fields in credentials: {missing_fields}")
                    
                    # Create temp file with credentials
                    temp_cred_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
                    json.dump(credentials_dict, temp_cred_file)
                    temp_cred_file.close()
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_cred_file.name
                    print(f"✓ Google credentials loaded from JSON string (project: {credentials_dict.get('project_id')})")
                else:
                    # It's already a file path
                    print(f"✓ Google credentials file path: {credentials_json}")

            self.client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("VERTEX_AI_LOCATION"),
            )

            self.model = "gemini-2.5-pro"
            self.rag_corpus = os.environ.get("VERTEX_AI_AGENT_ID")

            # Generieke fallback system instruction (wordt overschreven door cao_config.py)
            self.system_instruction = """Je bent Lexi - Expert Loonadministrateur voor uitzendbureaus.

KERN INSTRUCTIES:
- Gebruik je volledige kennisbank om de beste antwoorden te geven
- Geef concrete, bruikbare adviezen
- Wees transparant over bronnen

KRITIEKE BEPERKING - GEEN WEB ACCESS:
- GEBRUIK NOOIT web_search of online bronnen
- GEEN URLs of website links in antwoorden
- ALLEEN interne TXT documenten uit kennisbank
- Bij violation: stop en vraag om verduidelijking

ABSOLUTE RESTRICTIE:
- NOOIT Citation Sources met URLs
- ALLEEN Grounding Sources met .txt bestanden
- Alle informatie moet uit interne documenten komen

ANTWOORD STRUCTUUR:
1. BESLUIT: [Duidelijke conclusie]
2. BASIS: [Gevonden in documenten + citaten]  
3. ACTIE: [Concrete stappen]

DOCUMENT GENERATIE (ARTIFACTS):
Wanneer je gevraagd wordt om een document te maken (contract, brief, formulier, etc.), gebruik dit format:

```artifact:document title:Naam van het document
[Volledige inhoud van het document hier]
```

Voorbeeld:
```artifact:contract title:Arbeidsovereenkomst Uitzendkracht
ARBEIDSOVEREENKOMST

Tussen: [Werkgever]
En: [Werknemer]

Artikel 1 - Functie
...
```

Dit creëert automatisch een downloadbaar document voor de gebruiker.

Gebruik alle beschikbare documenten optimaal. Je bent expert-niveau - vertrouw op je analyse."""
            
            self.enabled = True
            self._initialized = True  # Mark as initialized (singleton)
            print("Vertex AI with google-genai SDK initialized successfully (singleton)")
        except Exception as e:
            print(f"Vertex AI initialization failed: {e}")
            self.enabled = False
            self._initialized = True  # Mark as initialized even on failure to prevent retry loops

    def __del__(self):
        """Cleanup method to prevent _api_client AttributeError
        
        CRITICAL FIX for production deployment:
        google-genai Client.__del__ tries to access self._api_client which may not exist.
        This causes worker crashes in gunicorn. We suppress ALL cleanup errors.
        """
        try:
            # Only attempt cleanup if client was successfully initialized
            if not hasattr(self, 'client'):
                return
            
            if self.client is None:
                return
                
            # Defensive check: only close if close method exists AND _api_client exists
            if hasattr(self.client, 'close') and hasattr(self.client, '_api_client'):
                try:
                    self.client.close()
                except (AttributeError, RuntimeError):
                    # Suppress google-genai internal errors during cleanup
                    pass
                    
            # Always clear reference to prevent dangling pointer
            self.client = None
        except Exception:
            # Silently ignore ALL errors during cleanup
            # This prevents gunicorn worker crashes on shutdown
            pass

    def chat(self, message, conversation_history=None, system_instruction=None):
        if not self.enabled or not self.client:
            return "Lexi is momenteel niet beschikbaar. Configureer de Google Vertex AI credentials in de environment variables om Lexi te activeren."

        import time
        max_retries = 3
        base_delay = 2  # seconds

        for attempt in range(max_retries):
            try:
                contents = []

                if conversation_history:
                    for msg in conversation_history:
                        contents.append(self.types.Content(
                            role=msg.get('role', 'user'),
                            parts=[self.types.Part.from_text(text=msg.get('content', ''))]
                        ))

                contents.append(self.types.Content(
                    role="user",
                    parts=[self.types.Part.from_text(text=message)]
                ))

                tools = [
                    self.types.Tool(
                        retrieval=self.types.Retrieval(
                            vertex_rag_store=self.types.VertexRagStore(
                                rag_resources=[
                                    self.types.VertexRagStoreRagResource(
                                        rag_corpus=self.rag_corpus
                                    )
                                ],
                                similarity_top_k=10,  # Reduced from 20 to 10 to save quota
                            )
                        )
                    )
                ]

                instruction_text = system_instruction if system_instruction else self.system_instruction

                # Optimized config to reduce quota usage
                config = self.types.GenerateContentConfig(
                    temperature=1,
                    top_p=0.95,
                    max_output_tokens=8192,  # Reduced from 65535 to 8192 (still very large)
                    tools=tools,
                    system_instruction=[self.types.Part.from_text(text=instruction_text)],
                    thinking_config=self.types.ThinkingConfig(thinking_budget=8192),  # Limited thinking budget
                )

                response_text = ""
                for chunk in self.client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=config,
                ):
                    if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                        if chunk.text:
                            response_text += chunk.text

                return response_text

            except Exception as e:
                error_str = str(e)

                # Check if it's a 429 rate limit error
                if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str:
                    if attempt < max_retries - 1:
                        # Exponential backoff: 2s, 4s, 8s
                        delay = base_delay * (2 ** attempt)
                        print(f"⚠️ Rate limit hit (attempt {attempt + 1}/{max_retries}), waiting {delay}s before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"❌ Rate limit persists after {max_retries} attempts: {e}")
                        return "Lexi is momenteel overbelast. Probeer het over een paar minuten opnieuw, of neem contact op met support als dit probleem aanhoudt."
                else:
                    # Non-rate-limit error, don't retry
                    print(f"Vertex AI chat error: {e}")
                    return f"Er ging iets mis bij het verwerken van je vraag: {error_str}"

        # Should not reach here, but just in case
        return "Er ging iets mis bij het verwerken van je vraag. Probeer het later opnieuw."

class S3Service:
    """
    Singleton S3 Service
    
    CRITICAL for production deployment:
    - Uses thread-safe singleton pattern to prevent client recreation
    - Prevents boto3 client creation crashes in gunicorn workers
    - Ensures single S3 client instance across all requests
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Thread-safe singleton implementation"""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize only once per process (singleton pattern)"""
        # Skip if already initialized
        if self._initialized:
            return
            
        self.endpoint = os.getenv('S3_ENDPOINT_URL')
        self.bucket = os.getenv('S3_BUCKET_NAME')
        self.access_key = os.getenv('S3_ACCESS_KEY')
        self.secret_key = os.getenv('S3_SECRET_KEY')
        
        if all([self.endpoint, self.bucket, self.access_key, self.secret_key]):
            try:
                self.s3_client = boto3.client(
                    's3',
                    endpoint_url=self.endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key
                )
                self.enabled = True
                self._initialized = True
                print("✓ S3 Service initialized successfully (singleton)")
            except Exception as e:
                print(f"S3 initialization failed: {e}")
                self.enabled = False
                self._initialized = True
        else:
            self.enabled = False
            self._initialized = True
            print("S3 Service disabled (missing credentials)")
    
    def upload_file(self, file, tenant_id, folder='uploads'):
        if not self.enabled:
            return None
        
        try:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4()}_{filename}"
            s3_key = f"{folder}/tenant_{tenant_id}/{unique_filename}"
            
            self.s3_client.upload_fileobj(
                file,
                self.bucket,
                s3_key,
                ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'}
            )
            
            return s3_key
        except Exception as e:
            print(f"S3 upload error: {e}")
            return None
    
    def upload_content(self, content, filename, tenant_id, folder='artifacts'):
        if not self.enabled:
            return None
        
        try:
            unique_filename = f"{uuid.uuid4()}_{filename}"
            s3_key = f"{folder}/tenant_{tenant_id}/{unique_filename}"
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=content.encode('utf-8') if isinstance(content, str) else content,
                ContentType='text/plain'
            )
            
            return s3_key
        except Exception as e:
            print(f"S3 upload content error: {e}")
            return None
    
    def download_file_content(self, s3_key, mime_type=None):
        if not self.enabled:
            return None, "S3 niet geconfigureerd"
        
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            content_bytes = response['Body'].read()
            
            if mime_type == 'application/pdf':
                try:
                    pdf_file = io.BytesIO(content_bytes)
                    pdf_reader = PdfReader(pdf_file)
                    text_content = []
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text and page_text.strip():
                            text_content.append(page_text)
                    
                    if not text_content:
                        return None, "PDF bevat geen leesbare tekst (mogelijk scan of beveiligd)"
                    
                    return '\n'.join(text_content), None
                except Exception as e:
                    return None, f"Kon PDF niet lezen: {str(e)}"
            
            if mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                try:
                    docx_file = io.BytesIO(content_bytes)
                    doc = Document(docx_file)
                    text_content = []
                    
                    for paragraph in doc.paragraphs:
                        if paragraph.text.strip():
                            text_content.append(paragraph.text)
                    
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = []
                            for cell in row.cells:
                                if cell.text.strip():
                                    row_text.append(cell.text.strip())
                            if row_text:
                                text_content.append(' | '.join(row_text))
                    
                    if not text_content:
                        return None, "DOCX bevat geen leesbare tekst"
                    
                    return '\n'.join(text_content), None
                except Exception as e:
                    return None, f"Kon DOCX niet lezen: {str(e)}"
            
            if mime_type and 'text' in mime_type:
                try:
                    return content_bytes.decode('utf-8'), None
                except UnicodeDecodeError:
                    return content_bytes.decode('latin-1'), None
            
            try:
                return content_bytes.decode('utf-8'), None
            except UnicodeDecodeError:
                return None, "Kon bestand niet lezen. Upload alleen tekst, PDF of DOCX bestanden."
                
        except Exception as e:
            print(f"S3 download error: {e}")
            return None, f"Fout bij downloaden: {str(e)}"
    
    def get_file_url(self, s3_key, expiration=3600):
        if not self.enabled:
            return None
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            print(f"S3 get URL error: {e}")
            return None
    
    def delete_file(self, s3_key):
        if not self.enabled:
            return False
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
            return True
        except Exception as e:
            print(f"S3 delete error: {e}")
            return False
    
    def save_chat_messages(self, chat_id, tenant_id, messages):
        """Save chat messages to S3 as JSON"""
        if not self.enabled:
            return None
        
        try:
            s3_key = f"chats/tenant_{tenant_id}/chat_{chat_id}_messages.json"
            
            messages_data = json.dumps(messages, ensure_ascii=False, indent=2)
            
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=messages_data.encode('utf-8'),
                ContentType='application/json'
            )
            
            return s3_key
        except Exception as e:
            print(f"S3 save chat messages error: {e}")
            return None
    
    def get_chat_messages(self, s3_key):
        """Get chat messages from S3"""
        if not self.enabled:
            return []
        
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            return json.loads(content)
        except self.s3_client.exceptions.NoSuchKey:
            return []
        except Exception as e:
            print(f"S3 get chat messages error: {e}")
            return []
    
    def get_messages(self, s3_key):
        """Get chat messages from S3 wrapped in messages dict"""
        if not self.enabled:
            return {'messages': []}
        
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            content = response['Body'].read().decode('utf-8')
            messages = json.loads(content)
            return {'messages': messages}
        except self.s3_client.exceptions.NoSuchKey:
            return {'messages': []}
        except Exception as e:
            print(f"S3 get messages error: {e}")
            return {'messages': []}
    
    def append_chat_message(self, s3_key, chat_id, tenant_id, message):
        """Append a new message to existing chat in S3"""
        if not self.enabled:
            return False
        
        try:
            messages = self.get_chat_messages(s3_key) if s3_key else []
            messages.append(message)
            
            new_s3_key = self.save_chat_messages(chat_id, tenant_id, messages)
            return new_s3_key
        except Exception as e:
            print(f"S3 append chat message error: {e}")
            return None

class StripeService:
    @staticmethod
    def create_checkout_session(tenant_id, plan, success_url, cancel_url):
        try:
            price_id = os.getenv(f'STRIPE_PRICE_{plan.upper()}')
            if not price_id:
                if plan == 'starter':
                    price_id = 'price_starter'
                elif plan == 'professional':
                    price_id = 'price_professional'
                else:
                    price_id = 'price_enterprise'
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card', 'ideal'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={'tenant_id': tenant_id, 'plan': plan}
            )
            return session
        except Exception as e:
            print(f"Stripe checkout error: {e}")
            return None
    
    @staticmethod
    def create_customer_portal_session(customer_id, return_url):
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session
        except Exception as e:
            print(f"Stripe portal error: {e}")
            return None

class EmailService:
    """
    Singleton Email Service
    
    CRITICAL for production deployment:
    - Uses thread-safe singleton pattern for consistency
    - Prevents multiple MailerSend API initializations
    - Ensures single email service instance across all requests
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Thread-safe singleton implementation"""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize only once per process (singleton pattern)"""
        # Skip if already initialized
        if self._initialized:
            return
            
        self.api_key = os.getenv('MAILERSEND_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@trial-3vz9dle4n8z4kj50.mlsender.net')
        self.from_name = os.getenv('FROM_NAME', 'Lexi CAO Meester')
        self.enabled = bool(self.api_key)
        self.api_url = "https://api.mailersend.com/v1/email"
        
        # TEST_EMAIL_OVERRIDE: Route all emails to this address for layout testing
        self.test_email_override = os.getenv('TEST_EMAIL_OVERRIDE', '')
        
        self._initialized = True
        
        if self.enabled:
            print(f"✓ MailerSend HTTP API initialized: {self.from_name} <{self.from_email}> (singleton)")
            if self.test_email_override:
                print(f"⚠️  TEST MODE: All emails redirected to {self.test_email_override}")
    
    def send_email(self, to_email, subject, html_content):
        """Send email via MailerSend HTTP API (stable, production-ready)"""
        if not self.enabled:
            print(f"Email not sent (MailerSend not configured): {subject} to {to_email}")
            return False
        
        # Override recipient for testing if TEST_EMAIL_OVERRIDE is set
        original_to_email = to_email
        if self.test_email_override:
            to_email = self.test_email_override
            print(f"📧 TEST MODE: Redirecting email from {original_to_email} to {to_email}")
        
        try:
            # Strip HTML tags for plain text version
            import re
            text_content = re.sub('<[^<]+?>', '', html_content)
            
            # Build email payload for HTTP API
            payload = {
                "from": {
                    "email": self.from_email,
                    "name": self.from_name
                },
                "to": [
                    {
                        "email": to_email
                    }
                ],
                "subject": subject,
                "text": text_content,
                "html": html_content
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            # Send email via HTTP POST
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 202:
                print(f"✓ Email sent successfully to {to_email} (subject: {subject})")
                return True
            else:
                print(f"MailerSend error: Status {response.status_code}, Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"MailerSend error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def send_welcome_email(self, user, tenant, login_url):
        """Send welcome email after successful signup (branded template)"""
        subject = "Welkom bij Lexi CAO Meester!"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">Welkom bij Lexi! 👋</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {user.first_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Je account is aangemaakt voor <strong style="color: #1a2332;">{tenant.company_name}</strong>. Lexi staat klaar om al je CAO vragen te beantwoorden!
                                    </p>
                                    <div style="background-color: #d4af37; border-radius: 8px; padding: 20px; margin: 24px 0; text-align: center;">
                                        <p style="margin: 0 0 12px 0; color: #1a2332; font-size: 18px; font-weight: 600;">Start nu met Lexi!</p>
                                        <a href="{login_url}" style="background: #1a2332; color: #d4af37; padding: 12px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600;">
                                            Inloggen →
                                        </a>
                                    </div>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <h3 style="margin: 0 0 12px 0; color: #1a2332; font-size: 16px; font-weight: 600;">Wat kun je met Lexi?</h3>
                                        <ul style="margin: 0; padding-left: 20px; color: #374151; line-height: 1.8;">
                                            <li>CAO vragen stellen en directe antwoorden krijgen</li>
                                            <li>Documenten genereren (contracten, brieven)</li>
                                            <li>Bestanden uploaden voor analyse</li>
                                            <li>Chat geschiedenis doorzoeken</li>
                                        </ul>
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                                        <strong style="color: #1a2332;">Lexi AI</strong> - Jouw Expert CAO Assistent
                                    </p>
                                    <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                                        Vragen? support@lexiai.nl
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(user.email, subject, html_content)
    
    def send_user_invitation_email(self, user, tenant, activation_url, admin_name):
        """Send invitation email with secure activation link (NO PASSWORD IN EMAIL!)"""
        subject = f"Je bent uitgenodigd voor Lexi CAO Meester bij {tenant.company_name}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">Welkom bij Lexi! 👋</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {user.first_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        {admin_name} heeft een account voor je aangemaakt bij <strong style="color: #1a2332;">{tenant.company_name}</strong>. 
                                        Je hebt nu toegang tot Lexi, jouw AI-assistent voor CAO-vragen.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <h3 style="margin: 0 0 12px 0; color: #1a2332; font-size: 18px; font-weight: 600;">🔐 Account Activeren</h3>
                                        <p style="margin: 0 0 16px 0; color: #374151; font-size: 14px; line-height: 1.6;">
                                            Klik op de knop hieronder om je account te activeren en je wachtwoord in te stellen.
                                        </p>
                                        <p style="margin: 0; color: #6b7280; font-size: 14px; line-height: 1.6;">
                                            <strong>Email:</strong> {user.email}
                                        </p>
                                    </div>
                                    <div style="background-color: #d4af37; border-radius: 8px; padding: 20px; margin: 24px 0; text-align: center;">
                                        <p style="margin: 0 0 12px 0; color: #1a2332; font-size: 18px; font-weight: 600;">Activeer je Account</p>
                                        <a href="{activation_url}" style="background: #1a2332; color: #d4af37; padding: 14px 40px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600; font-size: 16px;">
                                            Account Activeren →
                                        </a>
                                    </div>
                                    <div style="margin: 32px 0; padding: 24px; background-color: #f9fafb; border-radius: 8px;">
                                        <h3 style="margin: 0 0 16px 0; color: #1a2332; font-size: 16px; font-weight: 600;">✨ Wat kun je met Lexi?</h3>
                                        <ul style="margin: 0; padding-left: 20px; color: #374151; font-size: 14px; line-height: 2;">
                                            <li>Stel CAO-vragen en krijg direct antwoorden</li>
                                            <li>Gebaseerd op 1.000+ officiële documenten</li>
                                            <li>Upload eigen documenten voor analyse</li>
                                            <li>Genereer contracten en brieven</li>
                                        </ul>
                                    </div>
                                    <div style="background-color: #fef2f2; border-left: 4px solid #DC2626; border-radius: 8px; padding: 16px; margin: 24px 0;">
                                        <p style="margin: 0; color: #991b1b; font-size: 13px; line-height: 1.6;">
                                            <strong>⚠️ Veiligheid:</strong> Deze activatie link is 24 uur geldig en kan maar één keer worden gebruikt.
                                        </p>
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                                        <strong style="color: #1a2332;">Lexi AI</strong> - Jouw Expert CAO Assistent
                                    </p>
                                    <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                                        Vragen? support@lexiai.nl
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return self.send_email(user.email, subject, html_content)
    
    def send_password_reset_link_email(self, user, tenant, reset_url):
        """Send password reset link email (NO password in email - token-based)"""
        subject = "Wachtwoord resetten - Lexi CAO Meester"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <!-- Header -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">
                                        LEXI
                                    </h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">
                                        CAO MEESTER
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">
                                        🔒 Wachtwoord Reset Aangevraagd
                                    </h2>
                                    
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Hoi {user.first_name},
                                    </p>
                                    
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        We hebben een verzoek ontvangen om je wachtwoord te resetten voor je Lexi CAO Meester account bij <strong style="color: #1a2332;">{tenant.company_name}</strong>.
                                    </p>
                                    
                                    <!-- Reset Link Box -->
                                    <div style="background-color: #f9fafb; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <h3 style="margin: 0 0 16px 0; color: #1a2332; font-size: 18px; font-weight: 600;">
                                            🔑 Reset je wachtwoord
                                        </h3>
                                        
                                        <p style="margin: 0 0 16px 0; color: #6b7280; font-size: 14px; line-height: 1.5;">
                                            Klik op de onderstaande knop om een nieuw wachtwoord in te stellen. Deze link is <strong>1 uur geldig</strong> en kan maar <strong>één keer gebruikt</strong> worden.
                                        </p>
                                        
                                        <!-- CTA Button -->
                                        <table width="100%" cellpadding="0" cellspacing="0" style="margin: 16px 0;">
                                            <tr>
                                                <td align="center">
                                                    <a href="{reset_url}" 
                                                       style="display: inline-block; background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); color: #d4af37; text-decoration: none; padding: 16px 48px; border-radius: 8px; font-size: 16px; font-weight: 600; letter-spacing: 0.5px; box-shadow: 0 4px 12px rgba(26, 35, 50, 0.3);">
                                                        Wachtwoord Resetten →
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                        
                                        <p style="margin: 16px 0 0 0; color: #9ca3af; font-size: 12px; line-height: 1.5; word-break: break-all;">
                                            Of kopieer deze link: <br>
                                            <span style="color: #6b7280;">{reset_url}</span>
                                        </p>
                                    </div>
                                    
                                    <!-- Security Notice -->
                                    <div style="margin: 32px 0; padding: 20px; background-color: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 8px;">
                                        <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.6;">
                                            <strong>⚡ Veiligheidswaarschuwing:</strong> Heb je deze wachtwoordreset NIET aangevraagd? Negeer deze email en je account blijft veilig. Neem contact op met je administrator als je dit verdacht vindt.
                                        </p>
                                    </div>
                                    
                                    <div style="margin: 24px 0; padding: 16px; background-color: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 8px;">
                                        <p style="margin: 0; color: #1e40af; font-size: 13px; line-height: 1.6;">
                                            💡 <strong>Tip:</strong> Deze link werkt maar 1 keer en verloopt over 1 uur. Als de link niet meer werkt, kun je een nieuwe aanvragen.
                                        </p>
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                                        Veilig wachtwoord resetten! 🔐
                                    </p>
                                    <p style="margin: 0; color: #9ca3af; font-size: 13px;">
                                        Het <strong style="color: #d4af37;">Lexi AI</strong> Team
                                    </p>
                                    
                                    <p style="margin: 24px 0 0 0; color: #9ca3af; font-size: 12px; line-height: 1.6;">
                                        Deze email is verstuurd naar {user.email}<br>
                                        omdat er een wachtwoordreset is aangevraagd.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return self.send_email(user.email, subject, html_content)
    
    def send_password_reset_email(self, user, tenant, new_password, login_url):
        """Send password reset email with new credentials"""
        subject = "Je wachtwoord is gereset - Lexi CAO Meester"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <!-- Header -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">
                                        LEXI
                                    </h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">
                                        CAO MEESTER
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">
                                        🔒 Je wachtwoord is gereset
                                    </h2>
                                    
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Hoi {user.first_name},
                                    </p>
                                    
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Je wachtwoord voor je Lexi CAO Meester account bij <strong style="color: #1a2332;">{tenant.company_name}</strong> is gereset.
                                    </p>
                                    
                                    <!-- New Password Box -->
                                    <div style="background-color: #f9fafb; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <h3 style="margin: 0 0 16px 0; color: #1a2332; font-size: 18px; font-weight: 600;">
                                            🔑 Je nieuwe wachtwoord
                                        </h3>
                                        
                                        <div style="background-color: #ffffff; padding: 16px; border-radius: 4px; border: 2px solid #d4af37; margin: 16px 0;">
                                            <p style="margin: 0; color: #6b7280; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">
                                                Nieuw Wachtwoord:
                                            </p>
                                            <p style="margin: 8px 0 0 0; color: #1a2332; font-size: 20px; font-family: 'Courier New', monospace; font-weight: 700; letter-spacing: 1px;">
                                                {new_password}
                                            </p>
                                        </div>
                                        
                                        <p style="margin: 16px 0 0 0; color: #6b7280; font-size: 13px; line-height: 1.5;">
                                            ⚠️ <strong>Belangrijk:</strong> Wijzig dit wachtwoord direct na inloggen via je profielinstellingen voor extra veiligheid.
                                        </p>
                                    </div>
                                    
                                    <!-- CTA Button -->
                                    <table width="100%" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
                                        <tr>
                                            <td align="center">
                                                <a href="{login_url}" 
                                                   style="display: inline-block; background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); color: #d4af37; text-decoration: none; padding: 16px 48px; border-radius: 8px; font-size: 16px; font-weight: 600; letter-spacing: 0.5px; box-shadow: 0 4px 12px rgba(26, 35, 50, 0.3);">
                                                    Inloggen →
                                                </a>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <!-- Security Notice -->
                                    <div style="margin: 32px 0; padding: 20px; background-color: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 8px;">
                                        <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.6;">
                                            <strong>⚡ Veiligheids tip:</strong> Heb je deze wachtwoordreset niet aangevraagd? Neem dan direct contact op met je administrator.
                                        </p>
                                    </div>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                                        Veilig inloggen! 🔐
                                    </p>
                                    <p style="margin: 0; color: #9ca3af; font-size: 13px;">
                                        Het <strong style="color: #d4af37;">Lexi AI</strong> Team
                                    </p>
                                    
                                    <p style="margin: 24px 0 0 0; color: #9ca3af; font-size: 12px; line-height: 1.6;">
                                        Deze email is verstuurd naar {user.email}<br>
                                        omdat je wachtwoord is gereset.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        return self.send_email(user.email, subject, html_content)
    
    def send_payment_failed_email(self, tenant):
        subject = "⚠️ Betaling mislukt"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>⚠️ Betaling mislukt</h2>
            <p>Hoi {tenant.contact_name},</p>
            <p>We konden je laatste betaling voor Lexi CAO Meester niet verwerken.</p>
            <p>Update je betaalmethode om actief te blijven en toegang te behouden tot Lexi.</p>
            <p><a href="https://{tenant.subdomain}.lex-cao.replit.app/admin/billing" 
               style="background: #DC2626; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
               Betaalmethode Updaten →
            </a></p>
            <br>
            <p>Groeten,<br>Het Lexi team</p>
        </body>
        </html>
        """
        return self.send_email(tenant.contact_email, subject, html_content)
    
    def send_trial_expiring_email(self, tenant, days_left):
        subject = f"⏰ Je trial verloopt over {days_left} dagen"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>⏰ Je trial verloopt binnenkort</h2>
            <p>Hoi {tenant.contact_name},</p>
            <p>Je 14-daagse trial van Lexi CAO Meester verloopt over {days_left} dagen.</p>
            <p>Upgrade nu naar een betaald plan om toegang te behouden tot Lexi en al je chat geschiedenis.</p>
            <p><strong>Beschikbare plannen:</strong></p>
            <ul>
                <li>Professional: €499/maand (5 users, unlimited questions)</li>
                <li>Enterprise: €1.199/maand (unlimited users, unlimited questions)</li>
            </ul>
            <p><a href="https://{tenant.subdomain}.lex-cao.replit.app/admin/billing" 
               style="background: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
               Upgrade Nu →
            </a></p>
            <br>
            <p>Groeten,<br>Het Lexi team</p>
        </body>
        </html>
        """
        return self.send_email(tenant.contact_email, subject, html_content)
    
    def send_payment_success_email(self, tenant, plan, amount):
        """Send email after successful payment/subscription activation"""
        subject = f"✅ Welkom bij Lexi CAO Meester - {plan.title()} Plan Actief!"
        
        plan_details = {
            'starter': ('Starter', '€499', '3 users'),
            'professional': ('Professional', '€599', '5 users'),
            'enterprise': ('Enterprise', '€1.199', 'Unlimited users')
        }
        
        plan_name, plan_price, plan_users = plan_details.get(plan, ('Professional', '€599', '5 users'))
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">Betaling Succesvol! 🎉</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {tenant.contact_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Bedankt voor je betaling! Je <strong>{plan_name}</strong> abonnement is nu actief voor <strong>{tenant.company_name}</strong>.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <h3 style="margin: 0 0 16px 0; color: #1a2332; font-size: 18px; font-weight: 600;">📋 Abonnement Details</h3>
                                        <ul style="margin: 0; padding-left: 20px; color: #374151; line-height: 1.8;">
                                            <li><strong>Plan:</strong> {plan_name}</li>
                                            <li><strong>Prijs:</strong> {plan_price}/maand</li>
                                            <li><strong>Gebruikers:</strong> {plan_users}</li>
                                            <li><strong>Bedrijf:</strong> {tenant.company_name}</li>
                                        </ul>
                                    </div>
                                    <div style="background-color: #d4af37; border-radius: 8px; padding: 20px; margin: 24px 0; text-align: center;">
                                        <p style="margin: 0 0 12px 0; color: #1a2332; font-size: 18px; font-weight: 600;">Start nu met Lexi!</p>
                                        <a href="https://{tenant.subdomain}.lexiai.nl/chat" style="background: #1a2332; color: #d4af37; padding: 12px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600;">
                                            Naar Chat →
                                        </a>
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                                        <strong style="color: #1a2332;">Lexi AI</strong> - Jouw Expert CAO Assistent
                                    </p>
                                    <p style="margin: 0; color: #9ca3af; font-size: 12px;">
                                        Vragen? Neem contact op via support@lexiai.nl
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(tenant.contact_email, subject, html_content)
    
    def send_subscription_updated_email(self, tenant, old_plan, new_plan):
        """Send email when subscription plan changes"""
        subject = f"✅ Je abonnement is gewijzigd naar {new_plan.title()}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">Abonnement Gewijzigd</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {tenant.contact_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Je abonnement voor <strong>{tenant.company_name}</strong> is gewijzigd.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">Oud plan:</p>
                                        <p style="margin: 0 0 16px 0; color: #1a2332; font-size: 18px; font-weight: 600;">{old_plan.title()}</p>
                                        <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">Nieuw plan:</p>
                                        <p style="margin: 0; color: #d4af37; font-size: 18px; font-weight: 600;">{new_plan.title()}</p>
                                    </div>
                                    <p style="margin: 0; color: #6b7280; font-size: 14px; text-align: center;">
                                        De wijziging is direct actief.
                                    </p>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                                        <strong style="color: #1a2332;">Lexi AI</strong>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(tenant.contact_email, subject, html_content)
    
    def send_subscription_cancelled_email(self, tenant):
        """Send email when subscription is cancelled"""
        subject = "Je abonnement is geannuleerd"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">Abonnement Geannuleerd</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {tenant.contact_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Je abonnement voor <strong>{tenant.company_name}</strong> is geannuleerd.
                                    </p>
                                    <div style="background-color: #fef2f2; border-left: 4px solid #DC2626; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <p style="margin: 0 0 12px 0; color: #1a2332; font-size: 16px; font-weight: 600;">Wat betekent dit?</p>
                                        <ul style="margin: 0; padding-left: 20px; color: #374151; line-height: 1.8;">
                                            <li>Je toegang blijft actief tot het einde van je huidige factuurperiode</li>
                                            <li>Daarna wordt je account gedeactiveerd</li>
                                            <li>Al je chat geschiedenis blijft bewaard</li>
                                        </ul>
                                    </div>
                                    <p style="margin: 24px 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6; text-align: center;">
                                        Mocht je van gedachten veranderen, je bent altijd welkom terug!
                                    </p>
                                    <div style="text-align: center;">
                                        <a href="https://{tenant.subdomain}.lexiai.nl/admin/billing" style="background: #d4af37; color: #1a2332; padding: 12px 32px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600;">
                                            Heractiveer Abonnement
                                        </a>
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0; color: #6b7280; font-size: 14px;">
                                        Vragen? support@lexiai.nl
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(tenant.contact_email, subject, html_content)
    
    def send_ideal_payment_link_email(self, user, tenant, invoice_url, amount, due_date):
        """Send monthly iDEAL payment link email"""
        subject = f"💳 Maandelijkse betaling - {amount} via iDEAL"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">💳 Maandelijkse betaling via iDEAL</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {user.first_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Het is tijd voor je maandelijkse betaling van <strong>{amount}</strong> voor {tenant.company_name}.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <p style="margin: 0 0 12px 0; color: #1a2332; font-size: 16px; font-weight: 600;">Factuurdetails:</p>
                                        <div style="color: #374151; line-height: 1.8;">
                                            <p style="margin: 0 0 8px 0;"><strong>Bedrag:</strong> {amount}</p>
                                            <p style="margin: 0 0 8px 0;"><strong>Vervaldatum:</strong> {due_date}</p>
                                            <p style="margin: 0;"><strong>Betaalmethode:</strong> iDEAL</p>
                                        </div>
                                    </div>
                                    <div style="background-color: #fef9f3; border-radius: 8px; padding: 20px; margin: 24px 0;">
                                        <p style="margin: 0 0 12px 0; color: #92400e; font-size: 14px; line-height: 1.6;">
                                            ℹ️ <strong>Let op:</strong> Je hebt gekozen voor handmatige betaling via iDEAL. Klik op de knop hieronder om je betaling te voltooien via je bank.
                                        </p>
                                        <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.6;">
                                            <strong>Wil je automatische incasso?</strong> Stuur een email naar <a href="mailto:support@lexiai.nl" style="color: #d4af37;">support@lexiai.nl</a> voor SEPA automatische incasso (over 30 dagen beschikbaar).
                                        </p>
                                    </div>
                                    <div style="text-align: center; margin: 32px 0;">
                                        <a href="{invoice_url}" style="background: #d4af37; color: #1a2332; padding: 16px 48px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: 600; font-size: 18px; box-shadow: 0 4px 6px rgba(212, 175, 55, 0.3);">
                                            Betaal nu via iDEAL
                                        </a>
                                    </div>
                                    <p style="margin: 24px 0 0 0; color: #6b7280; font-size: 14px; line-height: 1.6; text-align: center;">
                                        Deze betaallink is 30 dagen geldig. Betaal op tijd om toegang te behouden.
                                    </p>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">
                                        Vragen over je factuur?
                                    </p>
                                    <p style="margin: 0; color: #6b7280; font-size: 14px;">
                                        <a href="mailto:support@lexiai.nl" style="color: #d4af37; text-decoration: none;">support@lexiai.nl</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(user.email, subject, html_content)
    
    def send_role_changed_email(self, user, tenant, new_role, changed_by):
        """Send email when user role is changed"""
        subject = f"Je rol is gewijzigd in Lexi CAO Meester"
        
        role_names = {
            'USER': 'Gebruiker',
            'TENANT_ADMIN': 'Administrator'
        }
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">Je Rol is Gewijzigd</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {user.first_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        {changed_by} heeft je rol gewijzigd in <strong>{tenant.company_name}</strong>.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0; text-align: center;">
                                        <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">Je nieuwe rol:</p>
                                        <p style="margin: 0; color: #1a2332; font-size: 24px; font-weight: 600;">{role_names.get(new_role, new_role)}</p>
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0; color: #6b7280; font-size: 14px;">
                                        <strong style="color: #1a2332;">Lexi AI</strong>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(user.email, subject, html_content)
    
    def send_account_deactivated_email(self, user, tenant, deactivated_by):
        """Send email when user account is deactivated"""
        subject = "Je account is gedeactiveerd"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">Account Gedeactiveerd</h2>
                                    <p style="margin: 0 0 16px 0; color: #374151; font-size: 16px; line-height: 1.6;">Hoi {user.first_name},</p>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        {deactivated_by} heeft je account gedeactiveerd bij <strong>{tenant.company_name}</strong>.
                                    </p>
                                    <div style="background-color: #fef2f2; border-left: 4px solid #DC2626; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <p style="margin: 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                            Je hebt geen toegang meer tot Lexi CAO Meester. Neem contact op met je administrator voor meer informatie.
                                        </p>
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0; color: #6b7280; font-size: 14px;">
                                        <strong style="color: #1a2332;">Lexi AI</strong>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(user.email, subject, html_content)
    
    def send_ticket_resolved_email(self, ticket, tenant):
        """Send email when support ticket is resolved"""
        subject = f"Support ticket #{ticket.id} opgelost"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f3f4f6;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f3f4f6; padding: 40px 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <tr>
                                <td style="background: linear-gradient(135deg, #1a2332 0%, #2a3f5f 100%); padding: 40px 30px; text-align: center;">
                                    <h1 style="margin: 0; color: #d4af37; font-size: 32px; font-weight: 700; letter-spacing: 2px;">LEXI</h1>
                                    <p style="margin: 10px 0 0 0; color: #ffffff; font-size: 14px; letter-spacing: 1px;">CAO MEESTER</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="margin: 0 0 20px 0; color: #1a2332; font-size: 24px; font-weight: 600;">✅ Ticket Opgelost</h2>
                                    <p style="margin: 0 0 24px 0; color: #374151; font-size: 16px; line-height: 1.6;">
                                        Je support ticket is opgelost.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #d4af37; border-radius: 8px; padding: 24px; margin: 24px 0;">
                                        <p style="margin: 0 0 8px 0; color: #6b7280; font-size: 14px;">Ticket:</p>
                                        <p style="margin: 0 0 16px 0; color: #1a2332; font-size: 18px; font-weight: 600;">#{ticket.id} - {ticket.subject}</p>
                                    </div>
                                    <p style="margin: 0; color: #374151; font-size: 14px; text-align: center;">
                                        Heb je nog vragen? Open een nieuw ticket via het support menu.
                                    </p>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color: #f9fafb; padding: 30px; text-align: center; border-top: 1px solid #e5e7eb;">
                                    <p style="margin: 0; color: #6b7280; font-size: 14px;">
                                        <strong style="color: #1a2332;">Lexi AI Support</strong>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        return self.send_email(ticket.email, subject, html_content)

vertex_ai_service = VertexAIService()
s3_service = S3Service()
email_service = EmailService()
