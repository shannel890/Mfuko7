import os

# Google OAuth permits HTTP redirect URLs only during local development.
if os.getenv('APP_ENV', os.getenv('FLASK_ENV', 'development')) == 'development':
    os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')

from app import create_app

app = create_app()  # Vercel detects this WSGI app.


if __name__ == '__main__':
    app.run(
        host=os.getenv('HOST', '127.0.0.1'),
        port=int(os.getenv('PORT', '5000')),
        debug=os.getenv('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes'),
    )
