# SQLAlchemy + MySQL — Complete Guide

## Imports

```python
from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, SmallInteger,
    String, Text, Boolean, Float, Numeric, DECIMAL,
    Date, DateTime, Time, TIMESTAMP, JSON, Enum,
    ForeignKey, ForeignKeyConstraint, PrimaryKeyConstraint,
    UniqueConstraint, CheckConstraint, Index, Table, text, func
)
from sqlalchemy.dialects.mysql import (
    TINYINT, MEDIUMINT, LONGTEXT, MEDIUMTEXT, CHAR, VARCHAR, DOUBLE, SET
)
from sqlalchemy.orm import declarative_base, relationship, Session
from datetime import datetime

Base = declarative_base()
engine = create_engine("mysql+pymysql://user:password@localhost/dbname", echo=True)
```

---

## Hierarchy to Remember

```
Engine          → connects to DB
  ↓
Base.metadata   → knows all your tables
  ↓
Session         → unit of work (add, query, commit, rollback)
  ↓
Model           → Python class = DB table
  ↓
Column          → Python attribute = DB column
```

---

## 1. Column Types

```python
class FullExample(Base):
    __tablename__ = "full_example"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    big_num     = Column(BigInteger)
    small_num   = Column(SmallInteger)
    is_active   = Column(Boolean, default=True)
    price       = Column(DECIMAL(10, 2))          # exact decimal — use for money
    name        = Column(String(100))
    bio         = Column(Text)
    long_text   = Column(LONGTEXT)                # MySQL specific
    data        = Column(JSON)                    # MySQL 5.7.8+
    status      = Column(Enum('active', 'inactive', 'banned'))
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(TIMESTAMP, onupdate=datetime.utcnow)
```

---

## 2. Nullable & NOT NULL

```python
id    = Column(Integer, primary_key=True)
name  = Column(String(100), nullable=False)   # NOT NULL
bio   = Column(Text, nullable=True)           # NULL allowed (default is True)
email = Column(String(100), nullable=False, unique=True)
```

---

## 3. Default Values & Server Defaults

```python
is_draft   = Column(Boolean, default=True)                     # Python sets this
views      = Column(Integer, default=0)
created_at = Column(DateTime, default=datetime.utcnow)         # Python sets this
updated_at = Column(DateTime, server_default=text("NOW()"),    # MySQL sets this
                    onupdate=datetime.utcnow)
```

| | `default` | `server_default` |
|---|---|---|
| Who sets it | Python / SQLAlchemy | MySQL server |
| When | Before INSERT | During INSERT in DB |
| Use for | Most cases | DB-level triggers / functions |

---

## 4. Unique Constraint

```python
# Single column
email = Column(String(100), unique=True)

# Composite — the PAIR must be unique
__table_args__ = (
    UniqueConstraint('name', 'phone', name='uq_name_phone'),
)
```

> Violated? SQLAlchemy throws `IntegrityError`.

---

## 5. Primary Key

```python
# Simple
id = Column(Integer, primary_key=True, autoincrement=True)

# Composite
__table_args__ = (
    PrimaryKeyConstraint('order_id', 'product_id', name='pk_order_item'),
)
```

---

## 6. Foreign Key

```python
# Inline (single column)
user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

# Table-level (use when FK spans multiple columns)
__table_args__ = (
    ForeignKeyConstraint(
        ['order_id', 'product_id'],
        ['orders.id', 'products.id'],
        ondelete='CASCADE',
        name='fk_order_product'
    ),
)
```

| `ondelete` Option | Behavior |
|---|---|
| `CASCADE` | Delete child when parent deleted |
| `SET NULL` | Set FK to NULL when parent deleted |
| `RESTRICT` | Block parent delete if child exists |
| `SET DEFAULT` | Set FK to default value |

---

## 7. Check Constraint

```python
__table_args__ = (
    CheckConstraint('price > 0',   name='chk_price_positive'),
    CheckConstraint('stock >= 0',  name='chk_stock_non_negative'),
    CheckConstraint('quantity > 0', name='chk_quantity'),
)
```

> **MySQL WARNING:** CHECK constraints are ignored before MySQL **8.0.16**. Use 8.0.16+ for real enforcement.

---

## 8. Index

