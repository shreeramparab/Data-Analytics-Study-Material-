# Eager Loading in SQLAlchemy

By default SQLAlchemy uses **lazy loading** — it hits the DB again every time you access a relationship. Eager loading fixes that by fetching everything in **one shot**.

---

## The Problem — Lazy Loading (N+1 query hell)

```python
with Session(engine) as session:
    users = session.query(User).all()       # Query 1: SELECT * FROM users

    for user in users:
        print(user.posts)                   # Query 2,3,4,5... one per user
```

If you have 100 users → **101 queries**. This will destroy your app's performance.

---

## Solution 1 — `joinedload` (LEFT OUTER JOIN)

```python
from sqlalchemy.orm import joinedload

with Session(engine) as session:
    users = session.query(User)\
        .options(joinedload(User.posts))\
        .all()

    for user in users:
        print(user.posts)                   # NO extra query — already loaded
```

**Generated SQL:**
```sql
SELECT users.*, posts.*
FROM users
LEFT OUTER JOIN posts ON posts.user_id = users.id
```

> ✅ Use when: **one-to-one** or **many-to-one** relationships. Works fine for small result sets.

---

## Solution 2 — `subqueryload` (Separate subquery)

```python
from sqlalchemy.orm import subqueryload

with Session(engine) as session:
    users = session.query(User)\
        .options(subqueryload(User.posts))\
        .all()
```

**Generated SQL:**
```sql
SELECT * FROM users;

SELECT posts.* FROM posts
WHERE posts.user_id IN (
    SELECT users.id FROM users
)
```

> ✅ Use when: **one-to-many** or **many-to-many**. Better than `joinedload` for collections — JOIN duplicates parent rows.

---

## Solution 3 — `selectinload` ⭐ RECOMMENDED

```python
from sqlalchemy.orm import selectinload

with Session(engine) as session:
    users = session.query(User)\
        .options(selectinload(User.posts))\
        .all()
```

**Generated SQL:**
```sql
SELECT * FROM users;

SELECT * FROM posts
WHERE posts.user_id IN (1, 2, 3, 4, 5)
```

> ✅ Use when: **almost always** — cleanest and most efficient for collections.

---

## Load Multiple Relationships at Once

```python
with Session(engine) as session:
    users = session.query(User)\
        .options(
            selectinload(User.posts),
            joinedload(User.profile),
        )\
        .all()
```

---

## Nested Eager Loading (Relationship of a Relationship)

```python
with Session(engine) as session:
    # Load users → posts → tags  (3 levels deep)
    users = session.query(User)\
        .options(
            selectinload(User.posts)
                .selectinload(Post.tags)
        )\
        .all()

    for user in users:
        for post in user.posts:
            print(post.tags)               # zero extra queries
```

---

## Set Eager Loading on the Relationship (Always Eager)

```python
class User(Base):
    __tablename__ = "users"
    id    = Column(Integer, primary_key=True)
    posts = relationship("Post", back_populates="author", lazy="selectin")
```

| `lazy=` Option | Behavior |
|---|---|
| `"select"` | Default — lazy, hits DB on access |
| `"joined"` | Always `joinedload` |
| `"subquery"` | Always `subqueryload` |
| `"selectin"` | Always `selectinload` ✅ |
| `"dynamic"` | Returns a query object, not a list |
| `"noload"` | Never loads — always returns empty |
| `"raise"` | Raises error if accessed lazily |

---

## `raise` Loading — The Disciplined Approach

```python
# Model
class User(Base):
    posts = relationship("Post", lazy="raise")   # blow up if you forget

# ❌ This throws sqlalchemy.exc.InvalidRequestError
with Session(engine) as session:
    user = session.query(User).first()
    print(user.posts)

# ✅ You MUST be explicit
with Session(engine) as session:
    user = session.query(User)\
        .options(selectinload(User.posts))\
        .first()
    print(user.posts)
```

> Use `lazy="raise"` in production — no accidental N+1 queries ever slip through.

---

## Decision Rule

| Relationship | Strategy | Reason |
|---|---|---|
| One-to-One | `joinedload` | Single object, JOIN is fine |
| Many-to-One | `joinedload` | Single object per row |
| One-to-Many | `selectinload` | Collection — avoid row duplication |
| Many-to-Many | `selectinload` | Collection — always |
| Production | `lazy="raise"` | Force explicit loading everywhere |

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


