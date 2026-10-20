import os
import sys

# Ensure the project root directory is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Import the WSGI Flask application
from app import app

# WSGI middleware to handle Vercel's backend rewrite routing
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
        if original_path and not original_path.startswith('/api/index'):
            environ['PATH_INFO'] = original_path
        else:
            # 2. Normalize and strip /api/index.py, /api/index, or /api prefixes
            for prefix in ('/api/index.py', '/api/index', '/api'):
                if path.startswith(prefix):
                    remainder = path[len(prefix):]
                    if remainder in ('', '/'):
                        environ['PATH_INFO'] = '/'
                    elif remainder.startswith('/'):
                        environ['PATH_INFO'] = remainder
                    break

        return self.wsgi_app(environ, start_response)

# Apply WSGI fix
app.wsgi_app = VercelPathFix(app.wsgi_app)


# For local invocation / testing
if __name__ == "__main__":
    app.run(debug=True)
