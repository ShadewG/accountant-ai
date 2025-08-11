from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Optional
from datetime import datetime, date, timedelta
import os

from src.models import get_db
from src.models.transactions import (
    Transaction, TransactionType, TransactionSource,
    SpendingCategory, AnalysisReport, BudgetRule, FinancialGoal
)
from src.services.transaction_import import transaction_import_service
from src.services.deep_analysis import deep_analysis_service
from src.api.schemas import TransactionResponse, AnalysisReportResponse
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/import/csv")
async def import_csv(
    file: UploadFile = File(...),
    bank_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Import transactions from CSV file"""
    # Save uploaded file
    os.makedirs("./uploads/imports", exist_ok=True)
    file_path = f"./uploads/imports/{datetime.now().timestamp()}_{file.filename}"
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Import based on bank or generic
    if bank_name:
        result = transaction_import_service.import_bank_statement(file_path, bank_name)
    else:
        result = transaction_import_service.import_csv(file_path)
    
    # Clean up file
    os.remove(file_path)
    
    return result


@router.post("/import/excel")
async def import_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import transactions from Excel file"""
    # Save uploaded file
    os.makedirs("./uploads/imports", exist_ok=True)
    file_path = f"./uploads/imports/{datetime.now().timestamp()}_{file.filename}"
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    result = transaction_import_service.import_excel(file_path)
    
    # Clean up
    os.remove(file_path)
    
    return result


@router.get("/")
async def get_transactions(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category: Optional[str] = None,
    type: Optional[TransactionType] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get transactions with filters"""
    query = db.query(Transaction)
    
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
    if category:
        query = query.filter(Transaction.category == category)
    if type:
        query = query.filter(Transaction.type == type)
    
    total = query.count()
    transactions = query.order_by(Transaction.date.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "transactions": transactions,
        "offset": offset,
        "limit": limit
    }


@router.get("/statistics")
async def get_statistics(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Get transaction statistics"""
    # Default to last 30 days
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    # Base query
    query = db.query(Transaction).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date
    )
    
    # Calculate totals
    income = query.filter(Transaction.type == TransactionType.INCOME).with_entities(
        func.sum(Transaction.amount)
    ).scalar() or 0
    
    expenses = query.filter(Transaction.type == TransactionType.EXPENSE).with_entities(
        func.sum(Transaction.amount)
    ).scalar() or 0
    
    # Category breakdown
    category_stats = query.filter(Transaction.type == TransactionType.EXPENSE).with_entities(
        Transaction.category,
        func.sum(Transaction.amount).label('total'),
        func.count(Transaction.id).label('count')
    ).group_by(Transaction.category).all()
    
    categories = [
        {
            "category": cat or "Uncategorized",
            "total": float(total),
            "count": count,
            "percentage": (float(total) / expenses * 100) if expenses > 0 else 0
        }
        for cat, total, count in category_stats
    ]
    
    # Daily average
    days = (end_date - start_date).days + 1
    daily_avg_expense = expenses / days if days > 0 else 0
    
    # Monthly projection
    monthly_projection = daily_avg_expense * 30
    
    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        },
        "totals": {
            "income": float(income),
            "expenses": float(expenses),
            "net": float(income - expenses),
            "savings_rate": ((income - expenses) / income * 100) if income > 0 else 0
        },
        "averages": {
            "daily_expense": daily_avg_expense,
            "monthly_projection": monthly_projection
        },
        "categories": sorted(categories, key=lambda x: x['total'], reverse=True),
        "transaction_count": query.count()
    }


