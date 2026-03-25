# SQLAlchemy Cascade Options — No Fluff Guide

## What Even Is a Cascade?

When you do something to a **parent** object (User, Order, Post), SQLAlchemy needs to know:
> *"What should happen to its children (addresses, items, comments)?"*

That answer is your **cascade** setting.

---

## The Options, Brutally Explained

### `save-update` *(default, always on)*
```python
# When you add parent to session → children are automatically added too
session.add(user)  # user.posts also get added. You didn't ask. It just happens.
```
You don't write this. It's always there. Don't fight it.

---

### `delete`
```python
relationship("Post", cascade="delete")
```
**Deleting the parent → deletes all children.**

```python
session.delete(user)   # Deletes user AND all user.posts
session.commit()
```

> ❌ **Trap:** If you *detach* a child from the parent (without deleting the parent), the child **survives**. `delete` alone doesn't handle orphans.

---

### `delete-orphan`
```python
relationship("Post", cascade="delete-orphan")
```
**Removing a child from the parent's collection → child gets deleted.**

```python
user.posts.remove(post)   # post is now an orphan → SQLAlchemy deletes it
session.commit()
```

> ❌ **Trap:** `delete-orphan` **cannot be used alone** — it requires `delete` to be present too. SQLAlchemy will throw a `SAWarning` or error.

---

### `expunge`
```python
relationship("Post", cascade="expunge")
```
**Removing parent from session → children are also removed from session.**

```python
session.expunge(user)   # user.posts are also detached from session
```

Rarely used in isolation. You'll almost never write this alone.

---

### `all`
```python
relationship("Post", cascade="all")
```
Shorthand for:
```
save-update + merge + refresh-expire + expunge + delete
```

> ❌ **Does NOT include `delete-orphan`.** This is the #1 mistake beginners make — they write `"all"` and expect orphans to be cleaned up. They aren't.

---

### `all, delete-orphan` ✅ — Use This in Production
```python
relationship("Post", cascade="all, delete-orphan")
```

This is the **complete package**:

| Action | Result |
|---|---|
| `session.add(user)` | Posts added to session |
| `session.delete(user)` | Posts deleted |
| `user.posts.remove(post)` | Orphaned post deleted |
| `session.expunge(user)` | Posts removed from session |

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    posts = relationship("Post", cascade="all, delete-orphan", back_populates="user")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="posts")
```

---

## Decision Table — Stop Guessing

| Scenario | Use This |
|---|---|
| Simple parent-child, children always die with parent | `"all, delete-orphan"` |
| Children can exist independently | `"save-update, merge"` (default) |
| You manually manage session lifecycle | `"all"` |
| You never delete parents, just orphan children | `"save-update, delete-orphan"` |

---

## The Relationship Between `cascade` and `passive_deletes`

```python
# If you want the DB (not Python) to handle deletes via ON DELETE CASCADE:
posts = relationship("Post", passive_deletes=True)

# And in your migration:
# ForeignKey("users.id", ondelete="CASCADE")
```

`passive_deletes=True` tells SQLAlchemy:
> *"Back off. Let the database handle child deletion. Don't load children into memory just to delete them."*

**Use this for performance** when tables are large. Don't load 10,000 posts into Python just to delete them.

---

## Common Mistakes (That Will Bite You)

### 1. Using `"all"` and expecting orphan cleanup
```python
# WRONG — orphans survive
posts = relationship("Post", cascade="all")
user.posts.remove(post)   # post still in DB ❌

# RIGHT
posts = relationship("Post", cascade="all, delete-orphan")
user.posts.remove(post)   # post deleted ✅
```

### 2. Forgetting `nullable=False` on the FK
```python
# If user_id can be NULL, SQLAlchemy won't enforce orphan deletion properly
user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # ← required
```

### 3. Using `delete-orphan` without `delete`
```python
# This will raise an error or warning:
posts = relationship("Post", cascade="delete-orphan")  # ❌ Invalid alone
```

---

## TL;DR

> Write `cascade="all, delete-orphan"` for any **owned** child relationship.  
> Use `passive_deletes=True` when performance matters and your DB supports `ON DELETE CASCADE`.  
> Everything else is edge cases you'll know when you need them.
