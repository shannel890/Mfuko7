import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from app import create_app

app = create_app()  # Vercel will detect this WSGI app
