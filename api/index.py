import os
import sys

# Ensure the project root directory is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Import the WSGI Flask application
from app import app

# For local invocation / testing
if __name__ == "__main__":
    app.run(debug=True)
