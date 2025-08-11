from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, JSON, Enum, Date
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from src.models.database import Base


class TransactionType(enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    INVESTMENT = "investment"
    SAVINGS = "savings"


class TransactionSource(enum.Enum):
    BANK_IMPORT = "bank_import"
    MANUAL = "manual"
    FOLIO = "folio"
    CSV_IMPORT = "csv_import"
    EXCEL_IMPORT = "excel_import"


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic transaction info
    date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default='NOK')
    type = Column(Enum(TransactionType), nullable=False)
    
    # Description and categorization
    description = Column(Text)
    merchant = Column(String(255), index=True)
    category = Column(String(100), index=True)
    subcategory = Column(String(100))
    tags = Column(JSON)  # List of tags
    
    # Account information
    account_name = Column(String(255))
    account_number = Column(String(50))
    
    # Source tracking
    source = Column(Enum(TransactionSource), nullable=False)
    source_id = Column(String(255))  # Original transaction ID from source
    import_batch_id = Column(String(100))  # For tracking bulk imports
    
    # AI Analysis
    ai_categorized = Column(Boolean, default=False)
    ai_confidence = Column(Float)
    ai_insights = Column(JSON)  # Store AI-generated insights
    
    # Metadata
    raw_data = Column(JSON)  # Original transaction data
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    analysis_reports = relationship("AnalysisReport", back_populates="transactions")


class SpendingCategory(Base):
    __tablename__ = "spending_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    parent_category = Column(String(100))
    
    # Budgeting
    monthly_budget = Column(Float)
    yearly_budget = Column(Float)
    
    # Rules for auto-categorization
    keywords = Column(JSON)  # List of keywords to match
    merchant_patterns = Column(JSON)  # Regex patterns for merchants
    
    # Visual
    color = Column(String(7))  # Hex color for charts
    icon = Column(String(50))
    
    created_at = Column(DateTime, default=datetime.utcnow)


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Report metadata
    report_type = Column(String(50))  # 'monthly', 'yearly', 'custom', 'deep_analysis'
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # AI Analysis with reasoning model
    ai_model = Column(String(50))  # Track which model was used
    analysis_prompt = Column(Text)
    
    # Results
    total_income = Column(Float)
    total_expenses = Column(Float)
    net_cashflow = Column(Float)
    
    # Category breakdowns
    category_breakdown = Column(JSON)  # {category: amount, percentage}
    merchant_breakdown = Column(JSON)  # Top merchants by spending
    
    # Insights and recommendations
    ai_insights = Column(JSON)
    spending_patterns = Column(JSON)
    anomalies = Column(JSON)
    recommendations = Column(JSON)
    
    # Visualizations data
    charts_data = Column(JSON)  # Pre-computed chart data
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    processing_time = Column(Float)  # Time taken for analysis
    
    # Relationships
    transactions = relationship("Transaction", back_populates="analysis_reports")


class BudgetRule(Base):
    __tablename__ = "budget_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Rule definition
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    
    # Limits
    daily_limit = Column(Float)
    weekly_limit = Column(Float)
    monthly_limit = Column(Float)
    yearly_limit = Column(Float)
    
    # Alert settings
    alert_threshold = Column(Float, default=0.8)  # Alert at 80% of limit
    alert_enabled = Column(Boolean, default=True)
    
    # Period tracking
    current_period_spent = Column(Float, default=0)
    period_start = Column(Date)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FinancialGoal(Base):
    __tablename__ = "financial_goals"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Goal definition
    name = Column(String(255), nullable=False)
    description = Column(Text)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0)
    
    # Timeline
    start_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=False)
    
    # Progress tracking
    progress_percentage = Column(Float, default=0)
    monthly_contribution_needed = Column(Float)
    
    # AI recommendations
    ai_suggestions = Column(JSON)
    feasibility_score = Column(Float)  # AI-calculated feasibility
    
    # Status
    is_active = Column(Boolean, default=True)
    achieved_date = Column(Date)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)