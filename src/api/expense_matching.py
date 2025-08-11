from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from src.models import get_db, Receipt, Payment, PaymentMatch
from src.services import folio_service, openai_service
from src.api.schemas import MatchResponse
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.post("/sync")
async def sync_expenses(background_tasks: BackgroundTasks):
    """Sync expense transactions from Folio.no"""
    background_tasks.add_task(sync_folio_expenses)
    return {"message": "Expense sync started"}


@router.post("/match-receipts")
async def match_expenses_to_receipts(
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """Match Folio expenses to uploaded receipts"""
    # Get recent expenses from Folio
    expenses = folio_service.get_expenses(days_back=days_back)
    
    # Get unmatched receipts
    unmatched_receipts = db.query(Receipt).filter(
        Receipt.status == 'processed'
    ).all()
    
    matches = []
    
    for expense in expenses:
        best_match = None
        best_confidence = 0.0
        
        # Try to match with each receipt
        for receipt in unmatched_receipts:
            confidence = folio_service.match_expense_to_receipt(expense, receipt)
            
            if confidence > best_confidence and confidence > 0.5:  # Minimum 50% confidence
                best_match = receipt
                best_confidence = confidence
        
        if best_match:
            # Use AI for additional verification
            ai_match = openai_service.match_payment_to_receipt(
                {
                    'amount': expense['amount'],
                    'payment_date': expense['date'],
                    'reference': expense['description'],
                    'tenant_name': expense['merchant'],
                    'currency': 'NOK'
                },
                [best_match]
            )
            
            if ai_match and ai_match.get('confidence', 0) > 0.6:
                # Create match record
                match = PaymentMatch(
                    receipt_id=best_match.id,
                    payment_id=None,  # We'll need to adjust the model for expense matching
                    match_confidence=best_confidence,
                    match_type='expense_match',
                    matched_amount=expense['amount'],
                    ai_match_reasoning=f"Matched Folio expense to receipt. Merchant: {expense['merchant']}, "
                                      f"Date diff: {abs((datetime.fromisoformat(expense['date']) - best_match.invoice_date).days)} days"
                )
                
                matches.append({
                    "expense": expense,
                    "receipt": {
                        "id": best_match.id,
                        "vendor": best_match.vendor_name,
                        "amount": best_match.total_amount,
                        "date": best_match.invoice_date.isoformat() if best_match.invoice_date else None
                    },
                    "confidence": best_confidence
                })
                
                # Update receipt status
                best_match.status = 'matched'
                db.add(match)
    
    db.commit()
    
    return {
        "message": f"Found {len(matches)} matches",
        "matches": matches
    }


async def sync_folio_expenses():
    """Background task to sync expenses from Folio"""
    try:
        # This would sync expenses similar to payments
        # For now, we'll just log
        expenses = folio_service.get_expenses(days_back=7)
        logger.info(f"Found {len(expenses)} expenses in Folio")
        
        # You could store these in a separate Expense table
        # or process them immediately for matching
        
    except Exception as e:
        logger.error(f"Failed to sync expenses: {e}")


@router.get("/unmatched")
async def get_unmatched_expenses(days_back: int = 30):
    """Get Folio expenses that haven't been matched to receipts"""
    expenses = folio_service.get_expenses(days_back=days_back)
    
    # Filter out expenses that might already be matched
    # This is simplified - you'd want to check against your database
    unmatched = [e for e in expenses if e['amount'] > 0]
    
    return {
        "count": len(unmatched),
        "total_amount": sum(e['amount'] for e in unmatched),
        "expenses": unmatched
    }


@router.post("/auto-categorize")
async def auto_categorize_expenses(days_back: int = 30):
    """Use AI to categorize Folio expenses"""
    expenses = folio_service.get_expenses(days_back=days_back)
    
    categorized = []
    for expense in expenses:
        category = openai_service.categorize_expense({
            'vendor_name': expense['merchant'],
            'total_amount': expense['amount'],
            'currency': 'NOK',
            'items': [{'description': expense['description']}]
        })
        
        expense['suggested_category'] = category
        categorized.append(expense)
    
    return {
        "message": f"Categorized {len(categorized)} expenses",
        "expenses": categorized
    }