@router.post("/analyze/deep")
async def deep_analysis(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Trigger deep AI analysis of spending patterns"""
    # Run analysis
    result = deep_analysis_service.analyze_spending_patterns(
        start_date=start_date,
        end_date=end_date
    )
    
    return result


@router.get("/analyze/reports")
async def get_analysis_reports(
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get previous analysis reports"""
    reports = db.query(AnalysisReport).order_by(
        AnalysisReport.created_at.desc()
    ).limit(limit).all()
    
    return reports


@router.get("/analyze/report/{report_id}")
async def get_analysis_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Get specific analysis report"""
    report = db.query(AnalysisReport).filter_by(id=report_id).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Generate readable report
    readable_report = deep_analysis_service.generate_insights_report(report_id)
    
    return {
        "report": report,
        "readable_report": readable_report
    }


@router.get("/trends")
async def get_spending_trends(
    months: int = 6,
    db: Session = Depends(get_db)
):
    """Get spending trends over time"""
    end_date = date.today()
    start_date = end_date - timedelta(days=months * 30)
    
    # Monthly aggregation
    monthly_data = db.query(
        extract('year', Transaction.date).label('year'),
        extract('month', Transaction.date).label('month'),
        Transaction.type,
        func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.date >= start_date
    ).group_by(
        extract('year', Transaction.date),
        extract('month', Transaction.date),
        Transaction.type
    ).all()
    
    # Format results
    trends = {}
    for year, month, trans_type, total in monthly_data:
        key = f"{int(year)}-{int(month):02d}"
        if key not in trends:
            trends[key] = {"income": 0, "expenses": 0}
        
        if trans_type == TransactionType.INCOME:
            trends[key]["income"] = float(total)
        elif trans_type == TransactionType.EXPENSE:
            trends[key]["expenses"] = float(total)
    
    # Category trends
    category_trends = db.query(
        extract('year', Transaction.date).label('year'),
        extract('month', Transaction.date).label('month'),
        Transaction.category,
        func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.date >= start_date,
        Transaction.type == TransactionType.EXPENSE
    ).group_by(
        extract('year', Transaction.date),
        extract('month', Transaction.date),
        Transaction.category
    ).all()
    
    # Format category trends
    cat_trends = {}
    for year, month, category, total in category_trends:
        key = f"{int(year)}-{int(month):02d}"
        if key not in cat_trends:
            cat_trends[key] = {}
        cat_trends[key][category or "Uncategorized"] = float(total)
    
    return {
        "monthly_totals": trends,
        "category_trends": cat_trends,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "months": months
        }
    }


@router.post("/categorize/auto")
async def auto_categorize(
    batch_size: int = 100,
    db: Session = Depends(get_db)
):
    """Auto-categorize uncategorized transactions using AI"""
    # Get uncategorized transactions
    uncategorized = db.query(Transaction).filter(
        Transaction.category == None,
        Transaction.ai_categorized == False
    ).limit(batch_size).all()
    
    categorized_count = 0
    
    for trans in uncategorized:
        # This would use AI to categorize
        # For now, use simple rules
        description = (trans.description or "").lower()
        
        if any(word in description for word in ["grocery", "food", "restaurant", "cafe"]):
            trans.category = "Food & Dining"
        elif any(word in description for word in ["gas", "fuel", "parking"]):
            trans.category = "Transportation"
        elif any(word in description for word in ["rent", "mortgage", "utilities"]):
            trans.category = "Housing"
        else:
            trans.category = "Other"
        
        trans.ai_categorized = True
        trans.ai_confidence = 0.8
        categorized_count += 1
    
    db.commit()
    
    return {
        "categorized": categorized_count,
        "remaining": db.query(Transaction).filter(
            Transaction.category == None
        ).count()
    }


@router.get("/insights/spending-velocity")
async def get_spending_velocity(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Calculate spending velocity and burn rate"""
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    
    # Get daily spending
    daily_spending = db.query(
        Transaction.date,
        func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.date >= start_date,
        Transaction.type == TransactionType.EXPENSE
    ).group_by(Transaction.date).all()
    
    if not daily_spending:
        return {"error": "No spending data available"}
    
    # Calculate metrics
    amounts = [float(total) for _, total in daily_spending]
    avg_daily = sum(amounts) / len(amounts)
    max_daily = max(amounts)
    min_daily = min(amounts)
    
    # Velocity trend (is spending accelerating?)
    first_half = amounts[:len(amounts)//2]
    second_half = amounts[len(amounts)//2:]
    
    velocity_change = (
        (sum(second_half) / len(second_half)) - 
        (sum(first_half) / len(first_half))
    ) if first_half and second_half else 0
    
    return {
        "period_days": days,
        "average_daily_spend": avg_daily,
        "max_daily_spend": max_daily,
        "min_daily_spend": min_daily,
        "monthly_projection": avg_daily * 30,
        "yearly_projection": avg_daily * 365,
        "velocity_trend": "accelerating" if velocity_change > 0 else "decelerating",
        "velocity_change_daily": velocity_change,
        "days_analyzed": len(amounts)
    }


@router.post("/budget/create")
async def create_budget_rule(
    category: str,
    monthly_limit: float,
    alert_threshold: float = 0.8,
    db: Session = Depends(get_db)
):
    """Create a budget rule for a category"""
    rule = BudgetRule(
        name=f"Budget for {category}",
        category=category,
        monthly_limit=monthly_limit,
        alert_threshold=alert_threshold,
        period_start=date.today().replace(day=1)
    )
    
    db.add(rule)
    db.commit()
    
    return {"message": "Budget rule created", "rule_id": rule.id}


@router.get("/budget/status")
async def get_budget_status(
    db: Session = Depends(get_db)
):
    """Get current budget status for all rules"""
    rules = db.query(BudgetRule).filter(
        BudgetRule.alert_enabled == True
    ).all()
    
    current_month_start = date.today().replace(day=1)
    
    budget_status = []
    
    for rule in rules:
        # Calculate current month spending
        spent = db.query(func.sum(Transaction.amount)).filter(
            Transaction.category == rule.category,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.date >= current_month_start
        ).scalar() or 0
        
        percentage = (spent / rule.monthly_limit * 100) if rule.monthly_limit else 0
        
        budget_status.append({
            "category": rule.category,
            "limit": rule.monthly_limit,
            "spent": float(spent),
            "remaining": rule.monthly_limit - float(spent),
            "percentage": percentage,
            "status": "over" if percentage > 100 else "warning" if percentage > rule.alert_threshold * 100 else "ok"
        })
    
    return budget_status