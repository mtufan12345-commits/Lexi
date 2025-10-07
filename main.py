import os
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
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['WTF_CSRF_SSL_STRICT'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True

csrf = CSRFProtect(app)
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
    
    host = request.host.split(':')[0]
    parts = host.split('.')
    
    if len(parts) >= 2 and parts[0] not in ['www', 'lex-cao', 'lex-cao-expert']:
        subdomain = parts[0]
        tenant = Tenant.query.filter_by(subdomain=subdomain).first()
        if tenant:
            g.tenant = tenant

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
        
        login_url = f"https://{subdomain}.lex-cao.replit.app/login"
        email_service.send_welcome_email(admin_user, tenant, login_url)
        
        flash('Account aangemaakt! Je kunt nu inloggen.', 'success')
        return redirect(login_url)
    
    return render_template('signup_tenant.html')

@app.route('/login', methods=['GET', 'POST'])
@tenant_required
def login():
    if current_user.is_authenticated and not g.is_super_admin:
        return redirect(url_for('chat_page'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(tenant_id=g.tenant.id, email=email).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Je account is gedeactiveerd.', 'danger')
                return render_template('login.html', tenant=g.tenant)
            
            if g.tenant.status not in ['trial', 'active']:
                flash('Je account is verlopen. Neem contact op met de administrator.', 'warning')
                return render_template('login.html', tenant=g.tenant)
            
            if user.session_token:
                flash('Er is al een actieve sessie op een ander apparaat. Log daar eerst uit.', 'warning')
                return render_template('login.html', tenant=g.tenant)
            
            user.session_token = secrets.token_hex(32)
            db.session.commit()
            
            login_user(user)
            session['session_token'] = user.session_token
            session['is_super_admin'] = False
            
            return redirect(url_for('chat_page'))
        
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

@app.route('/logout')
@login_required
def logout():
    if not g.is_super_admin and isinstance(current_user, User):
        current_user.session_token = None
        db.session.commit()
    
    logout_user()
    session.clear()
    return redirect(url_for('login') if g.tenant else url_for('index'))

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
    
    messages = [{'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat()} 
                for m in chat.messages]
    
    return jsonify({'id': chat.id, 'title': chat.title, 'messages': messages})

@app.route('/api/chat/<int:chat_id>/message', methods=['POST'])
@login_required
@tenant_required
def send_message(chat_id):
    chat = Chat.query.filter_by(
        id=chat_id,
        tenant_id=g.tenant.id,
        user_id=current_user.id
    ).first_or_404()
    
    data = request.json
    user_message = data.get('message', '')
    
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
    
    lex_response = vertex_ai_service.chat(user_message)
    
    assistant_message = Message(
        tenant_id=g.tenant.id,
        chat_id=chat.id,
        role='assistant',
        content=lex_response
    )
    db.session.add(assistant_message)
    db.session.commit()
    
    return jsonify({'response': lex_response})

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
    
    return render_template('admin_dashboard.html', 
                         tenant=g.tenant, 
                         users=users, 
                         total_chats=total_chats,
                         subscription=subscription)

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
@csrf.exempt
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
