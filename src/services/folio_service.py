import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import structlog
from src.config import settings
from src.models import Payment, SessionLocal

logger = structlog.get_logger()


class FolioService:
    """
    Service for integrating with Folio.no GraphQL API
    Folio.no is a Norwegian business banking/accounting service
    """
    
    def __init__(self):
        self.base_url = "https://app.folio.no/graphql"
        self.api_url = "https://api.folio.no/"
        self.session_cookie = settings.folio_session_cookie
        self.org_number = settings.folio_org_number
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Folio API requests"""
        return {
            "Cookie": f"folioSession={self.session_cookie}",
            "folio-org-number": self.org_number,
            "content-type": "application/json",
            "origin": "https://app.folio.no"
        }
    
    def test_connection(self) -> bool:
        """Test API connection"""
        try:
            # Simple query to test connection
            query = """
            query TestConnection {
                bookedActivities(
                    bookedBetween: {startDate: "2024-01-01", endDate: "2024-01-01"}
                ) {
                    items {
                        startedAt
                    }
                }
            }
            """
            
            response = requests.post(
                self.base_url,
                headers=self._get_headers(),
                json={"query": query},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if "errors" not in data:
                    logger.info("Successfully connected to Folio API")
                    return True
                else:
                    logger.error(f"Folio API error: {data['errors']}")
                    return False
            else:
                logger.error(f"Folio API connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Folio API: {e}")
            return False
    
    def get_booked_activities(self, start_date: str, end_date: str) -> List[Dict]:
        """Fetch booked activities (transactions) from Folio"""
        query = """
        query GetBookedActivities($startDate: Date!, $endDate: Date!) {
            bookedActivities(
                bookedBetween: {startDate: $startDate, endDate: $endDate}
            ) {
                items {
                    id
                    startedAt
                    bookedAt
                    booked
                    accountingCategoryInfo {
                        kind
                        category {
                            title
                            account {
                                folio
                            }
                        }
                    }
                    merchant {
                        name
                    }
                    nokAmount {
                        asNumericString
                    }
                    strings {
                        description
                    }
                    paidFrom {
                        account {
                            accountNumber
                        }
                        nokAmount {
                            asNumericString
                        }
                    }
                    paidTo {
                        account {
                            accountNumber
                        }
                        nokAmount {
                            asNumericString
                        }
                    }
                }
            }
        }
        """
        
        try:
            response = requests.post(
                self.base_url,
                headers=self._get_headers(),
                json={
                    "query": query,
                    "variables": {
                        "startDate": start_date,
                        "endDate": end_date
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return []
                
                activities = data.get("data", {}).get("bookedActivities", {}).get("items", [])
                logger.info(f"Retrieved {len(activities)} activities from Folio")
                return activities
            else:
                logger.error(f"Failed to fetch activities: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching activities: {e}")
            return []
    
    def get_recent_payments(self, days_back: int = 30) -> List[Dict]:
        """Fetch recent payment activities from Folio"""
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        activities = self.get_booked_activities(start_date, end_date)
        
        # Filter for incoming payments (where money comes into accounts)
        payments = []
        for activity in activities:
            # Check if this is an incoming payment
            if activity.get("paidTo") and activity["paidTo"].get("nokAmount"):
                payment = {
                    "id": activity.get("id"),
                    "date": activity.get("bookedAt") or activity.get("startedAt"),
                    "amount": float(activity["paidTo"]["nokAmount"]["asNumericString"]),
                    "merchant": activity.get("merchant", {}).get("name", "Unknown"),
                    "description": activity.get("strings", {}).get("description", ""),
                    "account": activity["paidTo"]["account"]["accountNumber"],
                    "category": self._extract_category(activity),
                    "raw_data": activity
                }
                payments.append(payment)
        
        return payments
    
    def get_expenses(self, days_back: int = 30) -> List[Dict]:
        """Fetch recent expense activities from Folio"""
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        activities = self.get_booked_activities(start_date, end_date)
        
        # Filter for outgoing payments (expenses)
        expenses = []
        for activity in activities:
            # Check if this is an outgoing payment
            if activity.get("paidFrom") and activity["paidFrom"].get("nokAmount"):
                expense = {
                    "id": activity.get("id"),
                    "date": activity.get("bookedAt") or activity.get("startedAt"),
                    "amount": float(activity["paidFrom"]["nokAmount"]["asNumericString"]),
                    "merchant": activity.get("merchant", {}).get("name", "Unknown"),
                    "description": activity.get("strings", {}).get("description", ""),
                    "account": activity["paidFrom"]["account"]["accountNumber"],
                    "category": self._extract_category(activity),
                    "raw_data": activity
                }
                expenses.append(expense)
        
        return expenses
    
    def _extract_category(self, activity: Dict) -> Optional[str]:
        """Extract category information from activity"""
        category_info = activity.get("accountingCategoryInfo", {})
        if category_info and category_info.get("category"):
            return category_info["category"].get("title")
        return None
    
    def sync_payments(self) -> int:
        """Sync payments from Folio to local database"""
        db = SessionLocal()
        synced_count = 0
        
        try:
            # Fetch recent payments
            folio_payments = self.get_recent_payments()
            
            for folio_payment in folio_payments:
                # Check if payment already exists
                existing = db.query(Payment).filter_by(
                    folio_payment_id=str(folio_payment.get('id'))
                ).first()
                
                if existing:
                    continue
                
                # Create new payment record
                payment = Payment(
                    folio_payment_id=str(folio_payment.get('id')),
                    tenant_name=folio_payment.get('merchant'),  # In Folio, merchant is the payer
                    property_name=folio_payment.get('account'),  # Account number
                    amount=folio_payment.get('amount'),
                    payment_date=self._parse_date(folio_payment.get('date')),
                    payment_method='bank_transfer',  # Folio is primarily bank transactions
                    reference=folio_payment.get('description'),
                    status='unmatched',
                    synced_at=datetime.utcnow()
                )
                
                db.add(payment)
                synced_count += 1
            
            db.commit()
            logger.info(f"Synced {synced_count} new payments from Folio")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing payments: {e}")
            db.rollback()
            return 0
            
        finally:
            db.close()
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime"""
        if not date_str:
            return datetime.utcnow()
        
        # Try different date formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Fallback
        logger.warning(f"Could not parse date: {date_str}")
        return datetime.utcnow()
    
    def get_accounts(self) -> List[Dict]:
        """Get list of accounts from Folio"""
        query = """
        query GetAccounts {
            accounts {
                items {
                    accountNumber
                    name
                    balance {
                        nokAmount {
                            asNumericString
                        }
                    }
                }
            }
        }
        """
        
        try:
            response = requests.post(
                self.base_url,
                headers=self._get_headers(),
                json={"query": query},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if "errors" not in data:
                    accounts = data.get("data", {}).get("accounts", {}).get("items", [])
                    return accounts
                
            return []
            
        except Exception as e:
            logger.error(f"Error fetching accounts: {e}")
            return []
    
    def match_expense_to_receipt(self, expense: Dict, receipt) -> float:
        """Calculate match confidence between Folio expense and receipt"""
        confidence = 0.0
        
        # Amount matching (40% weight)
        expense_amount = abs(expense.get('amount', 0))
        receipt_amount = abs(receipt.total_amount)
        
        if expense_amount == receipt_amount:
            confidence += 0.4
        elif abs(expense_amount - receipt_amount) < 1.0:  # Within 1 NOK
            confidence += 0.35
        elif abs(expense_amount - receipt_amount) / receipt_amount < 0.02:  # Within 2%
            confidence += 0.3
        
        # Date matching (30% weight)
        expense_date = self._parse_date(expense.get('date'))
        if receipt.invoice_date:
            date_diff = abs((expense_date - receipt.invoice_date).days)
            if date_diff == 0:
                confidence += 0.3
            elif date_diff <= 3:
                confidence += 0.25
            elif date_diff <= 7:
                confidence += 0.2
            elif date_diff <= 14:
                confidence += 0.1
        
        # Merchant/vendor matching (30% weight)
        expense_merchant = expense.get('merchant', '').lower()
        receipt_vendor = (receipt.vendor_name or '').lower()
        
        if expense_merchant and receipt_vendor:
            if expense_merchant == receipt_vendor:
                confidence += 0.3
            elif expense_merchant in receipt_vendor or receipt_vendor in expense_merchant:
                confidence += 0.25
            elif any(word in receipt_vendor for word in expense_merchant.split()):
                confidence += 0.2
        
        return min(confidence, 1.0)


# Singleton instance
folio_service = FolioService()