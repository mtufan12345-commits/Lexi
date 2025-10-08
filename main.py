import os
import re
from flask import Flask, render_template, request, redirect, url_for, jsonify, g, session, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from models import db, SuperAdmin, Tenant, User, Chat, Message, Subscription, Template, UploadedFile, Artifact
from services import vertex_ai_service, s3_service, email_service, StripeService
import stripe
from datetime import datetime, timedelta
import secrets
from functools import wraps

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
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

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    if session.get('is_super_admin'):
        return SuperAdmin.query.get(int(user_id))
    return User.query.get(int(user_id))

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

@app.route('/')
def index():
    if g.tenant:
        return redirect(url_for('login'))
    return render_template('landing.html')

@app.route('/signup/tenant', methods=['GET', 'POST'])
def signup_tenant():
    if request.method == 'POST':
        company_name = request.form.get('company_name')
        subdomain = request.form.get('subdomain', '').lower().strip()
        contact_email = request.form.get('contact_email')
        contact_name = request.form.get('contact_name')
        password = request.form.get('password')
        
        if Tenant.query.filter_by(subdomain=subdomain).first():
            flash('Deze subdomain is al in gebruik.', 'danger')
            return render_template('signup_tenant.html')
        
        tenant = Tenant(
            company_name=company_name,
            subdomain=subdomain,
            contact_email=contact_email,
            contact_name=contact_name,
            status='trial'
        )
        db.session.add(tenant)
        db.session.flush()
        
        admin_user = User(
            tenant_id=tenant.id,
            email=contact_email,
            first_name=contact_name.split()[0] if contact_name else 'Admin',
            last_name=' '.join(contact_name.split()[1:]) if len(contact_name.split()) > 1 else '',
            role='admin'
        )
        admin_user.set_password(password)
        db.session.add(admin_user)
        
        subscription = Subscription(
            tenant_id=tenant.id,
            plan='professional',
            status='trialing'
        )
        db.session.add(subscription)
        
        db.session.commit()
        
        # Set tenant in session for development mode
        session['tenant_id'] = tenant.id
        
        login_url = f"https://{subdomain}.lex-cao.replit.app/login"
        email_service.send_welcome_email(admin_user, tenant, login_url)
        
        flash('Account aangemaakt! Je kunt nu inloggen.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup_tenant.html')

@app.route('/login', methods=['GET', 'POST'])
@tenant_required
def login():
    if current_user.is_authenticated and not g.is_super_admin:
        return redirect(url_for('chat_page'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        print(f"Login attempt - Tenant ID: {g.tenant.id}, Email: {email}")
        user = User.query.filter_by(tenant_id=g.tenant.id, email=email).first()
        print(f"User found: {user is not None}")
        
        if user and user.check_password(password):
            print("Password check passed")
            if not user.is_active:
                flash('Je account is gedeactiveerd.', 'danger')
                return render_template('login.html', tenant=g.tenant)
            
            if g.tenant.status not in ['trial', 'active']:
                flash('Je account is verlopen. Neem contact op met de administrator.', 'warning')
                return render_template('login.html', tenant=g.tenant)
            
            force_login = request.form.get('force_login') == 'true'
            
            if user.session_token and not force_login:
                return render_template('login.html', tenant=g.tenant, 
                                     show_force_login=True, 
                                     email=email)
            
            user.session_token = secrets.token_hex(32)
            db.session.commit()
            
            login_user(user)
            session['session_token'] = user.session_token
            session['is_super_admin'] = False
            
            if force_login:
                flash('Oude sessie uitgelogd. Je bent nu ingelogd.', 'success')
            
            return redirect(url_for('chat_page'))
        
        print("Login failed - invalid credentials")
        flash('Ongeldige email of wachtwoord.', 'danger')
    
    return render_template('login.html', tenant=g.tenant)

@app.route('/super-admin/login', methods=['GET', 'POST'])
def super_admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        admin = SuperAdmin.query.filter_by(email=email).first()
        if admin and admin.check_password(password):
            login_user(admin)
            session['is_super_admin'] = True
            return redirect(url_for('super_admin_dashboard'))
        
        flash('Ongeldige credentials.', 'danger')
    
    return render_template('super_admin_login.html')

@app.route('/select-tenant', methods=['GET', 'POST'])
def select_tenant():
    """Development mode: manually select a tenant"""
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

@app.route('/chat')
@login_required
@tenant_required
def chat_page():
    chats = Chat.query.filter_by(
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).order_by(Chat.updated_at.desc()).all()
    
    return render_template('chat.html', chats=chats, tenant=g.tenant, user=current_user)

@app.route('/api/chat/new', methods=['POST'])
@login_required
@tenant_required
def new_chat():
    chat = Chat(
        tenant_id=g.tenant.id,
        user_id=current_user.id,
        title='Nieuwe chat'
    )
    db.session.add(chat)
    db.session.commit()
    
    return jsonify({'id': chat.id, 'title': chat.title})

@app.route('/api/chat/<int:chat_id>', methods=['GET'])
@login_required
@tenant_required
def get_chat(chat_id):
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    messages = []
    for m in chat.messages:
        msg_data = {
            'role': m.role,
            'content': m.content,
            'created_at': m.created_at.isoformat()
        }
        
        if m.role == 'assistant':
            artifacts = Artifact.query.filter_by(message_id=m.id, tenant_id=g.tenant.id).all()
            if artifacts:
                msg_data['artifacts'] = [{
                    'id': a.id,
                    'title': a.title,
                    'type': a.artifact_type
                } for a in artifacts]
        
        messages.append(msg_data)
    
    return jsonify({'id': chat.id, 'title': chat.title, 'messages': messages})

@app.route('/api/chat/<int:chat_id>/message', methods=['POST'])
@login_required
@tenant_required
def send_message(chat_id):
    print(f"[DEBUG] send_message called - chat_id: {chat_id}, user: {current_user.id}")
    
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    data = request.json
    user_message = data.get('message', '')
    print(f"[DEBUG] User message: {user_message}")
    
    message = Message(
        tenant_id=g.tenant.id,
        chat_id=chat.id,
        role='user',
        content=user_message
    )
    db.session.add(message)
    
    if len(chat.messages) == 0:
        chat.title = user_message[:50] + ('...' if len(user_message) > 50 else '')
    
    chat.updated_at = datetime.utcnow()
    db.session.commit()
    
    uploaded_files = UploadedFile.query.filter_by(
        chat_id=chat.id,
        tenant_id=g.tenant.id
    ).all()
    
    ai_message = user_message
    file_errors = []
    
    if uploaded_files:
        file_contents = []
        for uploaded_file in uploaded_files:
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
    print(f"[DEBUG] LEX response: {lex_response[:100]}...")
    
    assistant_message = Message(
        tenant_id=g.tenant.id,
        chat_id=chat.id,
        role='assistant',
        content=lex_response
    )
    db.session.add(assistant_message)
    db.session.commit()
    
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
                message_id=assistant_message.id,
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
                'type': artifact.artifact_type
            })
        print(f"[DEBUG] Created {len(artifacts_created)} artifacts")
    
    print("[DEBUG] Response sent successfully")
    return jsonify({
        'response': lex_response,
        'artifacts': artifacts_created
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
    
    data = request.json
    new_title = data.get('title', '').strip()
    
    if new_title:
        chat.title = new_title
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False}), 400

