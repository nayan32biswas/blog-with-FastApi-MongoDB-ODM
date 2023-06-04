import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, Query, status
from mongodb_odm import ODMObjectId
from slugify import slugify

from app.base.custom_types import ObjectIdStr
from app.base.exceptions import CustomException, ExType
from app.base.utils import get_offset, update_partially
from app.base.utils.string import rand_slug_str
from app.base.utils.query import get_object_or_404
from app.user.dependencies import get_authenticated_user, get_authenticated_user_or_none
from app.user.models import User

from ..models import Post, Topic
from ..schemas.posts import (
    PostCreate,
    PostDetailsOut,
    PostListOut,
    PostOut,
    PostUpdate,
    TopicIn,
    TopicOut,
)

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)


@router.post("/topics", status_code=status.HTTP_201_CREATED, response_model=TopicOut)
def create_topics(
    topic_data: TopicIn,
    user: User = Depends(get_authenticated_user),
) -> Any:
    name = topic_data.name.lower()

    topic, created = Topic.get_or_create({"name": name})
    if created:
        updated = False
        slug = slugify(topic.name)

        for i in range(1, 10):
            try:
                new_slug = f"{slug}-{rand_slug_str(i)}" if i > 1 else slug
                topic.update({"$set": {"user_id": user.id, "slug": new_slug}})
                topic.slug = new_slug
                updated = True
                break
            except Exception:
                pass
        if updated is False:
            topic.delete()
            raise CustomException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name error",
                code=ExType.VALIDATION_ERROR,
                field="name",
            )
    return TopicOut.from_orm(topic)


@router.get("/topics", status_code=status.HTTP_200_OK)
def get_topics(
    page: int = 1,
    limit: int = 20,
    q: Optional[str] = Query(default=None),
    _: Optional[User] = Depends(get_authenticated_user_or_none),
) -> Any:
    offset = get_offset(page, limit)
    filter: Dict[str, Any] = {}
    if q:
        filter["name"] = re.compile(q, re.IGNORECASE)

    topic_qs = Topic.find(filter=filter, limit=limit, skip=offset)
    results = [TopicOut.from_orm(topic) for topic in topic_qs]

    topic_count = Topic.count_documents(filter=filter)

    return {"count": topic_count, "results": results}


def get_short_description(description: Optional[str]) -> str:
    if description:
        return description[:200]
    return ""


@router.post(
    "/posts",
    status_code=status.HTTP_201_CREATED,
    response_model=PostDetailsOut,
)
def create_posts(
    post_data: PostCreate, user: User = Depends(get_authenticated_user)
) -> Any:
    short_description = post_data.short_description
    if not post_data.short_description:
        short_description = get_short_description(post_data.description)

    topic_ids = [
        obj["_id"] for obj in Topic.find_raw({"slug": {"$in": post_data.topics}})
    ]

    post = Post(
        author_id=user.id,
        slug=str(ObjectId()),
        title=post_data.title,
        short_description=short_description,
        description=post_data.description,
        cover_image=post_data.cover_image,
        publish_at=post_data.publish_at,
        topic_ids=topic_ids,
    ).create()

    is_slug_saved = False
    slug = slugify(post.title)
    for i in range(1, 10):
        try:
            new_slug = f"{slug}-{rand_slug_str(i)}" if i > 1 else slug
            post.update(raw={"$set": {"slug": new_slug}})
            post.slug = new_slug
            is_slug_saved = True
            break
        except Exception:
            pass
    if is_slug_saved is False:
        post.delete()
        raise CustomException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title error",
            code=ExType.VALIDATION_ERROR,
            field="title",
        )

    return PostOut.from_orm(post).dict()


@router.get("/posts", status_code=status.HTTP_200_OK)
def get_posts(
    page: int = 1,
    limit: int = 20,
    q: Optional[str] = Query(default=None),
    topics: List[ObjectIdStr] = Query(default=[]),
    author_id: Optional[ObjectIdStr] = Query(default=None),
    _: Optional[User] = Depends(get_authenticated_user_or_none),
) -> Dict[str, Any]:
    offset = get_offset(page, limit)
    filter: Dict[str, Any] = {
        "publish_at": {"$ne": None, "$lt": datetime.utcnow()},
    }
    if author_id:
        filter["author_id"] = ObjectId(author_id)
    if topics:
        filter["topic_ids"] = {"$in": [ODMObjectId(id) for id in topics]}
    if q:
        filter["title"] = q

    post_qs = Post.find(
        filter=filter, limit=limit, skip=offset, projection={"description": 0}
    )
    results = [PostListOut.from_orm(post).dict() for post in Post.load_related(post_qs)]

    post_count = Post.count_documents(filter=filter)

    return {"count": post_count, "results": results}


@router.get("/posts/{slug}", status_code=status.HTTP_200_OK)
def get_post_details(
    slug: str,
    _: Optional[User] = Depends(get_authenticated_user_or_none),
) -> Any:
    filter: Dict[str, Any] = {
        "slug": slug,
        "publish_at": {"$ne": None, "$lt": datetime.utcnow()},
    }
    try:
        post = Post.get(filter=filter)
        post.author = User.get({"_id": post.author_id})
    except Exception:
        raise CustomException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ExType.OBJECT_NOT_FOUND,
            detail="Object not found.",
        )
    post.topics = [
        TopicOut.from_orm(topic) for topic in Topic.find({"_id": {"$in": post.topic_ids}})
    ]

    return PostDetailsOut.from_orm(post).dict()


@router.patch("/posts/{slug}", status_code=status.HTTP_200_OK)
def update_posts(
    slug: str,
    post_data: PostUpdate,
    user: User = Depends(get_authenticated_user),
) -> Any:
    post = get_object_or_404(Post, {"slug": slug})

    if post.author_id != user.id:
        raise CustomException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ExType.PERMISSION_ERROR,
            detail="You don't have access to update this post.",
        )

    post = update_partially(post, post_data)

    post.short_description = post_data.short_description
    if not post.short_description and post_data.description:
        post.short_description = get_short_description(post_data.description)
    post.update()

    return {"message": "Post Updated"}


@router.delete("/posts/{slug}", status_code=status.HTTP_200_OK)
def delete_post(
    slug: str,
    user: User = Depends(get_authenticated_user),
) -> Any:
    post = get_object_or_404(Post, {"slug": slug})

    if post.author_id != user.id:
        raise CustomException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ExType.PERMISSION_ERROR,
            detail="You don't have access to delete this post.",
        )
    return {"message": "Deleted"}
