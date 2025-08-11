from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from src.config import settings

Base = declarative_base()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Receipt(Base):
    __tablename__ = "receipts"
    
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50))  # 'email', 'manual'
    email_id = Column(String(255), unique=True, nullable=True)
    file_path = Column(String(500))
    original_filename = Column(String(255))
    
    # Extracted data
    vendor_name = Column(String(255))
    invoice_number = Column(String(100))
    invoice_date = Column(DateTime)
    due_date = Column(DateTime, nullable=True)
    total_amount = Column(Float)
    vat_amount = Column(Float, nullable=True)
    currency = Column(String(3), default='NOK')
    
    # AI analysis
    ai_extracted_data = Column(JSON)
    ai_confidence = Column(Float)
    category = Column(String(100))
    
    # Processing status
    status = Column(String(50), default='pending')  # pending, processed, error, matched
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    
    # Relationships
    accounting_entries = relationship("AccountingEntry", back_populates="receipt")
    payment_matches = relationship("PaymentMatch", back_populates="receipt")


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    folio_payment_id = Column(String(255), unique=True)
    tenant_name = Column(String(255))
    property_name = Column(String(255))
    amount = Column(Float)
    payment_date = Column(DateTime)
    payment_method = Column(String(50))
    reference = Column(String(255), nullable=True)
    
    # Processing
    status = Column(String(50), default='unmatched')  # unmatched, matched, partial, error
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    synced_at = Column(DateTime)
    
    # Relationships
    payment_matches = relationship("PaymentMatch", back_populates="payment")


class PaymentMatch(Base):
    __tablename__ = "payment_matches"
    
    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"))
    payment_id = Column(Integer, ForeignKey("payments.id"))
    
    match_confidence = Column(Float)
    match_type = Column(String(50))  # 'exact', 'fuzzy', 'manual'
    matched_amount = Column(Float)
    
    # AI reasoning
    ai_match_reasoning = Column(Text)
    
    # Manual override
    is_manual = Column(Boolean, default=False)
    manual_notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    receipt = relationship("Receipt", back_populates="payment_matches")
    payment = relationship("Payment", back_populates="payment_matches")


class AccountingEntry(Base):
    __tablename__ = "accounting_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"))
    fiken_entry_id = Column(String(255), unique=True, nullable=True)
    
    # Entry details
    entry_date = Column(DateTime)
    description = Column(Text)
    debit_account = Column(String(100))
    credit_account = Column(String(100))
    amount = Column(Float)
    vat_code = Column(String(50), nullable=True)
    
    # Status
    status = Column(String(50), default='pending')  # pending, synced, error
    sync_error = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    synced_at = Column(DateTime, nullable=True)
    
    # Relationships
    receipt = relationship("Receipt", back_populates="accounting_entries")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    service = Column(String(50), unique=True)  # 'gmail', 'fiken'
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_type = Column(String(50))
    expires_at = Column(DateTime)
    
    # Additional data
    scope = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Create tables
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()