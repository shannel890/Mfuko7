import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from app import create_app
app = create_app()
if __name__ == "__main__":
    app.run()