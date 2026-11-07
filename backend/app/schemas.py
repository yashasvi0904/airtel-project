"""Request validation models."""
import re

from pydantic import BaseModel, Field, field_validator

from .services.profile import INTERNET_OPTIONS


class RegisterIn(BaseModel):
    email: str = Field(max_length=255)
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if v in (None, ""):
            return None
        v = re.sub(r"[\s\-+]", "", v)
        v = v[-10:] if len(v) > 10 else v
        if not re.fullmatch(r"[6-9]\d{9}", v):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return v


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20, max_length=4096)


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    business_name: str = Field(min_length=1, max_length=160)
    business_type: str = Field(min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=80)
    employees: int = Field(ge=1, le=5000)
    sites: int = Field(default=1, ge=1, le=500)
    current_internet: str = "Mobile hotspot"
    monthly_budget: float | None = Field(default=None, ge=0, le=10_000_000)
    monthly_telecom_spend: float | None = Field(default=None, ge=0, le=10_000_000)
    has_gstin: bool = False
    gstin: str | None = None
    has_udyam: bool = False
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = None
    language: str = "en"

    @field_validator("current_internet")
    @classmethod
    def _net(cls, v):
        if v not in INTERNET_OPTIONS:
            raise ValueError(f"current_internet must be one of {INTERNET_OPTIONS}")
        return v

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v):
        if not v:
            return None
        v = v.strip().upper()
        if len(v) != 15 or not v.isalnum():
            raise ValueError("GSTIN must be 15 letters/digits")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return RegisterIn._phone(v)

    @field_validator("language")
    @classmethod
    def _lang(cls, v):
        return v if re.fullmatch(r"[a-z]{2}", v or "") else "en"


class LanguageIn(BaseModel):
    language: str = Field(pattern=r"^[a-z]{2}$")


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class ItemIn(BaseModel):
    product_id: str = Field(pattern=r"^P\d{2}$")
    quantity: int = Field(ge=1, le=1000)


class SelectionIn(BaseModel):
    items: list[ItemIn] = Field(max_length=40)
    term_months: int = Field(ge=1, le=60)


class QuotePreviewIn(SelectionIn):
    journey_id: str


class OrderIn(BaseModel):
    quote_id: str
    accept_terms: bool


class ScheduleIn(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    window: str = Field(pattern="^(morning|afternoon)$")


class ConsentIn(BaseModel):
    accepted: bool
    has_gstin: bool = True
    has_udyam: bool = True
    gstin: str | None = Field(default=None, max_length=15)
    udyam_number: str | None = Field(default=None, max_length=25)
    signatory_name: str | None = Field(default=None, max_length=120)


class AdvanceIn(BaseModel):
    to: str
    note: str = Field(default="", max_length=300)


class DecisionIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=300)
