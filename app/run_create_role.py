from app import create_app, db
from app.models import Role

app = create_app()

with app.app_context():
    # Create roles if they don't already exist
    roles = ['tenant', 'landlord']
    
    for role_name in roles:
        existing = Role.query.filter_by(name=role_name).first()
        if not existing:
            new_role = Role(name=role_name.lower())  # Ensuring lowercase
            db.session.add(new_role)
            print(f"✅ Added role: {role_name.lower()}")
        else:
            print(f"ℹ️ Role already exists: {role_name.lower()}")
    
    db.session.commit()
    print("🎉 Role creation completed.")
