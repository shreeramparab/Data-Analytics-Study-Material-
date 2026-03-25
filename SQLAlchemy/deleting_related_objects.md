# Deleting Related Objects in SQLAlchemy

There are **4 completely different ways** this works.  
Get them confused and you either leak orphan rows or nuke data you didn't mean to.

---

## 1. `ondelete="CASCADE"` — Database Level

The **DB itself** deletes children when parent is deleted. SQLAlchemy doesn't even know it happened.

```python
class Post(Base):
    __tablename__ = "posts"

    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    #                                                  ↑ DB handles deletion
```

```python
with Session(engine) as session:
    user = session.query(User).get(1)
    session.delete(user)
    session.commit()
    # MySQL deletes all posts automatically — SQLAlchemy did nothing
```

> ⚠️ **Problem:** SQLAlchemy's in-memory session doesn't know those posts were deleted.  
> If you still have post objects loaded in the session → they become stale/inconsistent.

---

## 2. `cascade="all, delete-orphan"` — SQLAlchemy Level

SQLAlchemy **itself** deletes children before sending DELETE to DB.

```python
class User(Base):
    __tablename__ = "users"

    id    = Column(Integer, primary_key=True)
    posts = relationship(
        "Post",
        back_populates="author",
        cascade="all, delete-orphan"   # ← SQLAlchemy deletes posts first
    )
```

```python
with Session(engine) as session:
    user = session.query(User).get(1)
    session.delete(user)
    session.commit()
```

**What SQLAlchemy actually sends to DB:**
```sql
DELETE FROM posts WHERE user_id = 1;   -- children first
DELETE FROM users WHERE id = 1;        -- then parent
```

> ✅ Session stays consistent because SQLAlchemy tracks every deletion itself.

---

## 3. `cascade` Options — Know All of Them

```python
# Default — only save/update propagates
posts = relationship("Post", cascade="save-update, merge")

# Delete parent → delete children
posts = relationship("Post", cascade="all, delete")

# Delete parent → delete children AND delete orphaned children
posts = relationship("Post", cascade="all, delete-orphan")
#                                              ↑ also deletes post if removed from user.posts list

# Nuclear — everything propagates
posts = relationship("Post", cascade="all")
```

| Cascade Option | What It Does |
|---|---|
| `save-update` | Adding parent to session also adds children |
| `merge` | `session.merge()` propagates to children |
| `delete` | Deleting parent deletes children |
| `delete-orphan` | Child removed from collection → also deleted |
| `expunge` | Removing parent from session removes children |
| `all` | Everything except `delete-orphan` |
| `all, delete-orphan` | **Most common production choice** ✅ |

---

## 4. `delete-orphan` — The Subtle One

Triggers when you **remove a child from the collection** without explicitly deleting it.

```python
class User(Base):
    posts = relationship("Post", cascade="all, delete-orphan")
```

```python
with Session(engine) as session:
    user = session.query(User)\
        .options(selectinload(User.posts))\
        .get(1)

    post_to_remove = user.posts[0]
    user.posts.remove(post_to_remove)    # ← orphan detected

    session.commit()
    # SQLAlchemy deletes that post from DB automatically
```

**Without `delete-orphan`:**
```python
user.posts.remove(post_to_remove)
session.commit()
# post still exists in DB with user_id = NULL  →  or throws IntegrityError
```

---

## 5. Combining Both — The RIGHT Way

Use **both** `ondelete` on FK **and** `cascade` on relationship together.

```python
class Post(Base):
    __tablename__ = "posts"
    id      = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    #                                                  ↑ DB fallback

class User(Base):
    __tablename__ = "users"
    id    = Column(Integer, primary_key=True)
    posts = relationship("Post",
                         back_populates="author",
                         cascade="all, delete-orphan",
                         passive_deletes=True)
    #                    ↑ tells SQLAlchemy: trust the DB, don't SELECT children first
```

**`passive_deletes=True` tells SQLAlchemy:**
- Don't SELECT children before deleting parent
- Trust the DB `CASCADE` to handle it
- Saves a round trip to DB

---

## 6. Manually Deleting a Child

```python
with Session(engine) as session:
    post = session.query(Post).get(5)
    session.delete(post)    # explicit delete
    session.commit()
    # DELETE FROM posts WHERE id = 5
```

---

## 7. Bulk Delete — Never Loop `session.delete()`

```python
# ❌ WRONG — loads every object into memory, then deletes one by one
with Session(engine) as session:
    posts = session.query(Post).filter(Post.user_id == 1).all()
    for post in posts:
        session.delete(post)   # N round trips to DB
    session.commit()

# ✅ RIGHT — single DELETE query, nothing loaded into memory
with Session(engine) as session:
    session.query(Post)\
        .filter(Post.user_id == 1)\
        .delete(synchronize_session=False)
    session.commit()
    # DELETE FROM posts WHERE user_id = 1
```

| `synchronize_session` | Behavior |
|---|---|
| `"evaluate"` | Default — tries to update session in memory |
| `"fetch"` | SELECTs rows first, then deletes, updates session |
| `False` | No session sync — fastest ✅ use when you don't need those objects anymore |

---

## 8. Many-to-Many Deletion

```python
post_tags = Table(
    "post_tags", Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id",  Integer, ForeignKey("tags.id",  ondelete="CASCADE"), primary_key=True),
)

class Post(Base):
    tags = relationship("Tag", secondary=post_tags, back_populates="posts")
```

```python
with Session(engine) as session:
    post = session.query(Post)\
        .options(selectinload(Post.tags))\
        .get(1)

    # Remove one tag — deletes association row only, NOT the tag itself
    post.tags.remove(tag)
    session.commit()
    # DELETE FROM post_tags WHERE post_id=1 AND tag_id=X

    # Delete the post — cascades to post_tags automatically
    session.delete(post)
    session.commit()
    # DELETE FROM post_tags WHERE post_id = 1
    # DELETE FROM posts WHERE id = 1
```

---

## Rules Burned Into Your Brain

| Rule | Meaning |
|---|---|
| `ondelete="CASCADE"` | DB deletes — SQLAlchemy unaware. Use with `passive_deletes=True` |
| `cascade="all, delete-orphan"` | SQLAlchemy deletes — session stays consistent |
| `passive_deletes=True` | Trust DB cascade, skip SELECT before DELETE |
| `delete-orphan` | Child removed from list → deleted from DB |
| Bulk delete | `.delete(synchronize_session=False)` — never loop `session.delete()` |
| Many-to-many delete | Removes association row only — NOT the related object |
