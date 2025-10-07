import os
import json
import boto3
import stripe
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid

stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')

class VertexAIService:
    def __init__(self):
        project = os.getenv('GOOGLE_CLOUD_PROJECT')
        location = os.getenv('VERTEX_AI_LOCATION', 'europe-west1')
        agent_id = os.getenv('VERTEX_AI_AGENT_ID')
        
        self.agent = None
        self.enabled = False
        
        if project and agent_id:
            try:
                import vertexai
                credentials_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
                if credentials_json:
                    credentials_dict = json.loads(credentials_json)
                    from google.oauth2 import service_account
                    credentials = service_account.Credentials.from_service_account_info(credentials_dict)
                    vertexai.init(project=project, location=location, credentials=credentials)
                else:
                    vertexai.init(project=project, location=location)
                
                try:
                    from vertexai.preview import reasoning_engines
                    self.agent = reasoning_engines.ReasoningEngine(agent_id=agent_id)
                    self.enabled = True
                    print("Vertex AI agent initialized successfully")
                except ImportError:
                    from vertexai.generative_models import GenerativeModel
                    self.model = GenerativeModel('gemini-pro')
                    self.enabled = True
                    self.use_fallback = True
                    print("Vertex AI using Gemini fallback")
            except Exception as e:
                print(f"Vertex AI initialization failed: {e}")
                self.enabled = False
        else:
            print("Vertex AI not configured (missing credentials)")
            self.enabled = False
    
    def chat(self, message, context=None):
        if not self.enabled:
            return "LEX is momenteel niet beschikbaar. Configureer de Google Vertex AI credentials in de environment variables om LEX te activeren. Je kunt vragen stellen zodra de configuratie is voltooid."
        
        try:
            if context:
                full_message = f"{context}\n\n{message}"
            else:
                full_message = message
            
            if self.agent:
                response = self.agent.query(input=full_message)
                return response.text if hasattr(response, 'text') else str(response)
            elif hasattr(self, 'model'):
                prompt = f"Je bent LEX, een expert op het gebied van Nederlandse CAO's (Collectieve Arbeidsovereenkomsten). Beantwoord de volgende vraag op basis van CAO kennis:\n\n{full_message}"
                response = self.model.generate_content(prompt)
                return response.text if hasattr(response, 'text') else str(response)
            else:
                return "LEX is momenteel niet correct geconfigureerd."
        except Exception as e:
            print(f"Vertex AI chat error: {e}")
            return f"Er ging iets mis bij het verwerken van je vraag. LEX heeft wellicht nog geen toegang tot de CAO database. Configureer de Vertex AI agent voor volledige functionaliteit."

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
    
    def send_trial_expiring_email(self, tenant):
        subject = "Je LEX trial loopt over 3 dagen af"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Je trial loopt bijna af</h2>
            <p>Hoi {tenant.contact_name},</p>
            <p>Je 14-daagse trial van LEX CAO Expert loopt over 3 dagen af.</p>
            <p>Upgrade nu om door te gaan met LEX en toegang te houden tot al je CAO kennis.</p>
            <p><a href="https://{tenant.subdomain}.lex-cao.replit.app/admin/billing" 
               style="background: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
               Upgrade naar Professional →
            </a></p>
            <br>
            <p>Groeten,<br>Het LEX team</p>
        </body>
        </html>
        """
        return self.send_email(tenant.contact_email, subject, html_content)
    
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

vertex_ai_service = VertexAIService()
s3_service = S3Service()
email_service = EmailService()
