import os
import re
import tempfile
from flask import Flask, render_template, request, redirect, url_for, jsonify, g, session, flash, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from models import db, SuperAdmin, Tenant, User, Chat, Message, Subscription, Template, UploadedFile, Artifact, SupportTicket, SupportReply
from services import vertex_ai_service, s3_service, email_service, StripeService
import stripe
from datetime import datetime, timedelta
import secrets
from functools import wraps
from markitdown import MarkItDown
import pytesseract
from pdf2image import convert_from_path

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.secret_key = os.environ.get("SESSION_SECRET") or os.environ.get("SECRET_KEY") or "dev-secret-key-change-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['WTF_CSRF_ENABLED'] = os.getenv('ENABLE_CSRF', 'false').lower() == 'true'
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['WTF_CSRF_SSL_STRICT'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True

if app.config['WTF_CSRF_ENABLED']:
    csrf = CSRFProtect(app)
    print("CSRF Protection enabled")
else:
    print("CSRF Protection disabled for development")
    @app.context_processor
    def csrf_token_processor():
        return {'csrf_token': lambda: ''}

db.init_app(app)

# Initialize Stripe globally
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
print(f"Stripe initialized: {stripe.api_key is not None}")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    if session.get('is_super_admin'):
        return SuperAdmin.query.get(int(user_id))
    return User.query.get(int(user_id))

def get_max_users_for_tier(tier):
    """Get max users allowed for a subscription tier"""
    tier_limits = {
        'starter': 5,
        'professional': 10,
        'enterprise': 999999
    }
    return tier_limits.get(tier, 5)

def cleanup_stale_pending_signups():
    """Clean up pending signups older than 24 hours"""
    from models import PendingSignup
    from datetime import datetime, timedelta
    
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    stale_signups = PendingSignup.query.filter(PendingSignup.created_at < cutoff_time).all()
    
    count = len(stale_signups)
    if count > 0:
        for signup in stale_signups:
            db.session.delete(signup)
        db.session.commit()
        print(f"🧹 Cleaned up {count} stale pending signups")
    
    return count

@app.before_request
def load_tenant():
    g.tenant = None
    g.is_super_admin = session.get('is_super_admin', False)
    
    if g.is_super_admin:
        return
    
    # Development mode: tenant via session
    tenant_id = session.get('tenant_id')
    print(f"[DEBUG] load_tenant - tenant_id from session: {tenant_id}")
    if tenant_id:
        g.tenant = Tenant.query.get(tenant_id)
        print(f"[DEBUG] Tenant loaded from session: {g.tenant.company_name if g.tenant else None}")
        return
    
    # Production mode: tenant via subdomain
    host = request.host.split(':')[0]
    parts = host.split('.')
    print(f"[DEBUG] Host parts: {parts}")
    
    if len(parts) >= 2 and parts[0] not in ['www', 'lex-cao', 'lex-cao-expert']:
        subdomain = parts[0]
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if tenant:
            g.tenant = tenant
            print(f"[DEBUG] Tenant loaded from subdomain: {tenant.company_name}")

def tenant_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.tenant:
            return "Tenant niet gevonden", 404
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.role == 'admin':
            flash('Je hebt geen toegang tot deze pagina.', 'danger')
            return redirect(url_for('chat_page'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not g.is_super_admin:
            return "Geen toegang", 403
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def add_cache_headers(response):
    """Add cache headers for faster page loads"""
    if request.endpoint and request.endpoint in ['index', 'pricing', 'login']:
        # Cache static pages for 5 minutes
        response.headers['Cache-Control'] = 'public, max-age=300'
    return response

@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/prijzen')
def pricing():
    return render_template('pricing.html')

@app.route('/algemene-voorwaarden')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')

def count_user_questions(user_id):
    """Count total questions asked by user using message_count with fallbacks"""
    user_chats = Chat.query.filter_by(user_id=user_id).all()
    question_count = 0
    
    for c in user_chats:
        if c.message_count and c.message_count > 0:
            # Use message_count if available (most reliable)
            # Divide by 2 since message_count includes both user and assistant messages
            question_count += (c.message_count + 1) // 2
        elif c.s3_messages_key:
            # Try S3 if message_count not set
            messages = s3_service.get_chat_messages(c.s3_messages_key)
            if messages:
                question_count += sum(1 for m in messages if m.get('role') == 'user')
            else:
                # S3 failed, try PostgreSQL
                db_messages = Message.query.filter_by(chat_id=c.id, role='user').count()
                question_count += db_messages
        else:
            # No S3, use PostgreSQL
            db_messages = Message.query.filter_by(chat_id=c.id, role='user').count()
            question_count += db_messages
    
    return question_count

@app.route('/signup/tenant', methods=['GET', 'POST'])
def signup_tenant():
    # Get tier and billing cycle from query params (from pricing page)
    tier = request.args.get('tier', 'starter')
    billing = request.args.get('billing', 'monthly')
    
    if request.method == 'POST':
        from stripe_config import get_price_id
        
        company_name = request.form.get('company_name') or ''
        contact_email = request.form.get('contact_email') or ''
        contact_name = request.form.get('contact_name') or ''
        password = request.form.get('password') or ''
        tier = request.form.get('tier', 'starter')
        billing = request.form.get('billing', 'monthly')
        
        # Validate inputs
        if not all([company_name, contact_email, contact_name, password]):
            flash('Alle velden zijn verplicht.', 'danger')
            return render_template('signup_tenant.html', tier=tier, billing=billing)
        
        # Check if email already exists
        existing_user = User.query.filter_by(email=contact_email).first()
        if existing_user:
            flash('Dit email adres is al in gebruik.', 'danger')
            return render_template('signup_tenant.html', tier=tier, billing=billing)
        
        # Get Stripe Price ID
        price_id = get_price_id(tier, billing)
        if not price_id or not price_id.startswith('price_'):
            app.logger.error(f"Invalid or missing Stripe Price ID for tier={tier}, billing={billing}, price_id={price_id}")
            flash('Ongeldige pricing optie. Neem contact op met support.', 'danger')
            return render_template('signup_tenant.html', tier=tier, billing=billing)
        
        # Create Stripe Checkout Session FIRST to get session ID
        try:
            from models import PendingSignup
            import stripe as stripe_lib
            
            # Get base URL (works in both dev and production)
            base_url = request.host_url.rstrip('/')
            
            # Ensure Stripe is initialized
            stripe_lib.api_key = os.getenv('STRIPE_SECRET_KEY')
            
            checkout_session = stripe_lib.checkout.Session.create(
                payment_method_types=['card', 'ideal'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f"{base_url}/signup/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{base_url}/signup/cancel?session_id={{CHECKOUT_SESSION_ID}}",
                customer_email=contact_email,
                metadata={
                    'signup_email': contact_email,
                    'tier': tier,
                    'billing': billing
                }
            )
            
            # Store signup data in database (server-side) with checkout session ID
            pending_signup = PendingSignup(
                checkout_session_id=checkout_session.id,
                email=contact_email,
                company_name=company_name,
                contact_name=contact_name,
                tier=tier,
                billing=billing
            )
            pending_signup.set_password(password)  # Hash the password
            db.session.add(pending_signup)
            db.session.commit()
            
            # Redirect to Stripe Checkout
            return redirect(checkout_session.url, code=303)
            
        except Exception as e:
            app.logger.exception(f"Stripe checkout error for tier={tier}, billing={billing}, price_id={price_id}: {str(e)}")
            
            # Provide more specific error messages
            error_msg = str(e)
            if 'No such price' in error_msg:
                flash('De gekozen prijsoptie is niet geldig. Neem contact op met support.', 'danger')
            elif 'API key' in error_msg:
                flash('Betaalconfiguratie is niet correct ingesteld. Neem contact op met support.', 'danger')
            else:
                flash('Er ging iets mis met de betaling. Probeer het opnieuw.', 'danger')
            
            return render_template('signup_tenant.html', tier=tier, billing=billing)
    
    # GET request - show signup form
    return render_template('signup_tenant.html', tier=tier, billing=billing)

@app.route('/signup/success')
def signup_success():
    """Success page after Stripe payment - account will be created via webhook"""
    session_id = request.args.get('session_id')
    
    if not session_id:
        flash('Geen geldige sessie gevonden.', 'danger')
        return redirect(url_for('index'))
    
    # The webhook will create the account, just show success message
    return render_template('signup_success.html', session_id=session_id)

@app.route('/signup/cancel')
def signup_cancel():
    """Cancel page if user cancels Stripe payment"""
    from models import PendingSignup
    
    # Try to clean up pending signup if session_id is provided
    session_id = request.args.get('session_id')
    if session_id:
        pending = PendingSignup.query.filter_by(checkout_session_id=session_id).first()
        if pending:
            db.session.delete(pending)
            db.session.commit()
    
    flash('Betaling geannuleerd. U kunt opnieuw proberen wanneer u klaar bent.', 'info')
    return redirect(url_for('pricing'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated and not g.is_super_admin:
        return redirect(url_for('chat_page'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password')
        
        print(f"Login attempt - Email: {email}")
        
        # Zoek user op basis van email (uniek over alle tenants)
        user = User.query.filter_by(email=email).first()
        print(f"User found: {user is not None}")
        
        if user and user.check_password(password):
            print("Password check passed")
            
            # Haal de tenant op van deze user
            tenant = Tenant.query.get(user.tenant_id)
            
            if not user.is_active:
                flash('Je account is gedeactiveerd.', 'danger')
                return render_template('login.html')
            
            if tenant.status not in ['trial', 'active']:
                flash('Je account is verlopen. Neem contact op met de administrator.', 'warning')
                return render_template('login.html')
            
            force_login = request.form.get('force_login') == 'true'
            
            if user.session_token and not force_login:
                return render_template('login.html', 
                                     show_force_login=True, 
                                     email=email)
            
            user.session_token = secrets.token_hex(32)
            db.session.commit()
            
            login_user(user)
            session['tenant_id'] = tenant.id  # Zet tenant_id automatisch in session
            session['session_token'] = user.session_token
            session['is_super_admin'] = False
            
            if force_login:
                flash('Oude sessie uitgelogd. Je bent nu ingelogd.', 'success')
            
            print(f"Login successful - Tenant: {tenant.company_name}")
            return redirect(url_for('chat_page'))
        
        print("Login failed - invalid credentials")
        flash('Ongeldige email of wachtwoord.', 'danger')
    
    return render_template('login.html')

@app.route('/super-admin/login', methods=['GET', 'POST'])
def super_admin_login():
    if request.method == 'POST':
        email = request.form.get('email') or ''
        password = request.form.get('password') or ''
        
        admin = SuperAdmin.query.filter_by(email=email).first()
        if admin and admin.check_password(password):
            login_user(admin)
            session['super_admin_id'] = admin.id
            session['is_super_admin'] = True
            return redirect(url_for('super_admin_dashboard'))
        
        flash('Ongeldige credentials.', 'danger')
    
    return render_template('super_admin_login.html')

@app.route('/select-tenant', methods=['GET', 'POST'])
@super_admin_required
def select_tenant():
    """Development/admin mode: manually select a tenant (alleen voor super admins)"""
    if request.method == 'POST':
        subdomain = request.form.get('subdomain')
        print(f"[DEBUG] select_tenant - subdomain: {subdomain}")
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if tenant:
            session['tenant_id'] = tenant.id
            session.modified = True  # Force session save
            print(f"[DEBUG] Tenant ID {tenant.id} saved to session")
            flash(f'Tenant geselecteerd: {tenant.company_name}', 'success')
            return redirect(url_for('login'))
        flash('Tenant niet gevonden', 'danger')
    
    tenants = Tenant.query.all()
    return render_template('select_tenant.html', tenants=tenants)

@app.route('/logout')
@login_required
def logout():
    if not g.is_super_admin and isinstance(current_user, User):
        current_user.session_token = None
        db.session.commit()
    
    logout_user()
    session.clear()
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
@tenant_required
def user_profile():
    if request.method == 'POST':
        new_email = request.form.get('email')
        
        if new_email != current_user.email:
            existing = User.query.filter_by(
                tenant_id=g.tenant.id,
                email=new_email
            ).first()
            if existing:
                flash('Dit e-mailadres is al in gebruik!', 'error')
                return redirect(url_for('user_profile'))
        
        current_user.first_name = request.form.get('first_name') or current_user.first_name
        current_user.last_name = request.form.get('last_name') or current_user.last_name
        current_user.email = new_email
        
        new_password = request.form.get('new_password') or ''
        if new_password:
            current_user.set_password(new_password)
        
        db.session.commit()
        flash('Profiel bijgewerkt!', 'success')
        return redirect(url_for('user_profile'))
    
    return render_template('user_profile.html', tenant=g.tenant, user=current_user)

@app.route('/api/profile/avatar', methods=['POST'])
@login_required
@tenant_required
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': 'Geen bestand'}), 400
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'Geen bestand geselecteerd'}), 400
    
    # Check file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    filename = file.filename or ''
    if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'error': 'Alleen afbeeldingen toegestaan (PNG, JPG, GIF, WEBP)'}), 400
    
    # Upload to S3
    s3_key = s3_service.upload_file(file, g.tenant.id, folder='avatars')
    if not s3_key:
        return jsonify({'error': 'Upload mislukt'}), 500
    
    # Get URL
    avatar_url = s3_service.get_file_url(s3_key)
    
    # Update user
    current_user.avatar_url = avatar_url
    db.session.commit()
    
    return jsonify({'success': True, 'avatar_url': avatar_url})

@app.route('/chat')
@login_required
@tenant_required
def chat_page():
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        flash('Je account is niet actief. Neem contact op met je beheerder.', 'warning')
        return redirect(url_for('index'))
    
    chats = Chat.query.filter_by(
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).order_by(Chat.updated_at.desc()).all()
    
    return render_template('chat.html', chats=chats, tenant=g.tenant, user=current_user)

@app.route('/api/chat/new', methods=['POST'])
@login_required
@tenant_required
def new_chat():
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        return jsonify({'error': 'Subscription niet actief'}), 403
    
    chat = Chat(
        tenant_id=g.tenant.id,
        user_id=current_user.id,
        title='Nieuwe chat'
    )
    db.session.add(chat)
    db.session.commit()
    
    # Associate any pending uploaded files (chat_id=NULL) with this new chat
    pending_files = UploadedFile.query.filter_by(
        tenant_id=g.tenant.id,
        user_id=current_user.id,
        chat_id=None
    ).all()
    
    if pending_files:
        for uploaded_file in pending_files:
            uploaded_file.chat_id = chat.id
        db.session.commit()
        print(f"[DEBUG] Associated {len(pending_files)} pending files with new chat {chat.id}")
    
    return jsonify({'id': chat.id, 'title': chat.title})

@app.route('/api/chat/<int:chat_id>', methods=['GET'])
@login_required
@tenant_required
def get_chat(chat_id):
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        return jsonify({'error': 'Subscription niet actief'}), 403
    
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    # Get messages from S3
    messages = []
    if chat.s3_messages_key:
        s3_messages = s3_service.get_chat_messages(chat.s3_messages_key)
        for idx, m in enumerate(s3_messages):
            msg_data = {
                'id': idx + 1,
                'role': m.get('role'),
                'content': m.get('content'),
                'created_at': m.get('created_at'),
                'feedback_rating': m.get('feedback_rating')
            }
            
            # Add attachments if present (user messages)
            if m.get('attachments'):
                msg_data['attachments'] = m.get('attachments')
            
            if m.get('role') == 'assistant':
                artifacts = Artifact.query.filter_by(message_id=idx + 1, chat_id=chat.id, tenant_id=g.tenant.id).all()
                if artifacts:
                    msg_data['artifacts'] = [{
                        'id': a.id,
                        'title': a.title,
                        'type': a.artifact_type,
                        'content': a.content
                    } for a in artifacts]
            
            messages.append(msg_data)
    
    return jsonify({'id': chat.id, 'title': chat.title, 'messages': messages})

@app.route('/api/chat/<int:chat_id>/message', methods=['POST'])
@login_required
@tenant_required
def send_message(chat_id):
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        return jsonify({'error': 'Subscription niet actief'}), 403
    
    print(f"[DEBUG] send_message called - chat_id: {chat_id}, user: {current_user.id}")
    
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    data = request.json
    user_message = data.get('message', '')
    print(f"[DEBUG] User message: {user_message}")
    
    # Get uploaded files for this chat
    uploaded_files = UploadedFile.query.filter_by(
        chat_id=chat.id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).all()
    
    # Create user message dict for S3 with file attachments
    user_msg_dict = {
        'role': 'user',
        'content': user_message,
        'created_at': datetime.utcnow().isoformat()
    }
    
    # Add file attachments to message ONLY for newly uploaded files
    # Files uploaded AFTER the last message should be shown as attachments
    # For subsequent messages, old files are still used for AI context but not shown as attachments
    if uploaded_files:
        # Get files uploaded after the last message (new uploads since last message)
        # Guard against None updated_at (legacy/migrated chats) - show all files if None
        if chat.message_count > 0 and chat.updated_at is not None:
            newly_uploaded = [f for f in uploaded_files if f.created_at > chat.updated_at]
        else:
            newly_uploaded = uploaded_files
        
        if newly_uploaded:
            user_msg_dict['attachments'] = [{
                'id': f.id,
                'filename': f.original_filename,
                'mime_type': f.mime_type
            } for f in newly_uploaded]
    
    # Append to S3
    s3_key = s3_service.append_chat_message(
        chat.s3_messages_key,
        chat.id,
        g.tenant.id,
        user_msg_dict
    )
    
    if not s3_key:
        return jsonify({'error': 'Kon bericht niet opslaan. Probeer het opnieuw.'}), 500
    
    chat.s3_messages_key = s3_key
    chat.message_count = (chat.message_count or 0) + 1
    
    if chat.message_count <= 1:
        chat.title = user_message[:50] + ('...' if len(user_message) > 50 else '')
    
    chat.updated_at = datetime.utcnow()
    db.session.commit()
    
    ai_message = user_message
    file_errors = []
    
    if uploaded_files:
        file_contents = []
        for uploaded_file in uploaded_files:
            print(f"[DEBUG] Processing file: {uploaded_file.original_filename}, type: {uploaded_file.mime_type}")
            # For PDF files, try extracted_text from database first
            if uploaded_file.mime_type == 'application/pdf':
                if uploaded_file.extracted_text and uploaded_file.extracted_text.strip():
                    # Use pre-extracted text if available and not empty
                    print(f"[DEBUG] Using extracted_text from database (length: {len(uploaded_file.extracted_text)})")
                    content = uploaded_file.extracted_text
                    file_contents.append(f"\n\n--- Bestand: {uploaded_file.original_filename} ---\n{content}\n--- Einde bestand ---\n")
                else:
                    # Fallback: try downloading from S3 for legacy PDFs or failed extractions
                    print(f"[DEBUG] No extracted_text, trying S3 fallback for {uploaded_file.original_filename}")
                    try:
                        content, error = s3_service.download_file_content(uploaded_file.s3_key, uploaded_file.mime_type)
                        if error:
                            print(f"[DEBUG] S3 error: {error}")
                            file_errors.append(f"{uploaded_file.original_filename}: {error}")
                        elif content:
                            print(f"[DEBUG] S3 fallback successful, content length: {len(content)}")
                            file_contents.append(f"\n\n--- Bestand: {uploaded_file.original_filename} ---\n{content}\n--- Einde bestand ---\n")
                        else:
                            print(f"[DEBUG] S3 returned empty content")
                    except Exception as e:
                        print(f"[DEBUG] Exception in S3 fallback: {str(e)}")
                        file_errors.append(f"{uploaded_file.original_filename}: Kon bestand niet lezen")
            else:
                # For non-PDF files, download from S3
                content, error = s3_service.download_file_content(uploaded_file.s3_key, uploaded_file.mime_type)
                if error:
                    file_errors.append(f"{uploaded_file.original_filename}: {error}")
                elif content:
                    file_contents.append(f"\n\n--- Bestand: {uploaded_file.original_filename} ---\n{content}\n--- Einde bestand ---\n")
        
        if file_contents:
            ai_message = f"{user_message}\n\n{''.join(file_contents)}"
            print(f"[DEBUG] Including {len(file_contents)} uploaded files in context")
        
        if file_errors and not file_contents:
            error_msg = "\n".join(file_errors)
            return jsonify({'response': f"⚠️ Kon geen bestanden lezen:\n{error_msg}\n\nProbeer andere bestanden.", 'has_errors': True})
    
    print("[DEBUG] Calling Vertex AI service...")
    lex_response = vertex_ai_service.chat(ai_message)
    print(f"[DEBUG] Lexi response: {lex_response[:100]}...")
    
    # Create assistant message dict for S3
    assistant_msg_dict = {
        'role': 'assistant',
        'content': lex_response,
        'created_at': datetime.utcnow().isoformat()
    }
    
    # Append to S3
    s3_key = s3_service.append_chat_message(
        chat.s3_messages_key,
        chat.id,
        g.tenant.id,
        assistant_msg_dict
    )
    
    if not s3_key:
        return jsonify({'error': 'Kon AI response niet opslaan. Probeer het opnieuw.'}), 500
    
    chat.s3_messages_key = s3_key
    chat.message_count = (chat.message_count or 0) + 1
    chat.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Store last message ID for artifacts (use message_count as ID)
    assistant_message_id = chat.message_count
    
    artifacts_created = []
    artifact_pattern = r'```artifact:(\w+)\s+title:([^\n]+)\n(.*?)```'
    matches = re.finditer(artifact_pattern, lex_response, re.DOTALL)
    
    artifacts_to_commit = []
    for match in matches:
        artifact_type = match.group(1).strip()
        title = match.group(2).strip()
        content = match.group(3).strip()
        
        s3_key = s3_service.upload_content(
            content=content,
            filename=f"{title}.txt",
            tenant_id=g.tenant.id,
            folder='artifacts'
        )
        
        if s3_key:
            artifact = Artifact(
                tenant_id=g.tenant.id,
                chat_id=chat.id,
                message_id=assistant_message_id,
                title=title,
                content=content,
                artifact_type=artifact_type,
                s3_key=s3_key
            )
            db.session.add(artifact)
            artifacts_to_commit.append(artifact)
    
    if artifacts_to_commit:
        db.session.commit()
        for artifact in artifacts_to_commit:
            artifacts_created.append({
                'id': artifact.id,
                'title': artifact.title,
                'type': artifact.artifact_type,
                'content': artifact.content
            })
        print(f"[DEBUG] Created {len(artifacts_created)} artifacts")
    
    print("[DEBUG] Response sent successfully")
    return jsonify({
        'response': lex_response,
        'artifacts': artifacts_created,
        'message_id': assistant_message_id,
        'feedback_rating': None
    })

@app.route('/api/chat/<int:chat_id>/rename', methods=['POST'])
@login_required
@tenant_required
def rename_chat(chat_id):
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    data = request.json or {}
    new_title = data.get('title', '').strip()
    
    if new_title:
        chat.title = new_title
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False}), 400

@app.route('/api/chat/<int:chat_id>/delete', methods=['POST', 'DELETE'])
@login_required
@tenant_required
def delete_chat(chat_id):
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    # Delete uploaded files and their S3 objects
    uploaded_files = UploadedFile.query.filter_by(chat_id=chat.id).all()
    for uploaded_file in uploaded_files:
        if uploaded_file.s3_key:
            s3_service.delete_file(uploaded_file.s3_key)
        db.session.delete(uploaded_file)
    
    # Delete artifacts and their S3 objects
    artifacts = Artifact.query.filter_by(chat_id=chat.id).all()
    for artifact in artifacts:
        if artifact.s3_key:
            s3_service.delete_file(artifact.s3_key)
        db.session.delete(artifact)
    
    # Delete S3 messages file
    if chat.s3_messages_key:
        s3_service.delete_file(chat.s3_messages_key)
    
    # Finally delete the chat itself (cascade will delete messages)
    db.session.delete(chat)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/user/accept-first-chat-warning', methods=['POST'])
@login_required
def accept_first_chat_warning():
    """Mark that user has seen and accepted the first chat warning"""
    from datetime import datetime
    current_user.first_chat_warning_seen_at = datetime.now()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/chats', methods=['GET'])
@login_required
@tenant_required
def get_chats():
    chats = Chat.query.filter_by(
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).order_by(Chat.updated_at.desc()).all()
    
    return jsonify([{
        'id': chat.id,
        'title': chat.title,
        'updated_at': chat.updated_at.strftime('%d/%m %H:%M')
    } for chat in chats])

@app.route('/api/chats/search', methods=['POST'])
@login_required
@tenant_required
def search_chats():
    query = (request.json or {}).get('query', '').strip().lower()
    if not query:
        return jsonify([])
    
    chats = Chat.query.filter_by(
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).all()
    
    results = []
    for chat in chats:
        if query in chat.title.lower():
            results.append({
                'id': chat.id,
                'title': chat.title,
                'updated_at': chat.updated_at.strftime('%d/%m %H:%M'),
                'match_type': 'title'
            })
            continue
        
        if chat.s3_messages_key:
            messages_data = s3_service.get_messages(chat.s3_messages_key)
            if messages_data and 'messages' in messages_data:
                for msg in messages_data['messages']:
                    if query in msg.get('content', '').lower():
                        results.append({
                            'id': chat.id,
                            'title': chat.title,
                            'updated_at': chat.updated_at.strftime('%d/%m %H:%M'),
                            'match_type': 'content',
                            'snippet': msg.get('content', '')[:100] + '...'
                        })
                        break
    
    return jsonify(results)

@app.route('/api/chat/<int:chat_id>/export', methods=['GET'])
@login_required
@tenant_required
def export_chat_pdf(chat_id):
    from io import BytesIO
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    
    export_format = request.args.get('format', 'pdf')
    
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    # Collect messages
    messages = []
    if chat.s3_messages_key:
        messages_data = s3_service.get_messages(chat.s3_messages_key)
        if messages_data and 'messages' in messages_data:
            for msg in messages_data['messages']:
                role = "Jij" if msg.get('role') == "user" else "Lexi"
                timestamp = msg.get('timestamp', datetime.now().isoformat())
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp_str = dt.strftime('%d-%m-%Y %H:%M')
                except:
                    timestamp_str = timestamp
                messages.append({
                    'role': role,
                    'timestamp': timestamp_str,
                    'content': msg.get('content', '')
                })
    else:
        # Fallback naar oude Message tabel
        db_messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.created_at).all()
        for msg in db_messages:
            role = "Jij" if msg.role == "user" else "Lexi"
            messages.append({
                'role': role,
                'timestamp': msg.created_at.strftime('%d-%m-%Y %H:%M'),
                'content': msg.content
            })
    
    if export_format == 'pdf':
        # PDF Export - Available for ALL tiers
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a2332'),
            spaceAfter=20
        )
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.grey,
            spaceAfter=10
        )
        user_style = ParagraphStyle(
            'UserMessage',
            parent=styles['Normal'],
            fontSize=11,
            leftIndent=10,
            rightIndent=10,
            spaceAfter=10,
            textColor=colors.HexColor('#1a2332')
        )
        lexi_style = ParagraphStyle(
            'LexiMessage',
            parent=styles['Normal'],
            fontSize=11,
            leftIndent=10,
            rightIndent=10,
            spaceAfter=10,
            textColor=colors.HexColor('#333333')
        )
        
        story = []
        
        # Header
        story.append(Paragraph("Lexi CAO Meester - Chat Export", title_style))
        story.append(Paragraph(f"<b>Titel:</b> {chat.title}", header_style))
        story.append(Paragraph(f"<b>Datum:</b> {datetime.now().strftime('%d-%m-%Y %H:%M')}", header_style))
        story.append(Paragraph(f"<b>Gebruiker:</b> {current_user.full_name}", header_style))
        story.append(Spacer(1, 0.5*cm))
        
        # Messages
        for msg in messages:
            role_label = f"<b>{msg['role']}</b> ({msg['timestamp']})"
            story.append(Paragraph(role_label, header_style))
            
            # Clean content for PDF
            content = msg['content'].replace('<', '&lt;').replace('>', '&gt;')
            content = content.replace('\n', '<br/>')
            
            if msg['role'] == "Jij":
                story.append(Paragraph(content, user_style))
            else:
                story.append(Paragraph(content, lexi_style))
            
            story.append(Spacer(1, 0.3*cm))
        
        doc.build(story)
        buffer.seek(0)
        
        return Response(
            buffer.getvalue(),
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename=chat_{chat_id}_{datetime.now().strftime("%Y%m%d")}.pdf'}
        )
    
    elif export_format == 'docx':
        # Word Export - Only for Professional and Enterprise
        tier = g.tenant.subscription_tier or 'starter'
        if tier not in ['professional', 'enterprise']:
            return jsonify({'error': 'Word export is only available for Professional and Enterprise tiers'}), 403
        
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        doc = Document()
        
        # Title
        title = doc.add_heading('Lexi CAO Meester - Chat Export', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Metadata
        doc.add_paragraph(f"Titel: {chat.title}")
        doc.add_paragraph(f"Datum: {datetime.now().strftime('%d-%m-%Y %H:%M')}")
        doc.add_paragraph(f"Gebruiker: {current_user.full_name}")
        doc.add_paragraph('_' * 80)
        doc.add_paragraph()
        
        # Messages
        for msg in messages:
            # Role and timestamp
            p = doc.add_paragraph()
            run = p.add_run(f"{msg['role']} ({msg['timestamp']}):")
            run.bold = True
            run.font.size = Pt(11)
            if msg['role'] == "Jij":
                run.font.color.rgb = RGBColor(26, 35, 50)  # Navy
            else:
                run.font.color.rgb = RGBColor(212, 175, 55)  # Gold
            
            # Content
            content_p = doc.add_paragraph(msg['content'])
            content_p.paragraph_format.left_indent = Inches(0.5)
            
            # Separator
            doc.add_paragraph('_' * 80)
            doc.add_paragraph()
        
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        return Response(
            buffer.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition': f'attachment; filename=chat_{chat_id}_{datetime.now().strftime("%Y%m%d")}.docx'}
        )
    
    else:
        return jsonify({'error': 'Invalid export format'}), 400

@app.route('/api/feedback', methods=['POST'])
@login_required
@tenant_required
def submit_feedback():
    data = request.json or {}
    message_id = data.get('message_id')
    rating = data.get('rating')
    comment = data.get('comment', '')
    
    if not message_id or not rating:
        return jsonify({'error': 'Missing data'}), 400
    
    message = Message.query.filter_by(id=message_id, tenant_id=g.tenant.id).first_or_404()
    
    chat = Chat.query.filter_by(
        id=message.chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    message.feedback_rating = rating
    message.feedback_comment = comment
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/artifact/<int:artifact_id>/download')
@login_required
@tenant_required
def download_artifact(artifact_id):
    artifact = Artifact.query.filter_by(
        id=artifact_id,
        tenant_id=g.tenant.id
    ).first_or_404()
    
    download_url = s3_service.get_file_url(artifact.s3_key, expiration=300)
    
    if not download_url:
        return jsonify({'error': 'Download niet beschikbaar'}), 500
    
    return jsonify({
        'download_url': download_url,
        'title': artifact.title,
        'type': artifact.artifact_type
    })

@app.route('/api/chat/<int:chat_id>/files', methods=['GET'])
@login_required
@tenant_required
def get_chat_files(chat_id):
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        return jsonify({'error': 'Subscription niet actief'}), 403
    
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    files = UploadedFile.query.filter_by(
        chat_id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).all()
    
    return jsonify({
        'files': [{
            'id': f.id,
            'filename': f.original_filename,
            'file_size': f.file_size,
            'mime_type': f.mime_type,
            'created_at': f.created_at.isoformat()
        } for f in files]
    })

@app.route('/api/files/<int:file_id>', methods=['DELETE'])
@login_required
@tenant_required
def delete_file(file_id):
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        return jsonify({'error': 'Subscription niet actief'}), 403
    
    uploaded_file = UploadedFile.query.filter_by(
        id=file_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    # Delete from S3
    s3_deleted = s3_service.delete_file(uploaded_file.s3_key)
    if not s3_deleted:
        return jsonify({'error': 'Kon bestand niet verwijderen uit opslag'}), 500
    
    # Delete from database
    db.session.delete(uploaded_file)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Bestand verwijderd'})

@app.route('/api/file/<int:file_id>/view', methods=['GET'])
@login_required
@tenant_required
def view_file(file_id):
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        return jsonify({'error': 'Subscription niet actief'}), 403
    
    uploaded_file = UploadedFile.query.filter_by(
        id=file_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    # For PDF, return presigned URL for direct browser access
    if uploaded_file.mime_type == 'application/pdf':
        download_url = s3_service.get_file_url(uploaded_file.s3_key, expiration=3600)
        if not download_url:
            return jsonify({'error': 'Kon bestand niet ophalen'}), 500
        
        return jsonify({
            'type': 'pdf',
            'url': download_url,
            'filename': uploaded_file.original_filename
        })
    
    # For text/docx, return extracted content
    content, error = s3_service.download_file_content(uploaded_file.s3_key, uploaded_file.mime_type)
    if error:
        return jsonify({'error': error}), 500
    
    return jsonify({
        'type': 'text',
        'content': content
    })

@app.route('/api/upload', methods=['POST'])
@login_required
@tenant_required
def upload_file():
    if g.tenant.subscription_status not in ['active', 'trial', 'trialing']:
        return jsonify({'error': 'Subscription niet actief'}), 403
    
    if 'file' not in request.files:
        return jsonify({'error': 'Geen bestand'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Geen bestand geselecteerd'}), 400
    
    chat_id = request.form.get('chat_id')
    
    # Get file size
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    # Extract text from PDF using MarkItDown + OCR fallback
    extracted_text = None
    if file.content_type == 'application/pdf':
        try:
            # Read file data for MarkItDown
            file.seek(0)
            file_data = file.read()
            
            # Save to temporary file for MarkItDown processing
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name
            
            # Extract text using MarkItDown
            md = MarkItDown()
            result = md.convert(tmp_path)
            extracted_text = result.text_content
            
            # If MarkItDown didn't extract text (scanned PDF), use OCR
            if not extracted_text or len(extracted_text.strip()) == 0:
                print(f"[DEBUG] MarkItDown extracted no text, trying OCR...")
                try:
                    # Convert PDF pages to images
                    images = convert_from_path(tmp_path)
                    ocr_texts = []
                    
                    for i, image in enumerate(images):
                        # Extract text from each page using Tesseract OCR
                        page_text = pytesseract.image_to_string(image, lang='nld+eng')
                        if page_text.strip():
                            ocr_texts.append(f"--- Pagina {i+1} ---\n{page_text}")
                    
                    if ocr_texts:
                        extracted_text = '\n\n'.join(ocr_texts)
                        print(f"[DEBUG] OCR successful, extracted {len(extracted_text)} characters from {len(images)} pages")
                    else:
                        print(f"[DEBUG] OCR found no text in PDF")
                except Exception as ocr_error:
                    print(f"[DEBUG] OCR failed: {ocr_error}")
            
            # Clean up temporary file
            os.unlink(tmp_path)
            
            # Reset file pointer for S3 upload
            file.seek(0)
        except Exception as e:
            print(f"Error extracting PDF text: {e}")
            # Reset file pointer and continue without extracted text
            file.seek(0)
    
    # Upload to S3
    s3_key = s3_service.upload_file(file, g.tenant.id)
    if not s3_key:
        return jsonify({'error': 'Upload mislukt'}), 500
    
    uploaded_file = UploadedFile(
        tenant_id=g.tenant.id,
        user_id=current_user.id,
        chat_id=chat_id if chat_id else None,
        filename=file.filename,
        original_filename=file.filename,
        s3_key=s3_key,
        file_size=file_size,
        mime_type=file.content_type,
        extracted_text=extracted_text
    )
    db.session.add(uploaded_file)
    db.session.commit()
    
    return jsonify({'success': True, 'file_id': uploaded_file.id})

# Support Ticket Routes (Customer)
@app.route('/support')
@login_required
@tenant_required
def support_tickets():
    from models import SupportTicket
    tickets = SupportTicket.query.filter_by(
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).order_by(SupportTicket.updated_at.desc()).all()
    
    return render_template('support/tickets.html', tickets=tickets, tenant=g.tenant, user=current_user)

@app.route('/support/new')
@login_required
@tenant_required
def new_support_ticket():
    return render_template('support/new_ticket.html', tenant=g.tenant, user=current_user)

@app.route('/api/support/create', methods=['POST'])
@login_required
@tenant_required
def create_support_ticket():
    from models import SupportTicket, SupportReply
    data = request.json or {}
    
    subject = data.get('subject', '').strip()
    category = data.get('category', '').strip()
    message = data.get('message', '').strip()
    
    if not subject or not category or not message:
        return jsonify({'error': 'Alle velden zijn verplicht'}), 400
    
    # Get next ticket number
    last_ticket = SupportTicket.query.order_by(SupportTicket.ticket_number.desc()).first()
    ticket_number = (last_ticket.ticket_number + 1) if last_ticket else 1000
    
    # Create ticket
    ticket = SupportTicket(
        ticket_number=ticket_number,
        tenant_id=g.tenant.id,
        user_id=current_user.id,
        user_email=current_user.email,
        user_name=current_user.full_name,
        subject=subject,
        category=category,
        status='open'
    )
    db.session.add(ticket)
    db.session.flush()
    
    # Add first message
    reply = SupportReply(
        ticket_id=ticket.id,
        message=message,
        is_admin=False,
        sender_name=current_user.full_name
    )
    db.session.add(reply)
    db.session.commit()
    
    return jsonify({'success': True, 'ticket_id': ticket.id})

@app.route('/support/<int:ticket_id>')
@login_required
@tenant_required
def view_support_ticket(ticket_id):
    from models import SupportTicket
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    return render_template('support/ticket_detail.html', ticket=ticket, tenant=g.tenant, user=current_user)

@app.route('/api/support/<int:ticket_id>/reply', methods=['POST'])
@login_required
@tenant_required
def reply_support_ticket(ticket_id):
    from models import SupportTicket, SupportReply
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    data = request.json or {}
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'Bericht mag niet leeg zijn'}), 400
    
    reply = SupportReply(
        ticket_id=ticket.id,
        message=message,
        is_admin=False,
        sender_name=current_user.full_name
    )
    db.session.add(reply)
    
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/support/<int:ticket_id>/close', methods=['POST'])
@login_required
@tenant_required
def close_support_ticket(ticket_id):
    from models import SupportTicket
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    ticket.status = 'closed'
    ticket.closed_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/dashboard')
@login_required
@tenant_required
@admin_required
def admin_dashboard():
    users = User.query.filter_by(tenant_id=g.tenant.id).all()
    total_chats = Chat.query.filter_by(tenant_id=g.tenant.id).count()
    subscription = Subscription.query.filter_by(tenant_id=g.tenant.id).first()
    
    total_messages = Message.query.filter_by(
        tenant_id=g.tenant.id,
        role='user'
    ).count()
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    messages_this_month = Message.query.filter(
        Message.tenant_id == g.tenant.id,
        Message.role == 'user',
        Message.created_at >= thirty_days_ago
    ).count()
    
    active_users_ids = db.session.query(Chat.user_id).filter(
        Chat.tenant_id == g.tenant.id,
        Chat.updated_at >= thirty_days_ago
    ).distinct().all()
    active_users_count = len(active_users_ids)
    
    top_users = db.session.query(
        User,
        db.func.count(Chat.id).label('chat_count')
    ).join(Chat, User.id == Chat.user_id
    ).filter(
        User.tenant_id == g.tenant.id,
        Chat.tenant_id == g.tenant.id
    ).group_by(User.id
    ).order_by(db.desc('chat_count')
    ).limit(5).all()
    
    return render_template('admin_dashboard.html', 
                         tenant=g.tenant, 
                         users=users, 
                         total_chats=total_chats,
                         subscription=subscription,
                         total_messages=total_messages,
                         messages_this_month=messages_this_month,
                         active_users_count=active_users_count,
                         top_users=top_users)

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
@tenant_required
@admin_required
def admin_users():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            current_user_count = User.query.filter_by(tenant_id=g.tenant.id).count()
            if current_user_count >= g.tenant.max_users:
                flash(f'Maximum aantal gebruikers bereikt ({g.tenant.max_users}). Upgrade je plan.', 'warning')
                return redirect(url_for('admin_users'))
            
            email = request.form.get('email')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            password = request.form.get('password')
            role = request.form.get('role', 'user')
            
            if role not in ['user', 'admin']:
                role = 'user'
            
            if User.query.filter_by(tenant_id=g.tenant.id, email=email).first():
                flash('Deze email is al in gebruik.', 'danger')
            else:
                user = User(
                    tenant_id=g.tenant.id,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    role=role
                )
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                
                login_url = f"https://{g.tenant.subdomain}.lex-cao.replit.app/login"
                email_service.send_welcome_email(user, g.tenant, login_url)
                
                flash(f'Gebruiker toegevoegd als {role}!', 'success')
        
        elif action == 'toggle':
            user_id = request.form.get('user_id')
            user = User.query.filter_by(id=user_id, tenant_id=g.tenant.id).first()
            if user and user.id != current_user.id:
                user.is_active = not user.is_active
                db.session.commit()
                flash('Gebruiker status gewijzigd.', 'success')
        
        elif action == 'delete':
            user_id = request.form.get('user_id')
            user = User.query.filter_by(id=user_id, tenant_id=g.tenant.id).first()
            if user and user.id != current_user.id:
                db.session.delete(user)
                db.session.commit()
                flash('Gebruiker verwijderd.', 'success')
        
        elif action == 'change_role':
            user_id = request.form.get('user_id')
            new_role = request.form.get('role')
            user = User.query.filter_by(id=user_id, tenant_id=g.tenant.id).first()
            if user and user.id != current_user.id and new_role in ['user', 'admin']:
                user.role = new_role
                db.session.commit()
                flash(f'Gebruiker rol gewijzigd naar {new_role}.', 'success')
    
    users = User.query.filter_by(tenant_id=g.tenant.id).all()
    return render_template('admin_users.html', tenant=g.tenant, users=users)

# Admin Support Routes
@app.route('/admin/support')
@login_required
@tenant_required
@admin_required
def admin_support():
    from models import SupportTicket
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    
    query = SupportTicket.query.filter_by(tenant_id=g.tenant.id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    tickets = query.order_by(SupportTicket.updated_at.desc()).all()
    
    # Stats
    total_tickets = SupportTicket.query.filter_by(tenant_id=g.tenant.id).count()
    open_tickets = SupportTicket.query.filter_by(tenant_id=g.tenant.id, status='open').count()
    in_progress_tickets = SupportTicket.query.filter_by(tenant_id=g.tenant.id, status='in_progress').count()
    answered_tickets = SupportTicket.query.filter_by(tenant_id=g.tenant.id, status='answered').count()
    closed_tickets = SupportTicket.query.filter_by(tenant_id=g.tenant.id, status='closed').count()
    
    return render_template('admin_support.html', 
                         tickets=tickets, 
                         tenant=g.tenant,
                         total_tickets=total_tickets,
                         open_tickets=open_tickets,
                         in_progress_tickets=in_progress_tickets,
                         answered_tickets=answered_tickets,
                         closed_tickets=closed_tickets,
                         status_filter=status_filter,
                         category_filter=category_filter)

@app.route('/admin/support/<int:ticket_id>')
@login_required
@tenant_required
@admin_required
def admin_view_ticket(ticket_id):
    from models import SupportTicket
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        tenant_id=g.tenant.id
    ).first_or_404()
    
    return render_template('admin_support_detail.html', ticket=ticket, tenant=g.tenant)

@app.route('/api/admin/support/<int:ticket_id>/reply', methods=['POST'])
@login_required
@tenant_required
@admin_required
def admin_reply_ticket(ticket_id):
    from models import SupportTicket, SupportReply
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        tenant_id=g.tenant.id
    ).first_or_404()
    
    data = request.json or {}
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'Bericht mag niet leeg zijn'}), 400
    
    reply = SupportReply(
        ticket_id=ticket.id,
        message=message,
        is_admin=True,
        sender_name=current_user.full_name
    )
    db.session.add(reply)
    
    # Update status to answered when admin replies
    if ticket.status == 'open':
        ticket.status = 'answered'
    
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/admin/support/<int:ticket_id>/status', methods=['POST'])
@login_required
@tenant_required
@admin_required
def admin_update_ticket_status(ticket_id):
    from models import SupportTicket
    ticket = SupportTicket.query.filter_by(
        id=ticket_id,
        tenant_id=g.tenant.id
    ).first_or_404()
    
    data = request.json or {}
    new_status = data.get('status')
    
    if new_status not in ['open', 'in_progress', 'answered', 'closed']:
        return jsonify({'error': 'Ongeldige status'}), 400
    
    ticket.status = new_status
    if new_status == 'closed':
        ticket.closed_at = datetime.utcnow()
    else:
        ticket.closed_at = None
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/templates', methods=['GET', 'POST'])
@login_required
@tenant_required
@admin_required
def admin_templates():
    if request.method == 'POST':
        name = request.form.get('name') or ''
        category = request.form.get('category') or ''
        content = request.form.get('content') or ''
        
        template = Template(
            tenant_id=g.tenant.id,
            name=name,
            category=category,
            content=content
        )
        
        if content:
            s3_key = s3_service.upload_content(content, f"{name}.txt", g.tenant.id, 'templates')
            template.s3_key = s3_key
        
        db.session.add(template)
        db.session.commit()
        flash('Template opgeslagen!', 'success')
    
    templates = Template.query.filter_by(tenant_id=g.tenant.id).all()
    return render_template('admin_templates.html', tenant=g.tenant, templates=templates)

@app.route('/admin/billing')
@login_required
@tenant_required
@admin_required
def admin_billing():
    subscription = Subscription.query.filter_by(tenant_id=g.tenant.id).first()
    
    return render_template('admin_billing.html', 
                         tenant=g.tenant, 
                         subscription=subscription)

@app.route('/admin/billing/checkout/<plan>')
@login_required
@tenant_required
@admin_required
def billing_checkout(plan):
    if plan not in ['starter', 'professional', 'enterprise']:
        return "Invalid plan", 400
    
    success_url = url_for('billing_success', _external=True)
    cancel_url = url_for('admin_billing', _external=True)
    
    session_obj = StripeService.create_checkout_session(
        g.tenant.id, plan, success_url, cancel_url
    )
    
    if session_obj and session_obj.url:
        return redirect(session_obj.url)
    
    flash('Er ging iets mis met de betaling.', 'danger')
    return redirect(url_for('admin_billing'))

@app.route('/billing/success')
@login_required
@tenant_required
def billing_success():
    flash('Betaling succesvol! Je account is nu actief.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')
    
    if not webhook_secret:
        print("WARNING: No webhook secret configured!")
        return jsonify({'success': True})
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        print(f"Webhook signature verification failed: {e}")
        return jsonify({'error': str(e)}), 400
    
    print(f"Received Stripe webhook event: {event['type']}")
    
    if event['type'] == 'checkout.session.completed':
        from models import PendingSignup
        
        session_obj = event['data']['object']
        checkout_session_id = session_obj.get('id')
        
        print(f"Processing checkout.session.completed for session: {checkout_session_id}")
        
        # Get pending signup from database using checkout session ID
        pending_signup = PendingSignup.query.filter_by(checkout_session_id=checkout_session_id).first()
        
        if not pending_signup:
            print(f"❌ No pending signup found for session {checkout_session_id}")
            return jsonify({'error': 'No pending signup found'}), 404
        
        # Check if user already exists (prevent duplicates)
        existing_user = User.query.filter_by(email=pending_signup.email).first()
        if existing_user:
            print(f"User {pending_signup.email} already exists, cleaning up pending signup")
            try:
                db.session.delete(pending_signup)
                db.session.commit()
            except Exception as cleanup_error:
                print(f"Warning: Failed to cleanup pending signup: {cleanup_error}")
                db.session.rollback()
            return jsonify({'success': True, 'message': 'User already exists'})
        
        # Extract data from pending signup
        email_to_use = pending_signup.email
        company_name = pending_signup.company_name
        contact_name = pending_signup.contact_name
        password_hash = pending_signup.password_hash  # Already hashed
        tier = pending_signup.tier
        billing = pending_signup.billing
        
        print(f"Creating account for: {email_to_use}, tier: {tier}, billing: {billing}")
        
        try:
            # Create subdomain
            import re
            base_subdomain = re.sub(r'[^a-z0-9]', '', company_name.lower().replace(' ', ''))[:20]
            subdomain = base_subdomain if base_subdomain else 'tenant'
            
            counter = 1
            original_subdomain = subdomain
            while Tenant.query.filter_by(subdomain=subdomain).first():
                subdomain = f"{original_subdomain}{counter}"
                counter += 1
            
            # Create tenant
            tenant = Tenant(
                company_name=company_name,
                subdomain=subdomain,
                contact_email=email_to_use,
                contact_name=contact_name,
                status='active',
                subscription_tier=tier,
                max_users=get_max_users_for_tier(tier)
            )
            db.session.add(tenant)
            db.session.flush()
            
            # Create admin user
            name_parts = contact_name.split() if contact_name else []
            admin_user = User(
                tenant_id=tenant.id,
                email=email_to_use,
                first_name=name_parts[0] if name_parts else 'Admin',
                last_name=' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
                role='admin',
                is_active=True,
                disclaimer_accepted_at=datetime.utcnow(),
                password_hash=password_hash  # Use pre-hashed password from pending signup
            )
            db.session.add(admin_user)
            
            # Create subscription
            subscription = Subscription(
                tenant_id=tenant.id,
                plan=tier,
                status='active',
                stripe_customer_id=session_obj.get('customer'),
                stripe_subscription_id=session_obj.get('subscription')
            )
            db.session.add(subscription)
            
            db.session.commit()
            
            print(f"✅ Account created successfully for {email_to_use}")
            
            # Delete pending signup now that account is created
            db.session.delete(pending_signup)
            db.session.commit()
            
            # Send welcome email
            login_url = f"https://{subdomain}.lex-cao.replit.app/login"
            email_service.send_welcome_email(admin_user, tenant, login_url)
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error creating account: {e}")
            return jsonify({'error': str(e)}), 500
    
    elif event['type'] == 'customer.subscription.updated':
        subscription_obj = event['data']['object']
        stripe_sub_id = subscription_obj.get('id')
        status = subscription_obj.get('status')
        
        subscription = Subscription.query.filter_by(stripe_subscription_id=stripe_sub_id).first()
        if subscription:
            # Map Stripe status to our status
            if status in ['active', 'trialing']:
                subscription.status = 'active'
                tenant = Tenant.query.get(subscription.tenant_id)
                if tenant:
                    tenant.status = 'active'
            elif status in ['past_due', 'unpaid']:
                subscription.status = 'past_due'
            elif status in ['canceled', 'incomplete_expired']:
                subscription.status = 'canceled'
                tenant = Tenant.query.get(subscription.tenant_id)
                if tenant:
                    tenant.status = 'inactive'
            
            db.session.commit()
            print(f"Updated subscription {stripe_sub_id} to status {status}")
    
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        customer_id = invoice.get('customer')
        
        subscription = Subscription.query.filter_by(stripe_customer_id=customer_id).first()
        if subscription:
            tenant = Tenant.query.get(subscription.tenant_id)
            email_service.send_payment_failed_email(tenant)
            print(f"Payment failed email sent to {tenant.contact_email}")
    
    return jsonify({'success': True})

@app.route('/super-admin/dashboard')
@super_admin_required
def super_admin_dashboard():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    total_users = User.query.count()
    
    mrr_prices = {'starter': 499, 'professional': 599, 'enterprise': 1199}
    
    current_mrr = sum(mrr_prices.get(t.subscription_tier, 0) for t in tenants if t.subscription_status == 'active')
    arr = current_mrr * 12
    
    from dateutil.relativedelta import relativedelta
    last_month = datetime.utcnow() - relativedelta(months=1)
    last_month_tenants = [t for t in tenants if t.created_at < last_month and t.subscription_status == 'active']
    last_month_mrr = sum(mrr_prices.get(t.subscription_tier, 0) for t in last_month_tenants)
    
    growth_percentage = 0
    if last_month_mrr > 0:
        growth_percentage = ((current_mrr - last_month_mrr) / last_month_mrr) * 100
    elif current_mrr > 0 and last_month_mrr == 0:
        growth_percentage = 100
    
    starter_count = sum(1 for t in tenants if t.subscription_tier == 'starter' and t.subscription_status == 'active')
    professional_count = sum(1 for t in tenants if t.subscription_tier == 'professional' and t.subscription_status == 'active')
    enterprise_count = sum(1 for t in tenants if t.subscription_tier == 'enterprise' and t.subscription_status == 'active')
    starter_mrr = starter_count * 499
    professional_mrr = professional_count * 599
    enterprise_mrr = enterprise_count * 1199
    
    mrr_history = []
    for i in range(6, 0, -1):
        month_date = datetime.utcnow() - relativedelta(months=i)
        month_tenants = [t for t in tenants if t.created_at <= month_date and t.subscription_status == 'active']
        month_mrr = sum(mrr_prices.get(t.subscription_tier, 0) for t in month_tenants)
        mrr_history.append({
            'month': month_date.strftime('%b'),
            'mrr': month_mrr
        })
    
    return render_template('super_admin_dashboard.html', 
                         tenants=tenants, 
                         total_users=total_users,
                         current_mrr=current_mrr,
                         arr=arr,
                         growth_percentage=growth_percentage,
                         starter_count=starter_count,
                         professional_count=professional_count,
                         enterprise_count=enterprise_count,
                         starter_mrr=starter_mrr,
                         professional_mrr=professional_mrr,
                         enterprise_mrr=enterprise_mrr,
                         mrr_history=mrr_history)

@app.route('/super-admin/tenants/create', methods=['POST'])
@super_admin_required
def super_admin_create_tenant():
    company_name = request.form.get('company_name')
    subdomain = request.form.get('subdomain', '').lower().strip()
    contact_email = request.form.get('contact_email')
    contact_name = request.form.get('contact_name')
    max_users = int(request.form.get('max_users', 5))
    
    tenant = Tenant(
        company_name=company_name,
        subdomain=subdomain,
        contact_email=contact_email,
        contact_name=contact_name,
        max_users=max_users,
        status='active'
    )
    db.session.add(tenant)
    db.session.commit()
    
    flash('Tenant aangemaakt!', 'success')
    return redirect(url_for('super_admin_dashboard'))

@app.route('/super-admin/tenants/<int:tenant_id>/status', methods=['POST'])
@super_admin_required
def super_admin_update_tenant_status(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    new_status = request.form.get('status')
    
    if new_status in ['active', 'suspended']:
        tenant.status = new_status
        db.session.commit()
        flash('Tenant status bijgewerkt!', 'success')
    
    return redirect(url_for('super_admin_dashboard'))

@app.route('/super-admin/tenants/<int:tenant_id>/tier', methods=['POST'])
@super_admin_required
def super_admin_update_tenant_tier(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    new_tier = request.form.get('tier')
    
    if new_tier in ['starter', 'professional', 'enterprise']:
        tenant.subscription_tier = new_tier
        tenant.max_users = get_max_users_for_tier(new_tier)
        
        # Update subscription plan if exists
        subscription = Subscription.query.filter_by(tenant_id=tenant_id).first()
        if subscription:
            subscription.plan = new_tier
        
        db.session.commit()
        flash(f'Tenant tier bijgewerkt naar {new_tier} (max {tenant.max_users} users)!', 'success')
    
    return redirect(url_for('super_admin_dashboard'))

@app.route('/super-admin/impersonate/<int:tenant_id>', methods=['POST'])
@super_admin_required
def super_admin_impersonate(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    
    admin_user = User.query.filter_by(tenant_id=tenant_id, role='admin').first()
    
    if not admin_user:
        flash('Geen admin user gevonden voor deze tenant!', 'error')
        return redirect(url_for('super_admin_tenant_detail', tenant_id=tenant_id))
    
    session['impersonating_super_admin_id'] = session.get('super_admin_id')
    session['impersonating_from'] = 'super_admin'
    
    session.pop('super_admin_id', None)
    session.pop('is_super_admin', None)
    
    logout_user()
    login_user(admin_user)
    
    session['tenant_id'] = tenant_id
    
    flash(f'Nu ingelogd als {admin_user.full_name} ({tenant.company_name})', 'success')
    return redirect('/chat')

@app.route('/stop-impersonate', methods=['POST'])
def stop_impersonate():
    if session.get('impersonating_from') == 'super_admin':
        super_admin_id = session.get('impersonating_super_admin_id')
        
        if not super_admin_id:
            flash('Impersonation context verloren', 'error')
            return redirect(url_for('index'))
        
        super_admin = SuperAdmin.query.get(super_admin_id)
        if not super_admin:
            flash('Super admin niet gevonden', 'error')
            return redirect(url_for('index'))
        
        logout_user()
        
        session.pop('tenant_id', None)
        session.pop('impersonating_from', None)
        session.pop('impersonating_super_admin_id', None)
        
        login_user(super_admin)
        session['super_admin_id'] = super_admin.id
        session['is_super_admin'] = True
        
        flash('Impersonation gestopt', 'success')
        return redirect(url_for('super_admin_dashboard'))
    
    flash('Je was niet aan het impersonaten', 'error')
    return redirect(url_for('index'))

@app.route('/super-admin/tenants/<int:tenant_id>')
@super_admin_required
def super_admin_tenant_detail(tenant_id):
    tenant = Tenant.query.get_or_404(tenant_id)
    
    users = User.query.filter_by(tenant_id=tenant_id).all()
    
    total_questions = db.session.query(Message).join(Chat).filter(
        Chat.tenant_id == tenant_id,
        Message.role == 'user'
    ).count()
    
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    questions_this_month = db.session.query(Message).join(Chat).filter(
        Chat.tenant_id == tenant_id,
        Message.role == 'user',
        Message.created_at >= thirty_days_ago
    ).count()
    
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    questions_today = db.session.query(Message).join(Chat).filter(
        Chat.tenant_id == tenant_id,
        Message.role == 'user',
        Message.created_at >= today
    ).count()
    
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    active_users_count = db.session.query(Chat.user_id).filter(
        Chat.tenant_id == tenant_id,
        Chat.created_at >= seven_days_ago
    ).distinct().count()
    
    avg_questions = total_questions / len(users) if users else 0
    
    top_questions = db.session.query(
        Message.content, 
        db.func.count(Message.id).label('count')
    ).join(Chat).filter(
        Chat.tenant_id == tenant_id,
        Message.role == 'user'
    ).group_by(Message.content).order_by(db.desc('count')).limit(5).all()
    
    for user in users:
        user.question_count = db.session.query(Message).join(Chat).filter(
            Chat.user_id == user.id,
            Message.role == 'user'
        ).count()
        user.last_activity = db.session.query(db.func.max(Chat.updated_at)).filter(
            Chat.user_id == user.id
        ).scalar()
    
    trial_days_left = None
    if tenant.trial_ends_at and tenant.subscription_status == 'trial':
        trial_days_left = (tenant.trial_ends_at - datetime.utcnow()).days
        if trial_days_left < 0:
            trial_days_left = 0
    
    return render_template('super_admin_tenant_detail.html',
                         tenant=tenant,
                         users=users,
                         total_questions=total_questions,
                         questions_this_month=questions_this_month,
                         questions_today=questions_today,
                         active_users_count=active_users_count,
                         avg_questions=avg_questions,
                         top_questions=top_questions,
                         trial_days_left=trial_days_left)

@app.route('/super-admin/analytics/export')
@super_admin_required
def super_admin_analytics_export():
    import csv
    from io import StringIO
    from flask import Response
    
    tenants = Tenant.query.all()
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Tenant ID', 'Company Name', 'Subdomain', 'Status', 'Tier', 'MRR', 'Users', 'Questions', 'Created At'])
    
    mrr_prices = {'starter': 499, 'professional': 599, 'enterprise': 1199}
    
    for tenant in tenants:
        users_count = User.query.filter_by(tenant_id=tenant.id).count()
        questions_count = db.session.query(Message).join(Chat).filter(
            Chat.tenant_id == tenant.id,
            Message.role == 'user'
        ).count()
        
        mrr = mrr_prices.get(tenant.subscription_tier, 0) if tenant.subscription_status == 'active' else 0
        
        writer.writerow([
            tenant.id,
            tenant.company_name,
            tenant.subdomain,
            tenant.subscription_status,
            tenant.subscription_tier,
            mrr,
            users_count,
            questions_count,
            tenant.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=analytics_export.csv'}
    )

@app.route('/super-admin/analytics')
@super_admin_required
def super_admin_analytics():
    from dateutil.relativedelta import relativedelta
    from datetime import datetime, timedelta
    
    tenants = Tenant.query.all()
    all_users = User.query.all()
    
    mrr_prices = {'starter': 499, 'professional': 599, 'enterprise': 1199}
    
    current_mrr = sum(mrr_prices.get(t.subscription_tier, 0) for t in tenants if t.subscription_status == 'active')
    total_revenue = current_mrr * 12
    
    active_tenants = sum(1 for t in tenants if t.subscription_status == 'active')
    trial_tenants = sum(1 for t in tenants if t.subscription_status == 'trial')
    
    last_month = datetime.utcnow() - relativedelta(months=1)
    last_month_tenants = [t for t in tenants if t.created_at < last_month and t.subscription_status == 'active']
    last_month_mrr = sum(mrr_prices.get(t.subscription_tier, 0) for t in last_month_tenants)
    
    growth_rate = 0
    if last_month_mrr > 0:
        growth_rate = ((current_mrr - last_month_mrr) / last_month_mrr) * 100
    elif current_mrr > 0 and last_month_mrr == 0:
        growth_rate = 100
    
    total_questions = db.session.query(Message).filter(Message.role == 'user').count()
    
    mrr_history = []
    questions_history = []
    for i in range(12, 0, -1):
        month_date = datetime.utcnow() - relativedelta(months=i)
        month_tenants = [t for t in tenants if t.created_at <= month_date and t.subscription_status == 'active']
        month_mrr = sum(mrr_prices.get(t.subscription_tier, 0) for t in month_tenants)
        
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = (month_start + relativedelta(months=1)) - timedelta(seconds=1)
        month_questions = db.session.query(Message).filter(
            Message.role == 'user',
            Message.created_at >= month_start,
            Message.created_at <= month_end
        ).count()
        
        mrr_history.append({
            'month': month_date.strftime('%b %Y'),
            'mrr': month_mrr
        })
        questions_history.append({
            'month': month_date.strftime('%b %Y'),
            'count': month_questions
        })
    
    tier_distribution = {
        'starter': sum(1 for t in tenants if t.subscription_tier == 'starter' and t.subscription_status == 'active'),
        'professional': sum(1 for t in tenants if t.subscription_tier == 'professional' and t.subscription_status == 'active'),
        'enterprise': sum(1 for t in tenants if t.subscription_tier == 'enterprise' and t.subscription_status == 'active'),
        'trial': sum(1 for t in tenants if t.subscription_tier == 'trial')
    }
    
    top_tenants = []
    for tenant in tenants:
        tenant_questions = db.session.query(Message).join(Chat).filter(
            Chat.tenant_id == tenant.id,
            Message.role == 'user'
        ).count()
        if tenant_questions > 0:
            top_tenants.append({
                'tenant': tenant,
                'questions': tenant_questions
            })
    top_tenants = sorted(top_tenants, key=lambda x: x['questions'], reverse=True)[:10]
    
    top_questions = db.session.query(
        Message.content,
        db.func.count(Message.id).label('count')
    ).filter(
        Message.role == 'user'
    ).group_by(Message.content).order_by(db.desc('count')).limit(10).all()
    
    recent_activity = db.session.query(Chat).order_by(Chat.updated_at.desc()).limit(20).all()
    
    conversion_funnel = {
        'signups': len(tenants),
        'trials': trial_tenants,
        'active': active_tenants,
        'conversion_rate': (active_tenants / len(tenants) * 100) if tenants else 0
    }
    
    return render_template('super_admin_analytics.html',
                         current_mrr=current_mrr,
                         total_revenue=total_revenue,
                         active_tenants=active_tenants,
                         growth_rate=growth_rate,
                         total_questions=total_questions,
                         mrr_history=mrr_history,
                         questions_history=questions_history,
                         tier_distribution=tier_distribution,
                         top_tenants=top_tenants,
                         top_questions=top_questions,
                         recent_activity=recent_activity,
                         conversion_funnel=conversion_funnel)

@app.route('/super-admin/support')
@super_admin_required
def super_admin_support():
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    
    query = SupportTicket.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    tickets = query.order_by(SupportTicket.created_at.desc()).all()
    
    open_count = SupportTicket.query.filter_by(status='open').count()
    in_progress_count = SupportTicket.query.filter_by(status='in_progress').count()
    answered_count = SupportTicket.query.filter_by(status='answered').count()
    closed_count = SupportTicket.query.filter_by(status='closed').count()
    
    return render_template('super_admin_support.html',
                         tickets=tickets,
                         status_filter=status_filter,
                         category_filter=category_filter,
                         open_count=open_count,
                         in_progress_count=in_progress_count,
                         answered_count=answered_count,
                         closed_count=closed_count)

@app.route('/super-admin/support/<int:ticket_id>')
@super_admin_required
def super_admin_support_detail(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    replies = SupportReply.query.filter_by(ticket_id=ticket_id).order_by(SupportReply.created_at).all()
    
    tenant = Tenant.query.get(ticket.tenant_id)
    user = User.query.get(ticket.user_id)
    
    return render_template('super_admin_support_detail.html',
                         ticket=ticket,
                         replies=replies,
                         tenant=tenant,
                         user=user)

@app.route('/api/super-admin/support/<int:ticket_id>/reply', methods=['POST'])
@super_admin_required
def super_admin_support_reply(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    message = (request.json or {}).get('message')
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    reply = SupportReply(
        ticket_id=ticket_id,
        message=message,
        is_admin=True,
        sender_name='Super Admin'
    )
    db.session.add(reply)
    
    ticket.status = 'answered'
    ticket.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'reply': {
            'message': reply.message,
            'is_admin': reply.is_admin,
            'sender_name': reply.sender_name,
            'created_at': reply.created_at.strftime('%d-%m-%Y %H:%M')
        }
    })

@app.route('/api/super-admin/support/<int:ticket_id>/status', methods=['POST'])
@super_admin_required
def super_admin_support_status(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    new_status = (request.json or {}).get('status')
    
    if new_status not in ['open', 'in_progress', 'answered', 'closed']:
        return jsonify({'error': 'Invalid status'}), 400
    
    ticket.status = new_status
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})

def init_db():
    try:
        with app.app_context():
            db.create_all()
            print("Database tables checked/created successfully")
            
            if not SuperAdmin.query.first():
                admin = SuperAdmin(
                    email='admin@lex-cao.nl',
                    name='Super Administrator'
                )
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Super admin created: admin@lex-cao.nl / admin123")
    except Exception as e:
        print(f"Database initialization: {e}")

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
