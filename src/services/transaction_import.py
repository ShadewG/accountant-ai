import pandas as pd
import json
from typing import List, Dict, Optional
from datetime import datetime, date
import structlog
from sqlalchemy.orm import Session
import hashlib

from src.models import SessionLocal
from src.models.transactions import Transaction, TransactionType, TransactionSource
from src.services.openai_service import openai_service

logger = structlog.get_logger()


class TransactionImportService:
    """Service for importing transaction history from various sources"""
    
    def __init__(self):
        self.supported_formats = ['csv', 'xlsx', 'xls', 'json']
        
    def import_csv(self, file_path: str, source: str = "bank") -> Dict:
        """Import transactions from CSV file"""
        try:
            # Read CSV with various encodings
            encodings = ['utf-8', 'latin-1', 'iso-8859-1']
            df = None
            
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if df is None:
                raise Exception("Could not read CSV file with any encoding")
            
            # Detect column mappings using AI
            column_mapping = self._detect_columns(df)
            
            # Process and import transactions
            return self._process_dataframe(df, column_mapping, TransactionSource.CSV_IMPORT)
            
        except Exception as e:
            logger.error(f"Failed to import CSV: {e}")
            return {"error": str(e), "imported": 0}
    
    def import_excel(self, file_path: str) -> Dict:
        """Import transactions from Excel file"""
        try:
            # Read Excel file
            df = pd.read_excel(file_path)
            
            # Detect column mappings
            column_mapping = self._detect_columns(df)
            
            # Process and import
            return self._process_dataframe(df, column_mapping, TransactionSource.EXCEL_IMPORT)
            
        except Exception as e:
            logger.error(f"Failed to import Excel: {e}")
            return {"error": str(e), "imported": 0}
    
    def import_bank_statement(self, file_path: str, bank_name: str) -> Dict:
        """Import bank statement with bank-specific parsing"""
        # Bank-specific parsers
        bank_parsers = {
            "dnb": self._parse_dnb_statement,
            "nordea": self._parse_nordea_statement,
            "sparebank1": self._parse_sparebank1_statement,
            "handelsbanken": self._parse_handelsbanken_statement,
            "danske": self._parse_danske_statement,
        }
        
        parser = bank_parsers.get(bank_name.lower(), self.import_csv)
        return parser(file_path)
    
    def _detect_columns(self, df: pd.DataFrame) -> Dict:
        """Use AI to detect column mappings"""
        # Get sample data
        sample = df.head(5).to_dict('records')
        columns = df.columns.tolist()
        
        prompt = f"""
        Analyze these columns and sample data to identify transaction fields:
        
        Columns: {columns}
        Sample data: {json.dumps(sample, indent=2, default=str)}
        
        Return a JSON mapping:
        {{
            "date": "column_name_for_date",
            "amount": "column_name_for_amount",
            "description": "column_name_for_description",
            "merchant": "column_name_for_merchant_if_exists",
            "category": "column_name_for_category_if_exists",
            "account": "column_name_for_account_if_exists",
            "balance": "column_name_for_balance_if_exists",
            "type": "column_name_for_transaction_type_if_exists"
        }}
        
        Use null for fields that don't exist.
        """
        
        # This would call OpenAI to detect columns
        # For now, use common patterns
        mapping = {}
        
        for col in columns:
            col_lower = col.lower()
            if 'date' in col_lower or 'dato' in col_lower:
                mapping['date'] = col
            elif 'amount' in col_lower or 'beløp' in col_lower or 'sum' in col_lower:
                mapping['amount'] = col
            elif 'description' in col_lower or 'beskrivelse' in col_lower or 'tekst' in col_lower:
                mapping['description'] = col
            elif 'merchant' in col_lower or 'forretning' in col_lower:
                mapping['merchant'] = col
            elif 'category' in col_lower or 'kategori' in col_lower:
                mapping['category'] = col
            elif 'account' in col_lower or 'konto' in col_lower:
                mapping['account'] = col
        
        return mapping
    
    def _process_dataframe(self, df: pd.DataFrame, mapping: Dict, source: TransactionSource) -> Dict:
        """Process dataframe and import transactions"""
        db = SessionLocal()
        imported = 0
        skipped = 0
        errors = []
        
        # Generate batch ID
        batch_id = f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            for idx, row in df.iterrows():
                try:
                    # Extract fields
                    transaction_date = self._parse_date(row.get(mapping.get('date')))
                    amount = self._parse_amount(row.get(mapping.get('amount')))
                    
                    if not transaction_date or amount is None:
                        skipped += 1
                        continue
                    
                    # Generate unique ID for deduplication
                    source_id = self._generate_source_id(row, mapping)
                    
                    # Check if already exists
                    existing = db.query(Transaction).filter_by(
                        source_id=source_id
                    ).first()
                    
                    if existing:
                        skipped += 1
                        continue
                    
                    # Determine transaction type
                    trans_type = TransactionType.EXPENSE if amount < 0 else TransactionType.INCOME
                    
                    # Create transaction
                    transaction = Transaction(
                        date=transaction_date,
                        amount=abs(amount),
                        type=trans_type,
                        description=row.get(mapping.get('description', ''), ''),
                        merchant=row.get(mapping.get('merchant'), None),
                        category=row.get(mapping.get('category'), None),
                        account_name=row.get(mapping.get('account'), None),
                        source=source,
                        source_id=source_id,
                        import_batch_id=batch_id,
                        raw_data=row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                    )
                    
                    db.add(transaction)
                    imported += 1
                    
                    # Commit in batches
                    if imported % 100 == 0:
                        db.commit()
                        
                except Exception as e:
                    errors.append(f"Row {idx}: {str(e)}")
                    continue
            
            # Final commit
            db.commit()
            
            # Trigger AI categorization for new transactions
            self._trigger_categorization(batch_id)
            
            return {
                "success": True,
                "imported": imported,
                "skipped": skipped,
                "errors": errors[:10],  # Limit error messages
                "batch_id": batch_id
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Import failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "imported": imported
            }
        finally:
            db.close()
    
    def _parse_date(self, date_value) -> Optional[date]:
        """Parse various date formats"""
        if not date_value:
            return None
            
        if isinstance(date_value, date):
            return date_value
            
        # Try common date formats
        formats = [
            "%Y-%m-%d",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%Y/%m/%d",
            "%d-%m-%Y"
        ]
        
        date_str = str(date_value)
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _parse_amount(self, amount_value) -> Optional[float]:
        """Parse various amount formats"""
        if amount_value is None:
            return None
            
        if isinstance(amount_value, (int, float)):
            return float(amount_value)
        
        # Clean string amount
        amount_str = str(amount_value)
        amount_str = amount_str.replace(',', '.')  # Norwegian decimal
        amount_str = amount_str.replace(' ', '')  # Remove spaces
        amount_str = amount_str.replace('kr', '')  # Remove currency
        amount_str = amount_str.replace('NOK', '')
        
        try:
            return float(amount_str)
        except ValueError:
            return None
    
    def _generate_source_id(self, row, mapping) -> str:
        """Generate unique ID for transaction deduplication"""
        # Create hash from key fields
        key_data = f"{row.get(mapping.get('date', ''))}"
        key_data += f"{row.get(mapping.get('amount', ''))}"
        key_data += f"{row.get(mapping.get('description', ''))}"
        
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _trigger_categorization(self, batch_id: str):
        """Trigger AI categorization for imported transactions"""
        # This would be handled by a background task
        logger.info(f"Triggering AI categorization for batch {batch_id}")
    
    # Bank-specific parsers
    def _parse_dnb_statement(self, file_path: str) -> Dict:
        """Parse DNB bank statement"""
        df = pd.read_csv(file_path, sep=';', encoding='latin-1')
        
        mapping = {
            'date': 'Dato',
            'amount': 'Beløp',
            'description': 'Forklaring',
            'account': 'Fra konto'
        }
        
        return self._process_dataframe(df, mapping, TransactionSource.BANK_IMPORT)
    
    def _parse_nordea_statement(self, file_path: str) -> Dict:
        """Parse Nordea bank statement"""
        df = pd.read_csv(file_path, sep='\t', encoding='utf-8')
        
        mapping = {
            'date': 'Bokføringsdato',
            'amount': 'Beløp',
            'description': 'Melding',
            'account': 'Konto'
        }
        
        return self._process_dataframe(df, mapping, TransactionSource.BANK_IMPORT)
    
    def _parse_sparebank1_statement(self, file_path: str) -> Dict:
        """Parse SpareBank 1 statement"""
        df = pd.read_excel(file_path)
        
        mapping = {
            'date': 'Bokført',
            'amount': 'Beløp',
            'description': 'Tekst',
            'account': 'Kontonummer'
        }
        
        return self._process_dataframe(df, mapping, TransactionSource.BANK_IMPORT)
    
    def _parse_handelsbanken_statement(self, file_path: str) -> Dict:
        """Parse Handelsbanken statement"""
        df = pd.read_csv(file_path, encoding='iso-8859-1')
        
        mapping = {
            'date': 'Transaksjonsdato',
            'amount': 'Beløp',
            'description': 'Beskrivelse'
        }
        
        return self._process_dataframe(df, mapping, TransactionSource.BANK_IMPORT)
    
    def _parse_danske_statement(self, file_path: str) -> Dict:
        """Parse Danske Bank statement"""
        df = pd.read_csv(file_path, sep=';')
        
        mapping = {
            'date': 'Date',
            'amount': 'Amount',
            'description': 'Text',
            'category': 'Category'
        }
        
        return self._process_dataframe(df, mapping, TransactionSource.BANK_IMPORT)


# Singleton instance
transaction_import_service = TransactionImportService()