# `save-update` vs `merge` Cascade in SQLAlchemy

---

## Setup

```python
class User(Base):
    __tablename__ = "users"
    id    = Column(Integer, primary_key=True)
    name  = Column(String(100))
    posts = relationship("Post", cascade="save-update, merge")

class Post(Base):
    __tablename__ = "posts"
    id      = Column(Integer, primary_key=True)
    title   = Column(String(100))
    user_id = Column(Integer, ForeignKey("users.id"))
```

---

# PART 1 — `save-update`

> When you `session.add(parent)` → children are **automatically tracked** in the session too.

---

## ❌ Without `save-update` — what breaks

```python
# Imagine cascade="merge"  (no save-update)

user = User(name="Alice")
post = Post(title="Alice's Post")
user.posts.append(post)             # linked in Python only

with Session(engine) as session:
    session.add(user)               # only user tracked
    session.commit()

# Result in DB:
# users  → Alice saved  ✅
# posts  → NOTHING      ❌  session never knew about post
```

---

## ✅ With `save-update` — what actually happens

```python
user = User(name="Alice")
post1 = Post(title="Post One")
post2 = Post(title="Post Two")

user.posts.append(post1)
user.posts.append(post2)

with Session(engine) as session:
    session.add(user)               # ONLY user explicitly added

    print(post1 in session)         # True  ← save-update pulled it in
    print(post2 in session)         # True  ← save-update pulled it in

    session.commit()

# Result in DB:
# users → Alice    ✅
# posts → Post One ✅  Post Two ✅
# All saved — zero extra session.add() calls
```

---

## ✅ Works in reverse too — child pulls parent in

```python
user = User(name="Bob")
post = Post(title="Bob's Post")
post.author = user                  # link child → parent

with Session(engine) as session:
    session.add(post)               # only post added
    session.commit()

# Result in DB:
# users → Bob          ✅  pulled in automatically
# posts → Bob's Post   ✅
```

---

## ❌ Without `save-update` — you write this garbage forever

```python
with Session(engine) as session:
    session.add(user)
    session.add(post1)              # manually add every single child
    session.add(post2)
    session.add(post3)
    session.add(profile)
    session.add(address)
    session.commit()
```

> `save-update` exists so you **never write this**.

---
---

# PART 2 — `merge`

> When you `session.merge(parent)` → detached children are **re-attached** to the new session too.

---

## What is a "detached" object?

```python
# Session 1 — load object
with Session(engine) as session:
    user = session.query(User).get(1)
    # user is "persistent" — session is tracking it

# Session 1 CLOSED
# user is now "detached" — exists in memory but NO session owns it

user.name = "Updated Alice"         # changed in memory

# Now you want to save this in Session 2 — this is what merge solves
```

---

## ❌ Without `merge` cascade — children break

```python
# Imagine cascade="save-update"  (no merge)

# Session 1
with Session(engine) as session:
    user = session.query(User)\
        .options(selectinload(User.posts))\
        .get(1)
    # user.posts = [Post("Old Title")]

# Session 1 closed — user and posts are DETACHED

user.name = "Updated Alice"
user.posts[0].title = "New Title"   # changed post in memory too

# Session 2
with Session(engine) as session:
    merged_user = session.merge(user)
    session.commit()

# Result in DB:
# users → "Updated Alice"  ✅
# posts → "Old Title"      ❌  post was NOT merged — change lost
```

---

## ✅ With `merge` cascade — everything re-attaches

```python
# cascade="save-update, merge"  ← merge included

# Session 1
with Session(engine) as session:
    user = session.query(User)\
        .options(selectinload(User.posts))\
        .get(1)

# Session 1 closed — user and posts are DETACHED

user.name = "Updated Alice"
user.posts[0].title = "New Title"

# Session 2
with Session(engine) as session:
    merged_user = session.merge(user)   # user + posts re-attached automatically
    session.commit()

# Result in DB:
# users → "Updated Alice"  ✅
# posts → "New Title"      ✅  post was merged too
```

---

## Real World — Where Detached Objects Come From

