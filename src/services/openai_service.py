import base64
import json
from typing import Dict, Optional, List
from datetime import datetime
import openai
from PIL import Image
import PyPDF2
import pdf2image
import structlog
from src.config import settings
from src.models import Receipt, SessionLocal

logger = structlog.get_logger()


class OpenAIService:
    def __init__(self):
        openai.api_key = settings.openai_api_key
        self.model = settings.openai_model
        
    def analyze_receipt(self, file_path: str) -> Dict:
        """Analyze receipt/invoice using GPT-4 Vision"""
        try:
            # Determine file type
            file_ext = file_path.lower().split('.')[-1]
            
            if file_ext == 'pdf':
                # Convert PDF to images
                images = self._pdf_to_images(file_path)
                if not images:
                    raise Exception("Failed to convert PDF to images")
                # Use first page for now
                base64_image = self._image_to_base64(images[0])
            else:
                # Direct image file
                base64_image = self._image_to_base64(file_path)
            
            # Prepare the prompt
            prompt = self._create_analysis_prompt()
            
            # Call OpenAI Vision API
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert accountant analyzing receipts and invoices. Extract all relevant information and return it in the specified JSON format."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0.1
            )
            
            # Parse response
            result = json.loads(response.choices[0].message.content)
            
            # Add confidence score based on completeness
            result['confidence'] = self._calculate_confidence(result)
            
            logger.info(f"Successfully analyzed receipt: {file_path}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze receipt: {e}")
            return {
                "error": str(e),
                "confidence": 0
            }
    
    def _create_analysis_prompt(self) -> str:
        """Create the analysis prompt for GPT-4"""
        return """
        Analyze this receipt/invoice and extract the following information.
        Return the data as a JSON object with these fields:
        
        {
            "vendor_name": "Company/vendor name",
            "vendor_org_number": "Organization number if visible",
            "invoice_number": "Invoice/receipt number",
            "invoice_date": "Date in YYYY-MM-DD format",
            "due_date": "Due date in YYYY-MM-DD format (null if not present)",
            "currency": "Currency code (NOK, USD, EUR, etc.)",
            "subtotal": "Subtotal amount before tax",
            "vat_amount": "VAT/tax amount",
            "vat_rate": "VAT rate percentage",
            "total_amount": "Total amount including tax",
            "payment_method": "Payment method if visible",
            "items": [
                {
                    "description": "Item description",
                    "quantity": "Quantity",
                    "unit_price": "Price per unit",
                    "total": "Line total"
                }
            ],
            "category": "Suggested category (e.g., Office Supplies, Rent, Utilities, Travel, etc.)",
            "norwegian_specific": {
                "is_norwegian": "true/false",
                "mva_code": "Norwegian VAT code if applicable",
                "kid_number": "KID number if present"
            },
            "notes": "Any additional relevant information"
        }
        
        Important:
        - Extract amounts as numbers only (no currency symbols)
        - For Norwegian receipts, identify MVA (VAT) information
        - If any field is not visible or unclear, use null
        - Dates should be in YYYY-MM-DD format
        - Be especially careful with Norwegian receipts (kvittering/faktura)
        """
    
    def _pdf_to_images(self, pdf_path: str) -> List:
        """Convert PDF to images"""
        try:
            images = pdf2image.convert_from_path(pdf_path)
            return images
        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            # Try alternative method
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    # Extract text as fallback
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                    # Return text-based analysis instead
                    return self._analyze_text_receipt(text)
            except:
                return []
    
    def _image_to_base64(self, image_path) -> str:
        """Convert image to base64 string"""
        if isinstance(image_path, str):
            # File path
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        else:
            # PIL Image object
            import io
            buffered = io.BytesIO()
            image_path.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def _calculate_confidence(self, result: Dict) -> float:
        """Calculate confidence score based on extracted data completeness"""
        required_fields = ['vendor_name', 'invoice_date', 'total_amount']
        important_fields = ['invoice_number', 'vat_amount', 'currency']
        
        score = 0.0
        
        # Check required fields (60% weight)
        for field in required_fields:
            if result.get(field) and result[field] != 'null':
                score += 0.2
        
        # Check important fields (30% weight)
        for field in important_fields:
            if result.get(field) and result[field] != 'null':
                score += 0.1
        
        # Check if items are extracted (10% weight)
        if result.get('items') and len(result['items']) > 0:
            score += 0.1
        
        return min(score, 1.0)
    
    def match_payment_to_receipt(self, payment: Dict, receipts: List[Receipt]) -> Optional[Dict]:
        """Use AI to match a payment to potential receipts"""
        try:
            # Prepare receipt summaries
            receipt_summaries = []
            for receipt in receipts:
                if receipt.ai_extracted_data:
                    summary = {
                        "id": receipt.id,
                        "vendor": receipt.vendor_name,
                        "amount": receipt.total_amount,
                        "date": receipt.invoice_date.isoformat() if receipt.invoice_date else None,
                        "invoice_number": receipt.invoice_number
                    }
                    receipt_summaries.append(summary)
            
            prompt = f"""
            Match this payment to the most likely receipt:
            
            Payment:
            - Amount: {payment['amount']} {payment.get('currency', 'NOK')}
            - Date: {payment['payment_date']}
            - Reference: {payment.get('reference', 'N/A')}
            - Tenant/Payer: {payment.get('tenant_name', 'N/A')}
            
            Available Receipts:
            {json.dumps(receipt_summaries, indent=2)}
            
            Return a JSON object:
            {{
                "matched_receipt_id": "ID of matched receipt or null",
                "confidence": "0.0 to 1.0",
                "reasoning": "Explanation of the match",
                "match_type": "exact|fuzzy|none"
            }}
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert accountant matching payments to receipts."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Failed to match payment: {e}")
            return None
    
    def categorize_expense(self, receipt_data: Dict) -> str:
        """Categorize expense for accounting purposes"""
        try:
            prompt = f"""
            Based on this receipt data, suggest the most appropriate accounting category:
            
            Vendor: {receipt_data.get('vendor_name')}
            Items: {json.dumps(receipt_data.get('items', []))}
            Amount: {receipt_data.get('total_amount')} {receipt_data.get('currency')}
            
            Common categories:
            - Office Supplies
            - Rent
            - Utilities
            - Travel & Transportation
            - Meals & Entertainment
            - Professional Services
            - Software & Subscriptions
            - Marketing & Advertising
            - Equipment
            - Other
            
            Return only the category name.
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            category = response.choices[0].message.content.strip()
            return category
            
        except Exception as e:
            logger.error(f"Failed to categorize expense: {e}")
            return "Other"
    
    def process_receipt(self, receipt_id: int) -> bool:
        """Process a single receipt"""
        db = SessionLocal()
        
        try:
            receipt = db.query(Receipt).filter_by(id=receipt_id).first()
            if not receipt:
                logger.error(f"Receipt not found: {receipt_id}")
                return False
            
            # Analyze the receipt
            analysis_result = self.analyze_receipt(receipt.file_path)
            
            if 'error' in analysis_result:
                receipt.status = 'error'
                receipt.error_message = analysis_result['error']
            else:
                # Update receipt with extracted data
                receipt.vendor_name = analysis_result.get('vendor_name')
                receipt.invoice_number = analysis_result.get('invoice_number')
                
                # Parse dates
                if analysis_result.get('invoice_date'):
                    receipt.invoice_date = datetime.fromisoformat(analysis_result['invoice_date'])
                if analysis_result.get('due_date'):
                    receipt.due_date = datetime.fromisoformat(analysis_result['due_date'])
                
                receipt.total_amount = float(analysis_result.get('total_amount', 0))
                receipt.vat_amount = float(analysis_result.get('vat_amount', 0))
                receipt.currency = analysis_result.get('currency', 'NOK')
                
                # Store full AI analysis
                receipt.ai_extracted_data = analysis_result
                receipt.ai_confidence = analysis_result.get('confidence', 0)
                
                # Categorize
                receipt.category = self.categorize_expense(analysis_result)
                
                receipt.status = 'processed'
                receipt.processed_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"Processed receipt {receipt_id}: {receipt.vendor_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process receipt {receipt_id}: {e}")
            db.rollback()
            return False
            
        finally:
            db.close()


# Singleton instance
openai_service = OpenAIService()