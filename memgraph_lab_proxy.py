#!/usr/bin/env python3
"""
Password-protected proxy for Memgraph Lab
Routes requests to the actual Memgraph Lab service
"""

from flask import Flask, request, Response, render_template_string
from werkzeug.security import check_password_hash, generate_password_hash
import os
import requests
import time
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(32)

# Configuration from environment
MEMGRAPH_LAB_TARGET = os.getenv('MEMGRAPH_LAB_TARGET', 'http://localhost:3001')
MEMGRAPH_LAB_PASSWORD = os.getenv('MEMGRAPH_LAB_PASSWORD', 'memgraph2025')
MEMGRAPH_LAB_PORT = int(os.getenv('MEMGRAPH_LAB_PORT', 5001))
SESSION_TIMEOUT = 3600  # 1 hour

# In-memory session store
active_sessions = {}

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Memgraph Lab - Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        form {
            display: flex;
            flex-direction: column;
        }
        label {
            color: #333;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 14px;
        }
        input {
            padding: 12px;
            margin-bottom: 20px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        button:active {
            transform: translateY(0);
        }
        .error {
            background: #fee;
            color: #c00;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
            font-size: 14px;
            display: none;
        }
        .error.show {
            display: block;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Memgraph Lab</h1>
        <p class="subtitle">Knowledge Graph Visualization</p>
        <form method="POST">
            <div class="error" id="error">{{ error }}</div>
            <label for="password">Administrator Password</label>
            <input type="password" id="password" name="password" required autofocus>
            <button type="submit">Access Lab</button>
        </form>
    </div>
    <script>
        if (document.getElementById('error').textContent.trim()) {
            document.getElementById('error').classList.add('show');
        }
    </script>
</body>
</html>
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for Memgraph Lab"""
    error = None
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        # Simple password check
        if password == MEMGRAPH_LAB_PASSWORD:
            # Generate session token
            import secrets
            token = secrets.token_urlsafe(32)
            active_sessions[token] = {
                'timestamp': time.time(),
                'ip': request.remote_addr
            }
            
            response = Response('''
                <html><head>
                    <title>Redirecting...</title>
                    <meta http-equiv="refresh" content="0; url=/lab/" />
                </head><body></body></html>
            ''', content_type='text/html')
            response.set_cookie('memgraph_session', token, max_age=SESSION_TIMEOUT, httponly=True, samesite='Lax')
            return response
        else:
            error = 'Invalid password. Please try again.'
    
    return render_template_string(LOGIN_TEMPLATE, error=error)

def require_session(f):
    """Decorator to check session token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check session cookie
        token = request.cookies.get('memgraph_session')
        
        if not token or token not in active_sessions:
            return Response('<meta http-equiv="refresh" content="0; url=/login" />', content_type='text/html')
        
        # Check timeout
        session_data = active_sessions[token]
        if time.time() - session_data['timestamp'] > SESSION_TIMEOUT:
            del active_sessions[token]
            return Response('<meta http-equiv="refresh" content="0; url=/login" />', content_type='text/html')
        
        # Update timestamp
        session_data['timestamp'] = time.time()
        return f(*args, **kwargs)
    
    return decorated

@app.route('/lab/', defaults={'path': ''})
@app.route('/lab/<path:path>')
@require_session
def memgraph_lab(path):
    """Proxy requests to Memgraph Lab"""
    try:
        # Build target URL
        target_url = f"{MEMGRAPH_LAB_TARGET}/lab/{path}"
        if request.query_string:
            target_url += f"?{request.query_string.decode()}"
        
        # Forward request
        response = requests.request(
            method=request.method,
            url=target_url,
            headers={key: value for key, value in request.headers if key.lower() not in ['host', 'connection']},
            data=request.get_data(),
            allow_redirects=False,
            timeout=30
        )
        
        # Return response
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
    
    except Exception as e:
        return f"<h1>Error connecting to Memgraph Lab</h1><p>{str(e)}</p>", 502

@app.route('/logout')
def logout():
    """Logout"""
    token = request.cookies.get('memgraph_session')
    if token and token in active_sessions:
        del active_sessions[token]
    
    response = Response('<meta http-equiv="refresh" content="0; url=/login" />', content_type='text/html')
    response.delete_cookie('memgraph_session')
    return response

@app.route('/')
def index():
    """Redirect to login or lab"""
    token = request.cookies.get('memgraph_session')
    if token and token in active_sessions and time.time() - active_sessions[token]['timestamp'] < SESSION_TIMEOUT:
        return Response('<meta http-equiv="refresh" content="0; url=/lab/" />', content_type='text/html')
    else:
        return Response('<meta http-equiv="refresh" content="0; url=/login" />', content_type='text/html')

if __name__ == '__main__':
    print(f"""
    ╔════════════════════════════════════════════════════════════╗
    ║  Memgraph Lab Proxy - Password Protected                   ║
    ╠════════════════════════════════════════════════════════════╣
    ║  Local URL: http://localhost:{MEMGRAPH_LAB_PORT}                           ║
    ║  Production: https://lexiai.nl/memgraph/                    ║
    ║  Default Password: memgraph2025                             ║
    ║  To change: set MEMGRAPH_LAB_PASSWORD environment variable  ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    app.run(host='0.0.0.0', port=MEMGRAPH_LAB_PORT, debug=False, use_reloader=False)

