import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import structlog
from src.config import settings
from src.models import OAuthToken, AccountingEntry, Receipt, SessionLocal

logger = structlog.get_logger()


class FikenService:
    """Service for integrating with Fiken accounting API"""
    
    def __init__(self):
        self.base_url = settings.fiken_api_url
        self.company_id = settings.fiken_company_id
        self.client_id = settings.fiken_client_id
        self.client_secret = settings.fiken_client_secret
        self.redirect_uri = settings.fiken_redirect_uri
    
    def get_auth_url(self) -> str:
        """Generate OAuth2 authorization URL for Fiken"""
        auth_url = (
            f"https://fiken.no/oauth/authorize?"
            f"client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&response_type=code"
            f"&state=accountant-ai"
        )
        return auth_url
    
    def handle_oauth_callback(self, authorization_code: str) -> bool:
        """Handle OAuth2 callback and store tokens"""
        try:
            # Exchange code for tokens
            token_url = "https://fiken.no/oauth/token"
            
            data = {
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": self.redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            response = requests.post(token_url, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Store tokens in database
                db = SessionLocal()
                try:
                    token = db.query(OAuthToken).filter_by(service='fiken').first()
                    if not token:
                        token = OAuthToken(service='fiken')
                    
                    token.access_token = token_data['access_token']
                    token.refresh_token = token_data.get('refresh_token')
                    token.token_type = token_data.get('token_type', 'Bearer')
                    
                    # Calculate expiry
                    expires_in = token_data.get('expires_in', 3600)
                    token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                    
                    db.add(token)
                    db.commit()
                    
                    logger.info("Fiken OAuth tokens stored successfully")
                    return True
                    
                finally:
                    db.close()
            else:
                logger.error(f"Failed to exchange code for tokens: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to handle OAuth callback: {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """Get authenticated headers for API requests"""
        db = SessionLocal()
        try:
            token = db.query(OAuthToken).filter_by(service='fiken').first()
            if not token:
                raise Exception("Fiken not authenticated. Please complete OAuth flow.")
            
            # Check if token needs refresh
            if token.expires_at and token.expires_at < datetime.utcnow():
                self._refresh_token(token)
            
            return {
                "Authorization": f"Bearer {token.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        finally:
            db.close()
    
    def _refresh_token(self, token: OAuthToken) -> bool:
        """Refresh expired access token"""
        try:
            token_url = "https://fiken.no/oauth/token"
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }
            
            response = requests.post(token_url, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                token.access_token = token_data['access_token']
                if 'refresh_token' in token_data:
                    token.refresh_token = token_data['refresh_token']
                
                expires_in = token_data.get('expires_in', 3600)
                token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                
                # Update in database
                db = SessionLocal()
                try:
                    db.add(token)
                    db.commit()
                finally:
                    db.close()
                
                logger.info("Fiken token refreshed successfully")
                return True
            else:
                logger.error(f"Failed to refresh token: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test API connection"""
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{self.base_url}/companies/{self.company_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Successfully connected to Fiken API")
                return True
            else:
                logger.error(f"Fiken API connection failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Fiken API: {e}")
            return False
    
    def get_accounts(self) -> List[Dict]:
        """Get chart of accounts from Fiken"""
        try:
            headers = self._get_headers()
            response = requests.get(
                f"{self.base_url}/companies/{self.company_id}/accounts",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to fetch accounts: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching accounts: {e}")
            return []
    
    def create_purchase_invoice(self, receipt: Receipt) -> Optional[str]:
        """Create a purchase invoice in Fiken from a receipt"""
        try:
            headers = self._get_headers()
            
            # Prepare invoice data
            invoice_data = {
                "issueDate": receipt.invoice_date.strftime("%Y-%m-%d"),
                "dueDate": receipt.due_date.strftime("%Y-%m-%d") if receipt.due_date else None,
                "invoiceNumber": receipt.invoice_number or f"AI-{receipt.id}",
                "currency": receipt.currency,
                "supplier": {
                    "name": receipt.vendor_name
                },
                "lines": self._prepare_invoice_lines(receipt),
                "attachments": []  # Could add receipt file as attachment
            }
            
            response = requests.post(
                f"{self.base_url}/companies/{self.company_id}/purchases",
                headers=headers,
                json=invoice_data,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                invoice_id = result.get('purchaseId')
                logger.info(f"Created purchase invoice in Fiken: {invoice_id}")
                return invoice_id
            else:
                logger.error(f"Failed to create purchase invoice: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating purchase invoice: {e}")
            return None
    
    def _prepare_invoice_lines(self, receipt: Receipt) -> List[Dict]:
        """Prepare invoice lines from receipt data"""
        lines = []
        
        # If we have detailed items from AI extraction
        if receipt.ai_extracted_data and receipt.ai_extracted_data.get('items'):
            for item in receipt.ai_extracted_data['items']:
                line = {
                    "description": item.get('description', 'Item'),
                    "netAmount": int(float(item.get('total', 0)) * 100),  # Fiken uses cents
                    "vatType": self._get_vat_type(receipt),
                    "account": self._get_account_for_category(receipt.category)
                }
                lines.append(line)
        else:
            # Single line for the whole receipt
            net_amount = receipt.total_amount - (receipt.vat_amount or 0)
            line = {
                "description": f"Purchase from {receipt.vendor_name}",
                "netAmount": int(net_amount * 100),  # Fiken uses cents
                "vatType": self._get_vat_type(receipt),
                "account": self._get_account_for_category(receipt.category)
            }
            lines.append(line)
        
        return lines
    
    def _get_vat_type(self, receipt: Receipt) -> str:
        """Determine VAT type for Norwegian accounting"""
        # Check if it's a Norwegian receipt
        if receipt.ai_extracted_data:
            norwegian_info = receipt.ai_extracted_data.get('norwegian_specific', {})
            if norwegian_info.get('is_norwegian'):
                mva_code = norwegian_info.get('mva_code')
                if mva_code:
                    return self._map_mva_code(mva_code)
        
        # Default based on VAT amount
        if receipt.vat_amount and receipt.vat_amount > 0:
            vat_rate = (receipt.vat_amount / (receipt.total_amount - receipt.vat_amount)) * 100
            if vat_rate > 20:
                return "HIGH"  # 25% Norwegian VAT
            elif vat_rate > 10:
                return "MEDIUM"  # 15% Norwegian VAT
            else:
                return "LOW"  # 12% Norwegian VAT
        
        return "EXEMPT"
    
    def _map_mva_code(self, mva_code: str) -> str:
        """Map Norwegian MVA codes to Fiken VAT types"""
        mapping = {
            "3": "HIGH",     # 25% standard rate
            "31": "MEDIUM",  # 15% food rate
            "32": "LOW",     # 12% rate
            "5": "EXEMPT",   # 0% exempt
            "6": "OUTSIDE"   # Outside scope
        }
        return mapping.get(mva_code, "HIGH")
    
    def _get_account_for_category(self, category: str) -> str:
        """Map expense category to account number"""
        # This is a simplified mapping - should be configurable
        category_mapping = {
            "Office Supplies": "6800",
            "Rent": "6300",
            "Utilities": "6340",
            "Travel & Transportation": "7140",
            "Meals & Entertainment": "7160",
            "Professional Services": "6700",
            "Software & Subscriptions": "6810",
            "Marketing & Advertising": "7330",
            "Equipment": "6500",
            "Other": "6900"
        }
        
        return category_mapping.get(category, "6900")
    
    def create_journal_entry(self, entry_data: Dict) -> Optional[str]:
        """Create a journal entry in Fiken"""
        try:
            headers = self._get_headers()
            
            journal_entry = {
                "date": entry_data['date'],
                "description": entry_data['description'],
                "lines": entry_data['lines']
            }
            
            response = requests.post(
                f"{self.base_url}/companies/{self.company_id}/journal-entries",
                headers=headers,
                json=journal_entry,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                entry_id = result.get('journalEntryId')
                logger.info(f"Created journal entry in Fiken: {entry_id}")
                return entry_id
            else:
                logger.error(f"Failed to create journal entry: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating journal entry: {e}")
            return None
    
    def sync_receipt_to_fiken(self, receipt_id: int) -> bool:
        """Sync a processed receipt to Fiken"""
        db = SessionLocal()
        
        try:
            receipt = db.query(Receipt).filter_by(id=receipt_id).first()
            if not receipt or receipt.status != 'processed':
                logger.error(f"Receipt {receipt_id} not ready for sync")
                return False
            
            # Check if already synced
            existing_entry = db.query(AccountingEntry).filter_by(
                receipt_id=receipt_id,
                status='synced'
            ).first()
            
            if existing_entry:
                logger.info(f"Receipt {receipt_id} already synced")
                return True
            
            # Create purchase invoice in Fiken
            fiken_invoice_id = self.create_purchase_invoice(receipt)
            
            if fiken_invoice_id:
                # Create accounting entry record
                entry = AccountingEntry(
                    receipt_id=receipt_id,
                    fiken_entry_id=fiken_invoice_id,
                    entry_date=receipt.invoice_date,
                    description=f"Purchase from {receipt.vendor_name}",
                    debit_account=self._get_account_for_category(receipt.category),
                    credit_account="2400",  # Accounts Payable
                    amount=receipt.total_amount,
                    vat_code=self._get_vat_type(receipt),
                    status='synced',
                    synced_at=datetime.utcnow()
                )
                
                db.add(entry)
                db.commit()
                
                logger.info(f"Successfully synced receipt {receipt_id} to Fiken")
                return True
            else:
                # Create failed entry record
                entry = AccountingEntry(
                    receipt_id=receipt_id,
                    entry_date=receipt.invoice_date,
                    description=f"Purchase from {receipt.vendor_name}",
                    debit_account=self._get_account_for_category(receipt.category),
                    credit_account="2400",
                    amount=receipt.total_amount,
                    status='error',
                    sync_error="Failed to create invoice in Fiken"
                )
                
                db.add(entry)
                db.commit()
                
                return False
                
        except Exception as e:
            logger.error(f"Error syncing receipt to Fiken: {e}")
            db.rollback()
            return False
            
        finally:
            db.close()


# Singleton instance
fiken_service = FikenService()