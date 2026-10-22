import os
import sys
from urllib.parse import parse_qsl, urlencode

# Ensure both the project root directory and current directories are on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

for p in (ROOT_DIR, CURRENT_DIR, os.getcwd()):
    if p and p not in sys.path:
        sys.path.insert(0, p)

# Import the WSGI Flask application
from app import app


# WSGI middleware that restores the original request path.
#
# vercel.json rewrites every request to /api/index and passes the original
# path in the __ssp_path query parameter (destination:
# "/api/index?__ssp_path=:path*"), so PATH_INFO arrives as /api/index for
# every request and Flask would route everything to "/". This middleware
# swaps in the real path and removes the helper parameter from the query
# string. If __ssp_path is absent (local runs, direct /api/index calls) the
# request is passed through untouched.
class VercelPathFix:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # TEMPORARY DIAGNOSTIC: dump what Vercel actually delivers.
        if environ.get("HTTP_X_DEBUG_DUMP") == "1":
            import json

            keys = [
                "REQUEST_METHOD",
                "PATH_INFO",
                "QUERY_STRING",
                "SCRIPT_NAME",
                "HTTP_X_FORWARDED_PATH",
                "HTTP_X_VERCEL_PATH",
                "HTTP_X_MATCHED_PATH",
                "HTTP_X_VERCEL_ORIGINAL_PATH",
                "HTTP_X_INVOKE_PATH",
                "HTTP_X_ORIGINAL_URL",
                "HTTP_X_FORWARDED_URI",
                "REQUEST_URI",
                "RAW_URI",
            ]
            dump = {k: environ.get(k) for k in keys}
            body = json.dumps(dump, indent=1).encode()
            start_response(
                "200 OK",
                [("Content-Type", "application/json"), ("Content-Length", str(len(body)))],
            )
            return [body]
        qs = environ.get("QUERY_STRING", "")
        if qs:
            pairs = parse_qsl(qs, keep_blank_values=True)
            path_val = None
            kept = []
            for key, value in pairs:
                if key == "__ssp_path" and path_val is None:
                    path_val = value
                else:
                    kept.append((key, value))
            if path_val is not None:
                environ["PATH_INFO"] = "/" + path_val if path_val else "/"
                environ["QUERY_STRING"] = urlencode(kept)
        return self.wsgi_app(environ, start_response)


# Apply WSGI fix
app.wsgi_app = VercelPathFix(app.wsgi_app)

# Expose handler for Vercel serverless functions
handler = app

# For local invocation / testing
if __name__ == "__main__":
    app.run(debug=True)
