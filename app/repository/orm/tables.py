"""Tabelas (Core): o schema. Os agregados de `app/domain` são ligados a elas em `mapping.py`."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
)

from app.domain.status import OrderStatus

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

products = Table(
    "products",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(200), nullable=False),
    Column("price_cents", Integer, nullable=False),
    Column("stock", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("price_cents > 0"),
    CheckConstraint("stock >= 0"),
)

orders = Table(
    "orders",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("user_id", ForeignKey("users.id"), nullable=False, index=True),
    Column("status", Enum(OrderStatus, native_enum=False, length=20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

order_items = Table(
    "order_items",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("order_id", ForeignKey("orders.id"), nullable=False, index=True),
    Column("product_id", ForeignKey("products.id"), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("unit_price_cents", Integer, nullable=False),
    CheckConstraint("quantity > 0"),
)

order_status_history = Table(
    "order_status_history",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("order_id", ForeignKey("orders.id"), nullable=False, index=True),
    Column("status", Enum(OrderStatus, native_enum=False, length=20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("notified_at", DateTime(timezone=True)),
)
