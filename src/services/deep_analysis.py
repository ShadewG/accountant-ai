import openai
import json
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta
from sqlalchemy import func
import structlog
import numpy as np

from src.config import settings
from src.models import SessionLocal
from src.models.transactions import Transaction, TransactionType, AnalysisReport, SpendingCategory

logger = structlog.get_logger()


class DeepAnalysisService:
    """Advanced financial analysis using OpenAI's reasoning models"""
    
    def __init__(self):
        openai.api_key = settings.openai_api_key
        # Use latest reasoning model (o1-preview or gpt-4-turbo for deep thinking)
        self.reasoning_model = "gpt-4-turbo-preview"  # Will use o1 when available
        
    def analyze_spending_patterns(self, user_id: Optional[int] = None, 
                                 start_date: Optional[date] = None,
                                 end_date: Optional[date] = None) -> Dict:
        """Perform deep analysis on spending patterns"""
        
        db = SessionLocal()
        try:
            # Default to last 3 months
            if not end_date:
                end_date = date.today()
            if not start_date:
                start_date = end_date - timedelta(days=90)
            
            # Fetch transactions
            transactions = db.query(Transaction).filter(
                Transaction.date >= start_date,
                Transaction.date <= end_date
            ).all()
            
            if not transactions:
                return {"error": "No transactions found in the specified period"}
            
            # Prepare data for analysis
            transaction_data = self._prepare_transaction_data(transactions)
            
            # Generate deep analysis prompt
            analysis_prompt = self._create_deep_analysis_prompt(transaction_data)
            
            # Call OpenAI with reasoning model
            logger.info("Starting deep financial analysis with AI...")
            
            response = openai.ChatCompletion.create(
                model=self.reasoning_model,
                messages=[
                    {
                        "role": "system",
                        "content": """You are a expert financial analyst with deep understanding of personal finance, 
                        spending psychology, and budget optimization. Analyze the provided transaction data and provide:
                        1. Detailed spending patterns and trends
                        2. Unusual or concerning spending behaviors
                        3. Category-wise insights
                        4. Specific actionable recommendations
                        5. Potential savings opportunities
                        6. Risk factors and warnings
                        
                        Think step by step through the analysis, considering seasonal patterns, 
                        lifestyle factors, and financial health indicators."""
                    },
                    {
                        "role": "user",
                        "content": analysis_prompt
                    }
                ],
                temperature=0.2,  # Lower temperature for analytical consistency
                max_tokens=4000
            )
            
            ai_analysis = response.choices[0].message.content
            
            # Parse AI response into structured format
            structured_analysis = self._parse_ai_analysis(ai_analysis)
            
            # Calculate statistics
            stats = self._calculate_statistics(transactions)
            
            # Detect anomalies
            anomalies = self._detect_anomalies(transactions)
            
            # Generate visualizations data
            charts_data = self._prepare_chart_data(transactions)
            
            # Save analysis report
            report = AnalysisReport(
                report_type='deep_analysis',
                start_date=start_date,
                end_date=end_date,
                ai_model=self.reasoning_model,
                analysis_prompt=analysis_prompt[:1000],  # Store truncated prompt
                total_income=stats['total_income'],
                total_expenses=stats['total_expenses'],
                net_cashflow=stats['net_cashflow'],
                category_breakdown=stats['category_breakdown'],
                merchant_breakdown=stats['merchant_breakdown'],
                ai_insights=structured_analysis,
                spending_patterns=stats['patterns'],
                anomalies=anomalies,
                recommendations=structured_analysis.get('recommendations', []),
                charts_data=charts_data,
                processing_time=(datetime.utcnow() - datetime.utcnow()).total_seconds()
            )
            
            db.add(report)
            db.commit()
            
            return {
                "success": True,
                "report_id": report.id,
                "summary": {
                    "period": f"{start_date} to {end_date}",
                    "total_transactions": len(transactions),
                    "net_cashflow": stats['net_cashflow'],
                    "top_category": stats.get('top_category'),
                    "savings_potential": structured_analysis.get('savings_potential', 0)
                },
                "insights": structured_analysis,
                "statistics": stats,
                "anomalies": anomalies,
                "charts": charts_data
            }
            
        except Exception as e:
            logger.error(f"Deep analysis failed: {e}")
            return {"error": str(e)}
        finally:
            db.close()
    
    def _prepare_transaction_data(self, transactions: List[Transaction]) -> Dict:
        """Prepare transaction data for AI analysis"""
        
        # Group by category
        categories = {}
        merchants = {}
        daily_spending = {}
        
        for trans in transactions:
            # Categories
            cat = trans.category or 'Uncategorized'
            if cat not in categories:
                categories[cat] = {'count': 0, 'total': 0, 'transactions': []}
            categories[cat]['count'] += 1
            categories[cat]['total'] += trans.amount
            
            # Merchants
            if trans.merchant:
                if trans.merchant not in merchants:
                    merchants[trans.merchant] = {'count': 0, 'total': 0}
                merchants[trans.merchant]['count'] += 1
                merchants[trans.merchant]['total'] += trans.amount
            
            # Daily spending
            date_str = trans.date.isoformat()
            if date_str not in daily_spending:
                daily_spending[date_str] = {'income': 0, 'expenses': 0}
            
            if trans.type == TransactionType.INCOME:
                daily_spending[date_str]['income'] += trans.amount
            else:
                daily_spending[date_str]['expenses'] += trans.amount
        
        return {
            'categories': categories,
            'merchants': merchants,
            'daily_spending': daily_spending,
            'transaction_count': len(transactions)
        }
    
    def _create_deep_analysis_prompt(self, data: Dict) -> str:
        """Create comprehensive prompt for deep analysis"""
        
        prompt = f"""
        Analyze this financial transaction data and provide deep insights:
        
        TRANSACTION SUMMARY:
        - Total transactions: {data['transaction_count']}
        - Categories: {len(data['categories'])}
        - Unique merchants: {len(data['merchants'])}
        
        SPENDING BY CATEGORY:
        """
        
        for cat, info in sorted(data['categories'].items(), 
                               key=lambda x: x[1]['total'], 
                               reverse=True)[:10]:
            prompt += f"\n- {cat}: {info['total']:.2f} NOK ({info['count']} transactions)"
        
        prompt += "\n\nTOP MERCHANTS:"
        for merchant, info in sorted(data['merchants'].items(), 
                                    key=lambda x: x[1]['total'], 
                                    reverse=True)[:10]:
            prompt += f"\n- {merchant}: {info['total']:.2f} NOK ({info['count']} visits)"
        
        prompt += """
        
        Please provide:
        1. Key spending patterns and trends
        2. Potential problem areas or overspending
        3. Comparison to typical Norwegian spending patterns
        4. Specific savings opportunities with amounts
        5. Budget recommendations by category
        6. Risk assessment and warnings
        7. Behavioral insights about spending habits
        8. Seasonal or cyclical patterns
        
        Format your response as detailed JSON with these sections:
        {
            "executive_summary": "Brief overview",
            "spending_patterns": ["pattern1", "pattern2"],
            "problem_areas": [{"area": "", "issue": "", "monthly_impact": 0}],
            "savings_opportunities": [{"description": "", "potential_monthly_savings": 0}],
            "budget_recommendations": {"category": amount},
            "risk_factors": ["risk1", "risk2"],
            "behavioral_insights": ["insight1", "insight2"],
            "action_items": ["action1", "action2"],
            "savings_potential": total_amount
        }
        """
        
        return prompt
    
    def _parse_ai_analysis(self, ai_response: str) -> Dict:
        """Parse AI response into structured format"""
        try:
            # Try to extract JSON from response
            json_start = ai_response.find('{')
            json_end = ai_response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = ai_response[json_start:json_end]
                return json.loads(json_str)
            else:
                # Fallback to text parsing
                return {
                    "raw_analysis": ai_response,
                    "executive_summary": ai_response[:500]
                }
        except json.JSONDecodeError:
            logger.warning("Could not parse AI response as JSON")
            return {"raw_analysis": ai_response}
    
    def _calculate_statistics(self, transactions: List[Transaction]) -> Dict:
        """Calculate detailed statistics"""
        
        total_income = sum(t.amount for t in transactions if t.type == TransactionType.INCOME)
        total_expenses = sum(t.amount for t in transactions if t.type == TransactionType.EXPENSE)
        
        # Category breakdown
        category_breakdown = {}
        for trans in transactions:
            cat = trans.category or 'Uncategorized'
            if cat not in category_breakdown:
                category_breakdown[cat] = 0
            category_breakdown[cat] += trans.amount
        
        # Sort and get percentages
        total = sum(category_breakdown.values())
        for cat in category_breakdown:
            category_breakdown[cat] = {
                'amount': category_breakdown[cat],
                'percentage': (category_breakdown[cat] / total * 100) if total > 0 else 0
            }
        
        # Merchant breakdown
        merchant_breakdown = {}
        for trans in transactions:
            if trans.merchant:
                if trans.merchant not in merchant_breakdown:
                    merchant_breakdown[trans.merchant] = 0
                merchant_breakdown[trans.merchant] += trans.amount
        
        # Top merchants
        top_merchants = dict(sorted(merchant_breakdown.items(), 
                                  key=lambda x: x[1], 
                                  reverse=True)[:20])
        
        # Spending patterns
        patterns = self._analyze_patterns(transactions)
        
        return {
            'total_income': total_income,
            'total_expenses': total_expenses,
            'net_cashflow': total_income - total_expenses,
            'category_breakdown': category_breakdown,
            'merchant_breakdown': top_merchants,
            'patterns': patterns,
            'top_category': max(category_breakdown.items(), 
                              key=lambda x: x[1]['amount'])[0] if category_breakdown else None
        }
    
    def _detect_anomalies(self, transactions: List[Transaction]) -> List[Dict]:
        """Detect unusual transactions or patterns"""
        
        anomalies = []
        
        # Calculate mean and std for amounts
        amounts = [t.amount for t in transactions if t.type == TransactionType.EXPENSE]
        if amounts:
            mean_amount = np.mean(amounts)
            std_amount = np.std(amounts)
            
            # Find outliers (3 standard deviations)
            for trans in transactions:
                if trans.type == TransactionType.EXPENSE:
                    z_score = (trans.amount - mean_amount) / std_amount if std_amount > 0 else 0
                    if abs(z_score) > 3:
                        anomalies.append({
                            'date': trans.date.isoformat(),
                            'amount': trans.amount,
                            'description': trans.description,
                            'type': 'unusual_amount',
                            'z_score': z_score
                        })
        
        # Detect unusual frequency patterns
        merchant_freq = {}
        for trans in transactions:
            if trans.merchant:
                if trans.merchant not in merchant_freq:
                    merchant_freq[trans.merchant] = []
                merchant_freq[trans.merchant].append(trans.date)
        
        for merchant, dates in merchant_freq.items():
            if len(dates) > 10:  # Frequent merchant
                # Check for sudden increase in frequency
                dates.sort()
                recent = len([d for d in dates if (date.today() - d).days < 30])
                if recent > len(dates) * 0.5:  # More than 50% in last month
                    anomalies.append({
                        'merchant': merchant,
                        'type': 'frequency_spike',
                        'recent_transactions': recent,
                        'total_transactions': len(dates)
                    })
        
        return anomalies[:10]  # Limit to top 10 anomalies
    
    def _analyze_patterns(self, transactions: List[Transaction]) -> Dict:
        """Analyze spending patterns"""
        
        patterns = {
            'weekend_vs_weekday': {},
            'monthly_trend': {},
            'category_trends': {}
        }
        
        weekend_spending = 0
        weekday_spending = 0
        
        for trans in transactions:
            if trans.type == TransactionType.EXPENSE:
                if trans.date.weekday() >= 5:  # Weekend
                    weekend_spending += trans.amount
                else:
                    weekday_spending += trans.amount
        
        patterns['weekend_vs_weekday'] = {
            'weekend': weekend_spending,
            'weekday': weekday_spending,
            'weekend_ratio': weekend_spending / (weekend_spending + weekday_spending) if (weekend_spending + weekday_spending) > 0 else 0
        }
        
        return patterns
    
    def _prepare_chart_data(self, transactions: List[Transaction]) -> Dict:
        """Prepare data for charts and visualizations"""
        
        charts = {
            'daily_spending': [],
            'category_pie': [],
            'monthly_trend': [],
            'top_merchants_bar': []
        }
        
        # Daily spending line chart
        daily = {}
        for trans in transactions:
            date_str = trans.date.isoformat()
            if date_str not in daily:
                daily[date_str] = 0
            
            if trans.type == TransactionType.EXPENSE:
                daily[date_str] += trans.amount
            else:
                daily[date_str] -= trans.amount  # Income as negative
        
        charts['daily_spending'] = [
            {'date': date, 'amount': amount} 
            for date, amount in sorted(daily.items())
        ]
        
        # Category pie chart
        categories = {}
        for trans in transactions:
            if trans.type == TransactionType.EXPENSE:
                cat = trans.category or 'Uncategorized'
                categories[cat] = categories.get(cat, 0) + trans.amount
        
        total = sum(categories.values())
        charts['category_pie'] = [
            {'category': cat, 'amount': amount, 'percentage': (amount/total*100)}
            for cat, amount in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:8]
        ]
        
        return charts
    
    def generate_insights_report(self, report_id: int) -> str:
        """Generate human-readable insights report"""
        
        db = SessionLocal()
        try:
            report = db.query(AnalysisReport).filter_by(id=report_id).first()
            if not report:
                return "Report not found"
            
            insights = report.ai_insights
            
            # Format report
            report_text = f"""
            FINANCIAL ANALYSIS REPORT
            Period: {report.start_date} to {report.end_date}
            
            EXECUTIVE SUMMARY
            {insights.get('executive_summary', 'N/A')}
            
            KEY METRICS
            - Total Income: {report.total_income:,.2f} NOK
            - Total Expenses: {report.total_expenses:,.2f} NOK
            - Net Cashflow: {report.net_cashflow:,.2f} NOK
            
            SPENDING PATTERNS
            """
            
            for pattern in insights.get('spending_patterns', []):
                report_text += f"\n• {pattern}"
            
            report_text += "\n\nSAVINGS OPPORTUNITIES"
            for opp in insights.get('savings_opportunities', []):
                report_text += f"\n• {opp.get('description', '')} - Save {opp.get('potential_monthly_savings', 0):,.0f} NOK/month"
            
            report_text += "\n\nACTION ITEMS"
            for action in insights.get('action_items', []):
                report_text += f"\n✓ {action}"
            
            return report_text
            
        finally:
            db.close()


# Singleton instance
deep_analysis_service = DeepAnalysisService()