# ==============================================================================
# Lexi AI - Production Gunicorn Configuration
# ==============================================================================
# Optimized for google-genai and Vertex AI deployment
# Prevents AttributeError crashes and worker failures
# ==============================================================================

import multiprocessing
import os

# ==============================================================================
# WORKER CONFIGURATION
# ==============================================================================

# CRITICAL: Use 'sync' worker class (NOT gevent/eventlet)
# google-genai client is not async-safe and crashes with async workers
worker_class = 'sync'

# Worker count: 2-4 workers recommended for most deployments
# Formula: (2 × CPU cores) + 1
# Override with GUNICORN_WORKERS env variable
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

# CRITICAL: Enable preload_app to initialize VertexAI client ONCE
# This prevents multiple client initializations and reduces crashes
# The singleton pattern in services.py works best with preload_app=True
preload_app = True

# ==============================================================================
# TIMEOUT CONFIGURATION
# ==============================================================================

# Request timeout: 120 seconds (Vertex AI can be slow for complex queries)
timeout = 120

# Graceful timeout: Give workers time to finish current requests
# CRITICAL: Prevents AttributeError during shutdown
graceful_timeout = 120

# Keep-alive: Close idle connections after 5 seconds
keepalive = 5

# ==============================================================================
# BINDING & NETWORKING
# ==============================================================================

# Bind to all interfaces on port 5000
# Use --reuse-port for horizontal scaling (load balancer support)
bind = '0.0.0.0:5000'

# CRITICAL: Enable socket reuse for autoscaling deployments
# Allows multiple gunicorn processes to bind to same port
reuse_port = True

# ==============================================================================
# LOGGING
# ==============================================================================

# Access log: Log all requests
accesslog = '-'  # stdout

# Error log: Log errors and worker lifecycle events
errorlog = '-'   # stderr
# Capture stdout/stderr
capture_output = True
enable_stdio_inheritance = True

# Show full tracebacks
log_config = None
# Log level: info for production, debug for troubleshooting
loglevel = os.getenv('LOG_LEVEL', 'info')

# ==============================================================================
# WORKER LIFECYCLE & HEALTH
# ==============================================================================

# Max requests per worker before restart (prevent memory leaks)
# Set to 0 to disable worker recycling
max_requests = int(os.getenv('MAX_REQUESTS', 1000))

# Add jitter to prevent all workers restarting simultaneously
max_requests_jitter = 100

# Worker temporary directory (for large file uploads)
worker_tmp_dir = '/dev/shm'  # Use RAM disk for better performance

# ==============================================================================
# SECURITY
# ==============================================================================

# Limit request line size (prevent header injection attacks)
limit_request_line = 4096

# Limit header size
limit_request_fields = 100
limit_request_field_size = 8190

# ==============================================================================
# PRODUCTION OPTIMIZATIONS
# ==============================================================================

# Disable sendfile (can cause issues with some file systems)
sendfile = False

# Enable access log format with response time
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ==============================================================================
# HOOKS (Optional - for monitoring/debugging)
# ==============================================================================

def on_starting(server):
    """Called just before the master process is initialized"""
    print("=" * 80)
    print("🚀 Starting Lexi AI Production Server")
    print("=" * 80)
    print(f"Workers: {workers}")
    print(f"Worker class: {worker_class}")
    print(f"Preload app: {preload_app}")
    print(f"Timeout: {timeout}s")
    print(f"Bind: {bind}")
    print("=" * 80)

def on_reload(server):
    """Called when a worker is reloaded"""
    print("🔄 Worker reloaded")

def worker_exit(server, worker):
    """Called when a worker exits"""
    print(f"👷 Worker {worker.pid} exited")

# ==============================================================================
# GOOGLE-GENAI SPECIFIC SETTINGS
# ==============================================================================

# IMPORTANT NOTES:
# 1. The singleton pattern in services.py prevents multiple client initializations
# 2. preload_app=True ensures VertexAI client is initialized once in master process
# 3. Workers inherit the initialized client (no re-initialization = no crashes)
# 4. The improved __del__ method in services.py prevents AttributeError on shutdown
# 5. graceful_timeout gives workers time to clean up properly

# ==============================================================================
# DEPLOYMENT INSTRUCTIONS
# ==============================================================================

# To use this configuration:
# 
# 1. Development (Replit):
#    gunicorn --config gunicorn.conf.py main:app
#
# 2. Production (Hetzner with systemd):
#    Create /etc/systemd/system/lexiai.service:
#    
#    [Unit]
#    Description=Lexi AI Production Server
#    After=network.target
#    
#    [Service]
#    User=www-data
#    WorkingDirectory=/var/www/lexiai
#    Environment="PATH=/var/www/lexiai/venv/bin"
#    Environment="DATABASE_URL=..."
#    Environment="GOOGLE_APPLICATION_CREDENTIALS=..."
#    ExecStart=/var/www/lexiai/venv/bin/gunicorn --config gunicorn.conf.py main:app
#    Restart=always
#    RestartSec=10
#    
#    [Install]
#    WantedBy=multi-user.target
#
# 3. Enable and start:
#    sudo systemctl daemon-reload
#    sudo systemctl enable lexiai
#    sudo systemctl start lexiai
#    sudo systemctl status lexiai

# ==============================================================================
