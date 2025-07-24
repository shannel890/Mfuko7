# run_create_role.py
from app import create_app, db
from app.models import Role

app = create_app()
with app.app_context():
    role = Role(name='tenant')
    db.session.add(role)
    db.session.commit()
    print("Tenant role created.")