```python
# 1. Web request ends — session closes — object passed to next layer
with Session(engine) as session:
    user = session.query(User).get(1)
# session closed — user detached — passed to response/template

# 2. Background job receives object from another context
def background_job(user):           # user came from a different session
    with Session(engine) as session:
        merged = session.merge(user)
        merged.name = "Updated"
        session.commit()

# 3. Caching — object stored in Redis, re-used later
user = cache.get("user:1")          # detached object from cache
with Session(engine) as session:
    merged = session.merge(user)    # re-attach to fresh session
    session.commit()
```

---

# Side by Side — Crystal Clear

```python
# ── save-update ──────────────────────────────────────────
user = User(name="Alice")
post = Post(title="Hello")
user.posts.append(post)

session.add(user)           # post automatically tracked ← save-update
session.commit()            # both saved ✅


# ── merge ────────────────────────────────────────────────
with Session(engine) as s1:
    user = s1.query(User)\
        .options(selectinload(User.posts))\
        .get(1)
# s1 closed — user + posts detached

user.name = "New Name"
user.posts[0].title = "New Title"

with Session(engine) as s2:
    s2.merge(user)          # user + posts re-attached ← merge cascade
    s2.commit()             # both updated ✅
```

---

# One Line Each

| Cascade | What It Does |
|---|---|
| `save-update` | `session.add(parent)` drags all children into the session automatically |
| `merge` | `session.merge(parent)` re-attaches all detached children into the new session |

> **`save-update`** is about **first-time tracking.**  
> **`merge`** is about **re-attaching detached objects across sessions.**


Here’s a **clean, Jupyter Markdown–ready explanation** of the difference between `session.begin()` and `session.begin_nested()` 👇

````markdown
# SQLAlchemy: session.begin() vs session.begin_nested()

Both are used for **transaction management**, but they behave very differently.

---

## 🔹 1. session.begin()

👉 Starts a **regular (outer) transaction**

### Example
```python
from sqlalchemy.orm import Session

with Session() as session:
    with session.begin():
        user = User(name="Alice")
        session.add(user)
```

### Behavior
- Begins a **new transaction**
- Commits automatically if no error
- Rolls back if exception occurs

### SQL (conceptually)
```
BEGIN;
INSERT INTO user ...
COMMIT;
```

---

## 🔹 2. session.begin_nested()

👉 Starts a **nested transaction (SAVEPOINT)**

### Example
```python
from sqlalchemy.orm import Session

with Session() as session:
    with session.begin():
        session.add(User(name="Outer"))

        try:
            with session.begin_nested():
                session.add(User(name="Inner"))
                raise Exception("Error inside nested")
        except:
            print("Nested rolled back")

        session.add(User(name="After Nested"))
```

---

### Behavior
- Creates a **SAVEPOINT inside the main transaction**
- If error occurs:
  - Only **nested block is rolled back**
  - Outer transaction continues

### SQL (conceptually)
```
BEGIN;
INSERT INTO user (Outer)

SAVEPOINT sp1;
INSERT INTO user (Inner)
ROLLBACK TO SAVEPOINT sp1;

INSERT INTO user (After Nested)
COMMIT;
```

---

## 🔥 Key Differences

| Feature              | session.begin()         | session.begin_nested()        |
|----------------------|------------------------|--------------------------------|
| Type                 | Main transaction       | Nested transaction (SAVEPOINT) |
| Requires outer txn?  | No                     | Yes (usually)                  |
| Rollback scope       | Entire transaction     | Only nested block              |
| SQL concept          | BEGIN / COMMIT         | SAVEPOINT / ROLLBACK TO        |

---

## 🧠 When to Use What?

### 👉 Use `session.begin()`
- Normal transaction handling
- Most common use case

---

### 👉 Use `session.begin_nested()`
- Partial rollback needed
- Error-prone operations inside a larger transaction
- Testing / retry logic

---

## ⚡ Simple Mental Model

- `session.begin()` → **Start a transaction**
- `session.begin_nested()` → **Checkpoint inside transaction**

---

## 🚀 Real Use Case

```python
with Session() as session:
    with session.begin():
        for data in bulk_data:
            try:
                with session.begin_nested():
                    session.add(User(**data))
            except:
                print("Skipping bad record")
```

👉 Inserts valid rows, skips bad ones without failing whole transaction
````

---

If you want next level 🔥
I can explain:

* how SAVEPOINT works internally in PostgreSQL/MySQL
* why nested transactions are critical in bulk inserts
* common mistakes (very important for interviews)
