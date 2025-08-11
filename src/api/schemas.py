from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime


class ReceiptResponse(BaseModel):
    id: int
    source: str
    email_id: Optional[str]
    file_path: str
    original_filename: str
    vendor_name: Optional[str]
    invoice_number: Optional[str]
    invoice_date: Optional[datetime]
    due_date: Optional[datetime]
    total_amount: Optional[float]
    vat_amount: Optional[float]
    currency: str
    ai_extracted_data: Optional[Dict]
    ai_confidence: Optional[float]
    category: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: datetime
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class PaymentResponse(BaseModel):
    id: int
    folio_payment_id: str
    tenant_name: str
    property_name: str
    amount: float
    payment_date: datetime
    payment_method: str
    reference: Optional[str]
    status: str
    created_at: datetime
    synced_at: datetime
    
    class Config:
        from_attributes = True


class MatchResponse(BaseModel):
    id: int
    receipt_id: int
    payment_id: int
    match_confidence: float
    match_type: str
    matched_amount: float
    ai_match_reasoning: Optional[str]
    is_manual: bool
    manual_notes: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class AccountingEntryResponse(BaseModel):
    id: int
    receipt_id: int
    fiken_entry_id: Optional[str]
    entry_date: datetime
    description: str
    debit_account: str
    credit_account: str
    amount: float
    vat_code: Optional[str]
    status: str
    sync_error: Optional[str]
    created_at: datetime
    synced_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class StatusResponse(BaseModel):
    gmail_connected: bool
    fiken_connected: bool
    folio_connected: bool
    receipts: Dict[str, int]
    payments: Dict[str, int]
    accounting_entries: Dict[str, int]