```python
# Inline — simple
name = Column(String(100), index=True)

# In __table_args__
__table_args__ = (
    Index('idx_category_price', 'category', 'price'),            # composite
    Index('idx_name_unique',    'name', unique=True),            # unique index
    Index('idx_name',           'name', mysql_using='BTREE'),    # BTREE (default, range queries)
    Index('idx_code',           'code', mysql_using='HASH'),     # HASH (exact match only)
    Index('idx_bio',            'bio',  mysql_prefix='FULLTEXT'),# fulltext search
    Index('idx_geo',         'location',mysql_prefix='SPATIAL'), # geo data
    Index('idx_lower_email', func.lower(email)),                 # functional index (MySQL 8+)
    Index('idx_category',    'category', mysql_length=50),       # prefix index for long VARCHAR
)
```

| Index Type | When to Use |
|---|---|
| Simple `index=True` | Single column, frequent WHERE / filter |
| Composite | Queries filter on multiple columns together |
| Unique Index | Same as UniqueConstraint but also speeds up lookups |
| FULLTEXT | Full-text search on TEXT / VARCHAR columns |
| SPATIAL | Geo / geometry data |
| Functional | Index on expression e.g. `LOWER(email)` |
| Prefix | Long VARCHAR columns in MySQL |

> **Golden Rule:** Index columns you `filter()`, `order_by()`, or `join()` on. Never blindly index everything — writes become slower.

---

## 9. Relationships

```python
# One-to-Many
class User(Base):
    posts = relationship("Post", back_populates="author")

class Post(Base):
    user_id = Column(Integer, ForeignKey("users.id"))
    author  = relationship("User", back_populates="posts")


# Many-to-Many (needs association table)
post_tags = Table(
    "post_tags", Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id",  Integer, ForeignKey("tags.id"),  primary_key=True),
)

class Tag(Base):
    posts = relationship("Post", secondary=post_tags, back_populates="tags")


# One-to-One
class Profile(Base):
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)   # unique = 1-to-1
    user    = relationship("User", back_populates="profile", uselist=False)
    #                                                          ↑ returns object, not list
```

---

## 10. Views

```python
# Create view — must use raw SQL
with engine.connect() as conn:
    conn.execute(text("""
        CREATE OR REPLACE VIEW active_users_view AS
        SELECT id, name, email
        FROM users
        WHERE is_active = 1
    """))
    conn.commit()

# Map model to view (READ ONLY — never insert/update)
class ActiveUserView(Base):
    __tablename__  = "active_users_view"
    __table_args__ = {'extend_existing': True}

    id    = Column(Integer, primary_key=True)
    name  = Column(String(100))
    email = Column(String(100))

# Query view like a table
with Session(engine) as session:
    users = session.query(ActiveUserView).all()
```

---

## 11. `__table_args__` — Complete Reference

```python
__table_args__ = (
    # Constraints
    PrimaryKeyConstraint('col1', 'col2',           name='pk_name'),
    UniqueConstraint('col1', 'col2',               name='uq_name'),
    ForeignKeyConstraint(['col'], ['other.col'],
                         ondelete='CASCADE',       name='fk_name'),
    CheckConstraint('col > 0',                     name='chk_name'),

    # Indexes
    Index('idx_name',  'col',                      mysql_using='BTREE'),
    Index('idx_name',  'col',                      mysql_using='HASH'),
    Index('idx_name',  'col',                      mysql_prefix='FULLTEXT'),
    Index('idx_name',  'col',                      mysql_prefix='SPATIAL'),
    Index('idx_name',  func.lower(col)),           # functional index MySQL 8+

    # Dict MUST be LAST
    {
        'mysql_engine':         'InnoDB',          # supports FK & transactions
        'mysql_charset':        'utf8mb4',         # full unicode
        'mysql_collate':        'utf8mb4_unicode_ci', # case-insensitive
        'mysql_auto_increment': 1000,              # IDs start from 1000
        'mysql_row_format':     'DYNAMIC',         # DYNAMIC/COMPRESSED/FIXED/REDUNDANT
        'comment':              'table description',
        'schema':               'other_database',  # SELECT * FROM other_database.table
        'extend_existing':       True,             # won't error if already in metadata
    }
)
```

> **RULE: The dict must ALWAYS be the last item in the `__table_args__` tuple.**

---

## 12. Sessions — The Thing Everyone Gets Wrong

