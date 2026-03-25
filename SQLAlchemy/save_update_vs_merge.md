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
