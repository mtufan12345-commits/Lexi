import os
import json
import boto3
import stripe
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
import io
from PyPDF2 import PdfReader
from docx import Document

stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')

class VertexAIService:
    def __init__(self):
        credentials_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        
        try:
            from google import genai
            from google.genai import types
            import tempfile
            
            self.genai = genai
            self.types = types
            
            if isinstance(credentials_json, str):
                credentials_dict = json.loads(credentials_json)
                temp_cred_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
                json.dump(credentials_dict, temp_cred_file)
                temp_cred_file.close()
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_cred_file.name
            
            self.client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("VERTEX_AI_LOCATION"),
            )
            
            self.model = "gemini-2.5-pro"
            self.rag_corpus = os.environ.get("VERTEX_AI_AGENT_ID")
            
            self.system_instruction = """Je bent Lex - Expert Loonadministrateur voor UZB (NBBU CAO).

KERN INSTRUCTIES:
- Gebruik je volledige kennisbank om de beste antwoorden te geven
- UZB hanteert NBBU CAO als standaard
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
            print("Vertex AI with google-genai SDK initialized successfully")
        except Exception as e:
            print(f"Vertex AI initialization failed: {e}")
            self.enabled = False

    def chat(self, message, conversation_history=None):
        if not self.enabled:
            return "LEX is momenteel niet beschikbaar. Configureer de Google Vertex AI credentials in de environment variables om LEX te activeren."
        
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
                            similarity_top_k=20,
                        )
                    )
                )
            ]
            
            config = self.types.GenerateContentConfig(
                temperature=1,
                top_p=0.95,
                max_output_tokens=65535,
                tools=tools,
                system_instruction=[self.types.Part.from_text(text=self.system_instruction)],
                thinking_config=self.types.ThinkingConfig(thinking_budget=-1),
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
            print(f"Vertex AI chat error: {e}")
            return f"Er ging iets mis bij het verwerken van je vraag: {str(e)}"

class S3Service:
    def __init__(self):
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
            except Exception as e:
                print(f"S3 initialization failed: {e}")
                self.enabled = False
        else:
            self.enabled = False
    
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
                price_id = 'price_professional' if plan == 'professional' else 'price_enterprise'
            
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
    def __init__(self):
        self.api_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@lex-cao.nl')
        self.enabled = bool(self.api_key)
    
    def send_email(self, to_email, subject, html_content):
        if not self.enabled:
            print(f"Email not sent (SendGrid not configured): {subject} to {to_email}")
            return False
        
        try:
            message = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )
            sg = SendGridAPIClient(self.api_key)
            response = sg.send(message)
            return response.status_code in [200, 202]
        except Exception as e:
            print(f"SendGrid error: {e}")
            return False
    
    def send_welcome_email(self, user, tenant, login_url):
        subject = "Welkom bij LEX CAO Expert!"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Welkom bij LEX CAO Expert! 🤖</h2>
            <p>Hoi {user.first_name},</p>
            <p>Je account is aangemaakt voor <strong>{tenant.company_name}</strong>.</p>
            <p>Login hier: <a href="{login_url}">{login_url}</a></p>
            <p>LEX staat klaar om al je CAO vragen te beantwoorden!</p>
            <br>
            <p>Veel succes,<br>Het LEX team</p>
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
            <p>We konden je laatste betaling voor LEX CAO Expert niet verwerken.</p>
            <p>Update je betaalmethode om actief te blijven en toegang te behouden tot LEX.</p>
            <p><a href="https://{tenant.subdomain}.lex-cao.replit.app/admin/billing" 
               style="background: #DC2626; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
               Betaalmethode Updaten →
            </a></p>
            <br>
            <p>Groeten,<br>Het LEX team</p>
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
            <p>Je 14-daagse trial van LEX CAO Expert verloopt over {days_left} dagen.</p>
            <p>Upgrade nu naar een betaald plan om toegang te behouden tot LEX en al je chat geschiedenis.</p>
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
            <p>Groeten,<br>Het LEX team</p>
        </body>
        </html>
        """
        return self.send_email(tenant.contact_email, subject, html_content)

vertex_ai_service = VertexAIService()
s3_service = S3Service()
email_service = EmailService()