```python
# WRONG — connection leak, session never closed
session = Session(engine)
session.add(user)
session.commit()

# RIGHT — always use context manager
with Session(engine) as session:
    session.add(user)
    session.commit()

# RIGHT — with auto transaction control
with Session(engine) as session:
    with session.begin():     # auto commits or rolls back
        session.add(user)
```

---

## 13. Querying

```python
with Session(engine) as session:

    # All rows
    users = session.query(User).all()

    # Filter
    user = session.query(User).filter(User.email == "alice@example.com").first()

    # Multiple filters
    posts = session.query(Post).filter(
        Post.user_id == 1,
        Post.title.like("%python%")
    ).all()

    # Order + Limit
    recent = session.query(Post).order_by(Post.created_at.desc()).limit(10).all()

    # Join
    results = session.query(User, Post).join(Post, User.id == Post.user_id).all()

    # Count
    count = session.query(User).filter(User.is_active == True).count()

    # Exists
    from sqlalchemy import exists
    has_posts = session.query(exists().where(Post.user_id == 1)).scalar()

    # Fulltext search (raw SQL)
    results = session.execute(
        text("SELECT * FROM posts WHERE MATCH(title, body) AGAINST(:q IN BOOLEAN MODE)"),
        {"q": "python"}
    ).fetchall()
```

---

## 14. Full Working Example

```python
# Many-to-Many table
post_tags = Table(
    "post_tags", Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id",  Integer, ForeignKey("tags.id"),  primary_key=True),
)

class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(100), nullable=False)
    email      = Column(String(100), nullable=False, unique=True)
    phone      = Column(String(20),  nullable=True)
    bio        = Column(Text,        nullable=True)
    is_active  = Column(Boolean,     default=True)
    created_at = Column(DateTime,    default=datetime.utcnow)
    updated_at = Column(TIMESTAMP,   server_default=text("NOW()"), onupdate=datetime.utcnow)

    posts   = relationship("Post",    back_populates="author")
    profile = relationship("Profile", back_populates="user", uselist=False)

    __table_args__ = (
        UniqueConstraint('name', 'phone',              name='uq_name_phone'),
        Index('idx_name',        'name',               mysql_using='BTREE'),
        Index('idx_bio',         'bio',                mysql_prefix='FULLTEXT'),
        Index('idx_email_lower', func.lower(email)),
        CheckConstraint("char_length(name) > 0",       name='chk_name_not_empty'),
        {
            'mysql_engine':         'InnoDB',
            'mysql_charset':        'utf8mb4',
            'mysql_collate':        'utf8mb4_unicode_ci',
            'mysql_auto_increment': 1000,
            'mysql_row_format':     'DYNAMIC',
            'comment':              'Stores all users',
        }
    )


class Post(Base):
    __tablename__ = "posts"

    id         = Column(Integer,       primary_key=True)
    title      = Column(String(200),   nullable=False)
    body       = Column(LONGTEXT,      nullable=False)
    status     = Column(Enum('draft', 'published', 'archived'), default='draft')
    views      = Column(Integer,       default=0)
    price      = Column(DECIMAL(10,2), nullable=True)
    data       = Column(JSON,          nullable=True)
    user_id    = Column(Integer,       nullable=False)
    created_at = Column(DateTime,      default=datetime.utcnow)

    author = relationship("User", back_populates="posts")
    tags   = relationship("Tag",  secondary=post_tags, back_populates="posts")

    __table_args__ = (
        PrimaryKeyConstraint('id',                          name='pk_post_id'),
        ForeignKeyConstraint(['user_id'], ['users.id'],
                             ondelete='CASCADE',            name='fk_post_user'),
        UniqueConstraint('title', 'user_id',               name='uq_title_user'),
        Index('idx_status',       'status',                mysql_using='BTREE'),
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_title_body',   'title', 'body',         mysql_prefix='FULLTEXT'),
        CheckConstraint('views >= 0',                      name='chk_views_positive'),
        CheckConstraint('price > 0',                       name='chk_price_positive'),
        {
            'mysql_engine':     'InnoDB',
            'mysql_charset':    'utf8mb4',
            'mysql_collate':    'utf8mb4_unicode_ci',
            'mysql_row_format': 'DYNAMIC',
            'comment':          'Blog posts table',
        }
    )

Base.metadata.create_all(engine)
```
