from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FeedPostCreate(BaseModel):
    title: Optional[str] = None
    content: str
    subject: Optional[str] = None
    post_type: str = "post"


class FeedPostRead(BaseModel):
    id: UUID
    school_id: UUID
    author_id: UUID
    title: Optional[str] = None
    content: str
    subject: Optional[str] = None
    post_type: str
    is_published: bool
    created_at: datetime
    updated_at: datetime

    likes_count: int = 0
    comments_count: int = 0
    shares_count: int = 0
    liked_by_me: bool = False

    model_config = ConfigDict(from_attributes=True)


class FeedCommentCreate(BaseModel):
    content: str


class FeedCommentRead(BaseModel):
    id: UUID
    post_id: UUID
    author_id: UUID
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedShareCreate(BaseModel):
    caption: Optional[str] = None