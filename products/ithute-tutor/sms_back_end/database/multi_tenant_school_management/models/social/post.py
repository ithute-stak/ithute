import enum

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class PostType(str, enum.Enum):
    post = "post"
    question = "question"
    announcement = "announcement"
    assignment = "assignment"
    note = "note"
    video = "video"
    poll = "poll"


class FeedPost(Base):
    __tablename__ = "feed_posts"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    subject = Column(String, nullable=True)
    post_type = Column(String, default=PostType.post.value)

    is_published = Column(Boolean, default=True)

    author = relationship("User")
    comments = relationship("FeedComment", back_populates="post", cascade="all, delete")
    likes = relationship("FeedLike", back_populates="post", cascade="all, delete")
    shares = relationship("FeedShare", back_populates="post", cascade="all, delete")


class FeedComment(Base):
    __tablename__ = "feed_comments"

    post_id = Column(UUID(as_uuid=True), ForeignKey("feed_posts.id"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    content = Column(Text, nullable=False)

    post = relationship("FeedPost", back_populates="comments")
    author = relationship("User")


class FeedLike(Base):
    __tablename__ = "feed_likes"

    post_id = Column(UUID(as_uuid=True), ForeignKey("feed_posts.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    post = relationship("FeedPost", back_populates="likes")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_feed_like_post_user"),
    )


class FeedShare(Base):
    __tablename__ = "feed_shares"

    post_id = Column(UUID(as_uuid=True), ForeignKey("feed_posts.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    caption = Column(Text, nullable=True)

    post = relationship("FeedPost", back_populates="shares")
    user = relationship("User")