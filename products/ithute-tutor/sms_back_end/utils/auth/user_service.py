from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import User
from utils.auth.password_hash_verify import hash_password

def create_user_login(db: Session, payload, password: str):
    password_hashed = hash_password(password)
    user = User(
        id=payload.id,
        password=password_hashed
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return payload



def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def get_user(db: Session, user_id: str):
    return db.query(User).filter(User.id == user_id).first()
