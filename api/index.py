import os
import sys

# Ensure both the project root directory and current directories are on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

for p in (ROOT_DIR, CURRENT_DIR, os.getcwd()):
    if p and p not in sys.path:
        sys.path.insert(0, p)

# Import the WSGI Flask application
from app import app

# WSGI middleware to handle Vercel's backend rewrite routing and query strings
class VercelPathFix:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')

        # 1. Check if Vercel provided original forwarded path headers
        original_path = (
            environ.get('HTTP_X_FORWARDED_PATH') or
            environ.get('HTTP_X_VERCEL_PATH') or
            environ.get('HTTP_X_MATCHED_PATH')
        )
        
        target_path = original_path if (original_path and not original_path.startswith('/api/index')) else path

        # 2. Separate query string if embedded in target_path
        if '?' in target_path:
            clean_path, qs = target_path.split('?', 1)
            environ['PATH_INFO'] = clean_path
            if not environ.get('QUERY_STRING'):
                environ['QUERY_STRING'] = qs
        else:
            # 3. Normalize and strip /api/index.py, /api/index, or /api prefixes if needed
            for prefix in ('/api/index.py', '/api/index', '/api'):
                if target_path.startswith(prefix):
                    remainder = target_path[len(prefix):]
                    if remainder in ('', '/'):
                        target_path = '/'
                    elif remainder.startswith('/'):
                        target_path = remainder
                    break
            environ['PATH_INFO'] = target_path

        return self.wsgi_app(environ, start_response)

# Apply WSGI fix
app.wsgi_app = VercelPathFix(app.wsgi_app)

# Expose handler for Vercel serverless functions
handler = app

# For local invocation / testing
if __name__ == "__main__":
    app.run(debug=True)