@app.route('/api/chat/<int:chat_id>/delete', methods=['DELETE'])
@login_required
@tenant_required
def delete_chat(chat_id):
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    db.session.delete(chat)
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

@app.route('/api/upload', methods=['POST'])
@login_required
@tenant_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Geen bestand'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Geen bestand geselecteerd'}), 400
    
    chat_id = request.form.get('chat_id')
    
    s3_key = s3_service.upload_file(file, g.tenant.id)
    if not s3_key:
        return jsonify({'error': 'Upload mislukt'}), 500
    
    uploaded_file = UploadedFile(
        tenant_id=g.tenant.id,
        chat_id=chat_id if chat_id else None,
        filename=file.filename,
        original_filename=file.filename,
        s3_key=s3_key,
        file_size=0,
        mime_type=file.content_type
    )
    db.session.add(uploaded_file)
    db.session.commit()
    
    return jsonify({'success': True, 'file_id': uploaded_file.id})

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
            
            if User.query.filter_by(tenant_id=g.tenant.id, email=email).first():
                flash('Deze email is al in gebruik.', 'danger')
            else:
                user = User(
                    tenant_id=g.tenant.id,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    role='user'
                )
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                
                login_url = f"https://{g.tenant.subdomain}.lex-cao.replit.app/login"
                email_service.send_welcome_email(user, g.tenant, login_url)
                
                flash('Gebruiker toegevoegd!', 'success')
        
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

@app.route('/admin/templates', methods=['GET', 'POST'])
@login_required
@tenant_required
@admin_required
def admin_templates():
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        content = request.form.get('content')
        
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
    if plan not in ['professional', 'enterprise']:
        return "Invalid plan", 400
    
    success_url = url_for('billing_success', _external=True)
    cancel_url = url_for('admin_billing', _external=True)
    
    session_obj = StripeService.create_checkout_session(
        g.tenant.id, plan, success_url, cancel_url
    )
    
    if session_obj:
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
        return jsonify({'success': True})
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 400
    
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        tenant_id = session_obj['metadata'].get('tenant_id')
        
        if tenant_id:
            subscription = Subscription.query.filter_by(tenant_id=tenant_id).first()
            if subscription:
                subscription.status = 'active'
                subscription.stripe_customer_id = session_obj.get('customer')
                subscription.stripe_subscription_id = session_obj.get('subscription')
                
                tenant = Tenant.query.get(tenant_id)
                tenant.status = 'active'
                
                db.session.commit()
    
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        customer_id = invoice.get('customer')
        
        subscription = Subscription.query.filter_by(stripe_customer_id=customer_id).first()
        if subscription:
            tenant = Tenant.query.get(subscription.tenant_id)
            email_service.send_payment_failed_email(tenant)
    
    return jsonify({'success': True})

@app.route('/super-admin/dashboard')
@super_admin_required
def super_admin_dashboard():
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    total_users = User.query.count()
    
    return render_template('super_admin_dashboard.html', 
                         tenants=tenants, 
                         total_users=total_users)

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
        status='trial'
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
    
    if new_status in ['trial', 'active', 'suspended']:
        tenant.status = new_status
        db.session.commit()
        flash('Tenant status bijgewerkt!', 'success')
    
    return redirect(url_for('super_admin_dashboard'))

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
