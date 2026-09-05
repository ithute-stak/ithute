from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import User
from database.multi_tenant_school_management.models.social.post import (
    FeedComment,
    FeedLike,
    FeedPost,
    FeedShare,
)
from database.multi_tenant_school_management.schemas.social.feed import (
    FeedCommentCreate,
    FeedCommentRead,
    FeedPostCreate,
    FeedPostRead,
    FeedShareCreate,
)
from database.session import get_db
from utils.auth.tokens import get_current_user
from utils.school_context import SchoolContext, get_school_context
from ws.events.feed_events import (
    feed_comment_created_socket,
    feed_post_created_socket,
    feed_post_liked_socket,
    feed_post_shared_socket,
)

router = APIRouter(prefix="/feed", tags=["Feed"])


def _post_to_response(db: Session, post: FeedPost, current_user: User):
    data = jsonable_encoder(post)
    data["likes_count"] = db.query(FeedLike).filter(FeedLike.post_id == post.id).count()
    data["comments_count"] = db.query(FeedComment).filter(FeedComment.post_id == post.id).count()
    data["shares_count"] = db.query(FeedShare).filter(FeedShare.post_id == post.id).count()
    data["liked_by_me"] = (
        db.query(FeedLike)
        .filter(FeedLike.post_id == post.id, FeedLike.user_id == current_user.id)
        .first()
        is not None
    )
    return data


def _school_post(db: Session, post_id: UUID, context: SchoolContext) -> FeedPost:
    post = (
        db.query(FeedPost)
        .filter(FeedPost.id == post_id, FeedPost.school_id == context.school_id)
        .first()
    )
    if post is None:
        # Return 404 instead of exposing that another school's post exists.
        raise HTTPException(status_code=404, detail="Post not found in this school")
    return post


@router.post("/posts", response_model=FeedPostRead, status_code=status.HTTP_201_CREATED)
async def create_post(
    payload: FeedPostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    post = FeedPost(
        school_id=context.school_id,
        author_id=current_user.id,
        title=payload.title,
        content=payload.content,
        subject=payload.subject,
        post_type=payload.post_type,
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    response = _post_to_response(db, post, current_user)
    await feed_post_created_socket(response)
    return response


@router.get("/posts", response_model=list[FeedPostRead])
def get_feed_posts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    posts = (
        db.query(FeedPost)
        .filter(FeedPost.school_id == context.school_id, FeedPost.is_published.is_(True))
        .order_by(FeedPost.created_at.desc())
        .all()
    )
    return [_post_to_response(db, post, current_user) for post in posts]


@router.post("/posts/{post_id}/comments", response_model=FeedCommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: UUID,
    payload: FeedCommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    _school_post(db, post_id, context)
    comment = FeedComment(post_id=post_id, author_id=current_user.id, content=payload.content)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    await feed_comment_created_socket(jsonable_encoder(comment))
    return comment


@router.get("/posts/{post_id}/comments", response_model=list[FeedCommentRead])
def get_comments(
    post_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    _school_post(db, post_id, context)
    return (
        db.query(FeedComment)
        .filter(FeedComment.post_id == post_id)
        .order_by(FeedComment.created_at.asc())
        .all()
    )


@router.post("/posts/{post_id}/like")
async def toggle_like_post(
    post_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    _school_post(db, post_id, context)
    existing = (
        db.query(FeedLike)
        .filter(FeedLike.post_id == post_id, FeedLike.user_id == current_user.id)
        .first()
    )

    liked = False
    if existing:
        db.delete(existing)
    else:
        liked = True
        db.add(FeedLike(post_id=post_id, user_id=current_user.id))
    db.commit()

    data = {
        "post_id": str(post_id),
        "user_id": str(current_user.id),
        "liked": liked,
        "likes_count": db.query(FeedLike).filter(FeedLike.post_id == post_id).count(),
    }
    await feed_post_liked_socket(data)
    return data


@router.post("/posts/{post_id}/share")
async def share_post(
    post_id: UUID,
    payload: FeedShareCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    _school_post(db, post_id, context)
    share = FeedShare(post_id=post_id, user_id=current_user.id, caption=payload.caption)
    db.add(share)
    db.commit()
    db.refresh(share)

    data = jsonable_encoder(share)
    await feed_post_shared_socket(data)
    return {"message": "Post shared successfully", "share": data}
