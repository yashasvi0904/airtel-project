"""SQLAlchemy models. JSON columns keep the schema portable between SQLite and PostgreSQL."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")  # customer | admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Product(Base):
    """Catalogue row seeded from product_catalogue.csv. Prices are never hardcoded in code."""
    __tablename__ = "products"
    product_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    category: Mapped[str] = mapped_column(String(60))
    product_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(30))
    price_min: Mapped[float] = mapped_column(Float)
    price_max: Mapped[float] = mapped_column(Float)
    setup_fee: Mapped[float] = mapped_column(Float)
    min_contract_months: Mapped[int] = mapped_column(Integer)
    city_tiers: Mapped[list] = mapped_column(JSON)
    min_employees: Mapped[int] = mapped_column(Integer)
    min_sites: Mapped[int] = mapped_column(Integer)
    requires_gstin: Mapped[bool] = mapped_column(Boolean)
    requires_one_of: Mapped[list] = mapped_column(JSON)
    install_days: Mapped[int] = mapped_column(Integer)
    target_segments: Mapped[list] = mapped_column(JSON)


class Journey(Base):
    """A prospect session: business profile, advisor chat, selected products.
    Guest-accessible through an unguessable id; bound to a user at checkout."""
    __tablename__ = "journeys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    needs: Mapped[dict] = mapped_column(JSON, default=dict)  # slots extracted by the advisor
    selection: Mapped[dict] = mapped_column(JSON, default=dict)  # {"items": [{"product_id","quantity"}], "term_months": int}
    stage: Mapped[str] = mapped_column(String(30), default="onboarding")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    messages = relationship("AdvisorMessage", cascade="all, delete-orphan", order_by="AdvisorMessage.id")


class AdvisorMessage(Base):
    __tablename__ = "advisor_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    journey_id: Mapped[str] = mapped_column(ForeignKey("journeys.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    journey_id: Mapped[str] = mapped_column(ForeignKey("journeys.id"), index=True)
    term_months: Mapped[int] = mapped_column(Integer)
    items: Mapped[list] = mapped_column(JSON)
    totals: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # UD-YYYYMMDD-XXXXXX
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    journey_id: Mapped[str] = mapped_column(ForeignKey("journeys.id"))
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    status: Mapped[str] = mapped_column(String(30), default="placed")
    kyc_status: Mapped[str] = mapped_column(String(20), default="not_started")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    business_name: Mapped[str] = mapped_column(String(200))
    segment: Mapped[str] = mapped_column(String(60), default="")
    term_months: Mapped[int] = mapped_column(Integer)
    monthly_total: Mapped[float] = mapped_column(Float)
    setup_total: Mapped[float] = mapped_column(Float)
    install_days: Mapped[int] = mapped_column(Integer, default=0)
    install_slot_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    install_slot_window: Mapped[str | None] = mapped_column(String(20), nullable=True)
    expected_activation: Mapped[str | None] = mapped_column(String(10), nullable=True)
    activated_on: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    events = relationship("OrderEvent", cascade="all, delete-orphan", order_by="OrderEvent.id")


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(20), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KycCase(Base):
    __tablename__ = "kyc_cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    consent: Mapped[dict] = mapped_column(JSON, default=dict)  # {given_at, purposes, notice_version}
    declared: Mapped[dict] = mapped_column(JSON, default=dict)  # identifiers entered by the applicant
    status: Mapped[str] = mapped_column(String(20), default="not_started")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    documents = relationship("KycDocument", cascade="all, delete-orphan")


class KycDocument(Base):
    __tablename__ = "kyc_documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("kyc_cases.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String(30))  # gst_certificate | udyam_certificate | signatory_id | address_proof
    file_path: Mapped[str | None] = mapped_column(String(400), nullable=True)  # encrypted at rest; null once purged
    sha256: Mapped[str] = mapped_column(String(64))
    original_name: Mapped[str] = mapped_column(String(200), default="")
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
