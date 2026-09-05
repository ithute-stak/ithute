# models/user_role.py

import enum
from sqlalchemy import Column, Enum
from database.base import Base
from database.multi_tenant_school_management.schemas.user import UserRole


class Role(Base):
    __tablename__ = "roles"
    name = Column(Enum(UserRole), unique=True, nullable=False)