from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from datetime import datetime

from src.config import settings
from src.models import get_db, Receipt, Payment, PaymentMatch, AccountingEntry
from src.services import gmail_service, openai_service, folio_service, fiken_service
from src.api.schemas import (
    ReceiptResponse, 
    PaymentResponse, 
    MatchResponse,
    AccountingEntryResponse,
    StatusResponse
)
from src.api import expense_matching

app = FastAPI(title="AccountantAI", version="1.0.0")

# Include expense matching router
app.include_router(expense_matching.router)


@app.get("/")
async def root():
    return {"message": "AccountantAI API", "status": "running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# OAuth endpoints
@app.get("/auth/gmail")
async def gmail_auth():
    """Initiate Gmail OAuth flow"""
    auth_url = gmail_service.get_auth_url()
    return RedirectResponse(url=auth_url)


@app.get("/auth/gmail/callback")
async def gmail_callback(code: str):
    """Handle Gmail OAuth callback"""
    success = gmail_service.handle_oauth_callback(code)
    if success:
        return {"message": "Gmail authenticated successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to authenticate Gmail")


@app.get("/auth/fiken")
async def fiken_auth():
    """Initiate Fiken OAuth flow"""
    auth_url = fiken_service.get_auth_url()
    return RedirectResponse(url=auth_url)


@app.get("/auth/fiken/callback")
async def fiken_callback(code: str):
    """Handle Fiken OAuth callback"""
    success = fiken_service.handle_oauth_callback(code)
    if success:
        return {"message": "Fiken authenticated successfully"}
    else:
        raise HTTPException(status_code=400, detail="Failed to authenticate Fiken")


# Receipt endpoints
@app.post("/receipts/upload")
async def upload_receipt(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Manually upload a receipt"""
    # Validate file type
    file_ext = os.path.splitext(file.filename)[1].lower()[1:]
    if file_ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type {file_ext} not allowed")
    
    # Save file
    os.makedirs(settings.upload_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(settings.upload_folder, safe_filename)
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Create receipt record
    receipt = Receipt(
        source='manual',
        file_path=file_path,
        original_filename=file.filename,
        status='pending'
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    
    # Process in background
    background_tasks.add_task(openai_service.process_receipt, receipt.id)
    
    return {"id": receipt.id, "message": "Receipt uploaded and queued for processing"}


@app.get("/receipts", response_model=List[ReceiptResponse])
async def get_receipts(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get list of receipts"""
    query = db.query(Receipt)
    if status:
        query = query.filter(Receipt.status == status)
    
    receipts = query.order_by(Receipt.created_at.desc()).limit(limit).all()
    return receipts


@app.get("/receipts/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(receipt_id: int, db: Session = Depends(get_db)):
    """Get specific receipt details"""
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


@app.post("/receipts/sync-email")
async def sync_email_receipts(background_tasks: BackgroundTasks):
    """Sync receipts from Gmail"""
    background_tasks.add_task(gmail_service.process_receipt_emails)
    return {"message": "Email sync started"}


# Payment endpoints
@app.post("/payments/sync")
async def sync_payments(background_tasks: BackgroundTasks):
    """Sync payments from Folio"""
    background_tasks.add_task(folio_service.sync_payments)
    return {"message": "Payment sync started"}


@app.get("/payments", response_model=List[PaymentResponse])
async def get_payments(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get list of payments"""
    query = db.query(Payment)
    if status:
        query = query.filter(Payment.status == status)
    
    payments = query.order_by(Payment.payment_date.desc()).limit(limit).all()
    return payments


# Matching endpoints
@app.post("/match/auto")
async def auto_match_payments(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Automatically match unmatched payments to receipts"""
    # Get unmatched payments
    unmatched_payments = db.query(Payment).filter(
        Payment.status == 'unmatched'
    ).all()
    
    # Get unmatched receipts
    unmatched_receipts = db.query(Receipt).filter(
        Receipt.status == 'processed'
    ).all()
    
    matched_count = 0
    
    for payment in unmatched_payments:
        # Use AI to find best match
        payment_dict = {
            'amount': payment.amount,
            'payment_date': payment.payment_date.isoformat(),
            'reference': payment.reference,
            'tenant_name': payment.tenant_name,
            'currency': 'NOK'
        }
        
        match_result = openai_service.match_payment_to_receipt(
            payment_dict, 
            unmatched_receipts
        )
        
        if match_result and match_result.get('matched_receipt_id'):
            # Create match record
            match = PaymentMatch(
                receipt_id=int(match_result['matched_receipt_id']),
                payment_id=payment.id,
                match_confidence=float(match_result.get('confidence', 0)),
                match_type=match_result.get('match_type', 'fuzzy'),
                matched_amount=payment.amount,
                ai_match_reasoning=match_result.get('reasoning', '')
            )
            db.add(match)
            
            # Update statuses
            payment.status = 'matched'
            receipt = db.query(Receipt).filter(
                Receipt.id == int(match_result['matched_receipt_id'])
            ).first()
            if receipt:
                receipt.status = 'matched'
            
            matched_count += 1
    
    db.commit()
    
    return {"message": f"Matched {matched_count} payments"}


@app.post("/match/manual")
async def manual_match(
    payment_id: int,
    receipt_id: int,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Manually match a payment to a receipt"""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    
    if not payment or not receipt:
        raise HTTPException(status_code=404, detail="Payment or receipt not found")
    
    # Create match
    match = PaymentMatch(
        receipt_id=receipt_id,
        payment_id=payment_id,
        match_confidence=1.0,
        match_type='manual',
        matched_amount=payment.amount,
        is_manual=True,
        manual_notes=notes
    )
    db.add(match)
    
    # Update statuses
    payment.status = 'matched'
    receipt.status = 'matched'
    
    db.commit()
    
    return {"message": "Manual match created successfully"}


# Accounting sync endpoints
@app.post("/accounting/sync/{receipt_id}")
async def sync_to_fiken(
    receipt_id: int,
    background_tasks: BackgroundTasks
):
    """Sync a specific receipt to Fiken"""
    background_tasks.add_task(fiken_service.sync_receipt_to_fiken, receipt_id)
    return {"message": "Sync to Fiken started"}


@app.post("/accounting/sync-all")
async def sync_all_to_fiken(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Sync all matched receipts to Fiken"""
    # Get all matched receipts not yet synced
    receipts_to_sync = db.query(Receipt).filter(
        Receipt.status == 'matched'
    ).all()
    
    for receipt in receipts_to_sync:
        # Check if already has accounting entry
        existing = db.query(AccountingEntry).filter(
            AccountingEntry.receipt_id == receipt.id,
            AccountingEntry.status == 'synced'
        ).first()
        
        if not existing:
            background_tasks.add_task(
                fiken_service.sync_receipt_to_fiken, 
                receipt.id
            )
    
    return {"message": f"Queued {len(receipts_to_sync)} receipts for sync"}


@app.get("/accounting/entries", response_model=List[AccountingEntryResponse])
async def get_accounting_entries(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get list of accounting entries"""
    query = db.query(AccountingEntry)
    if status:
        query = query.filter(AccountingEntry.status == status)
    
    entries = query.order_by(AccountingEntry.created_at.desc()).limit(limit).all()
    return entries


# System status
@app.get("/status", response_model=StatusResponse)
async def get_system_status(db: Session = Depends(get_db)):
    """Get overall system status"""
    status = {
        "gmail_connected": False,
        "fiken_connected": False,
        "folio_connected": False,
        "receipts": {
            "total": db.query(Receipt).count(),
            "pending": db.query(Receipt).filter(Receipt.status == 'pending').count(),
            "processed": db.query(Receipt).filter(Receipt.status == 'processed').count(),
            "matched": db.query(Receipt).filter(Receipt.status == 'matched').count(),
            "error": db.query(Receipt).filter(Receipt.status == 'error').count()
        },
        "payments": {
            "total": db.query(Payment).count(),
            "unmatched": db.query(Payment).filter(Payment.status == 'unmatched').count(),
            "matched": db.query(Payment).filter(Payment.status == 'matched').count()
        },
        "accounting_entries": {
            "total": db.query(AccountingEntry).count(),
            "synced": db.query(AccountingEntry).filter(AccountingEntry.status == 'synced').count(),
            "error": db.query(AccountingEntry).filter(AccountingEntry.status == 'error').count()
        }
    }
    
    # Check service connections
    try:
        # This would need proper implementation
        # Test Gmail connection by checking for stored token
        from src.models import OAuthToken
        gmail_token = db.query(OAuthToken).filter_by(service='gmail').first()
        status["gmail_connected"] = gmail_token is not None
        
        status["fiken_connected"] = fiken_service.test_connection()
        status["folio_connected"] = folio_service.test_connection()
    except:
        pass
    
    return status


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)