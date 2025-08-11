import base64
import os
from datetime import datetime
from typing import List, Dict, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import structlog
from src.config import settings
from src.models import OAuthToken, Receipt, SessionLocal

logger = structlog.get_logger()


class GmailService:
    def __init__(self):
        self.service = None
        self.credentials = None
        
    def get_auth_url(self) -> str:
        """Generate OAuth2 authorization URL"""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.gmail_client_id,
                    "client_secret": settings.gmail_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.gmail_redirect_uri]
                }
            },
            scopes=settings.gmail_scopes
        )
        flow.redirect_uri = settings.gmail_redirect_uri
        
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        return auth_url
    
    def handle_oauth_callback(self, authorization_code: str) -> bool:
        """Handle OAuth2 callback and store tokens"""
        try:
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": settings.gmail_client_id,
                        "client_secret": settings.gmail_client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [settings.gmail_redirect_uri]
                    }
                },
                scopes=settings.gmail_scopes
            )
            flow.redirect_uri = settings.gmail_redirect_uri
            
            # Exchange authorization code for tokens
            flow.fetch_token(code=authorization_code)
            
            credentials = flow.credentials
            
            # Store tokens in database
            db = SessionLocal()
            try:
                token = db.query(OAuthToken).filter_by(service='gmail').first()
                if not token:
                    token = OAuthToken(service='gmail')
                
                token.access_token = credentials.token
                token.refresh_token = credentials.refresh_token
                token.token_type = 'Bearer'
                token.expires_at = credentials.expiry
                token.scope = ' '.join(credentials.scopes) if credentials.scopes else None
                
                db.add(token)
                db.commit()
                
                logger.info("Gmail OAuth tokens stored successfully")
                return True
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error("Failed to handle OAuth callback", error=str(e))
            return False
    
    def _get_service(self):
        """Get authenticated Gmail service"""
        if self.service:
            return self.service
            
        db = SessionLocal()
        try:
            token = db.query(OAuthToken).filter_by(service='gmail').first()
            if not token:
                raise Exception("Gmail not authenticated. Please complete OAuth flow.")
            
            credentials = Credentials(
                token=token.access_token,
                refresh_token=token.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.gmail_client_id,
                client_secret=settings.gmail_client_secret,
                scopes=settings.gmail_scopes
            )
            
            self.service = build('gmail', 'v1', credentials=credentials)
            return self.service
            
        finally:
            db.close()
    
    def search_receipt_emails(self, query: Optional[str] = None) -> List[Dict]:
        """Search for emails containing receipts/invoices"""
        try:
            service = self._get_service()
            
            # Build search query
            if not query:
                keywords = settings.receipt_email_filter.split(',')
                query_parts = [f'"{kw.strip()}"' for kw in keywords]
                query = f"({' OR '.join(query_parts)}) has:attachment"
            
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=50
            ).execute()
            
            messages = results.get('messages', [])
            
            logger.info(f"Found {len(messages)} potential receipt emails")
            return messages
            
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            return []
    
    def get_email_with_attachments(self, message_id: str) -> Optional[Dict]:
        """Get email details including attachments"""
        try:
            service = self._get_service()
            
            message = service.users().messages().get(
                userId='me',
                id=message_id
            ).execute()
            
            email_data = {
                'id': message_id,
                'snippet': message.get('snippet', ''),
                'attachments': []
            }
            
            # Extract headers
            headers = message['payload'].get('headers', [])
            for header in headers:
                if header['name'] == 'From':
                    email_data['from'] = header['value']
                elif header['name'] == 'Subject':
                    email_data['subject'] = header['value']
                elif header['name'] == 'Date':
                    email_data['date'] = header['value']
            
            # Extract attachments
            parts = message['payload'].get('parts', [])
            for part in parts:
                if part.get('filename'):
                    attachment = {
                        'filename': part['filename'],
                        'mimeType': part['mimeType'],
                        'attachmentId': part['body'].get('attachmentId'),
                        'size': part['body'].get('size', 0)
                    }
                    
                    # Check if it's a supported file type
                    file_ext = os.path.splitext(part['filename'])[1].lower()[1:]
                    if file_ext in settings.allowed_extensions:
                        email_data['attachments'].append(attachment)
            
            return email_data
            
        except HttpError as error:
            logger.error(f"Failed to get email: {error}")
            return None
    
    def download_attachment(self, message_id: str, attachment_id: str, filename: str) -> Optional[str]:
        """Download attachment and save to uploads folder"""
        try:
            service = self._get_service()
            
            attachment = service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()
            
            file_data = base64.urlsafe_b64decode(attachment['data'])
            
            # Create uploads directory if it doesn't exist
            os.makedirs(settings.upload_folder, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{filename}"
            file_path = os.path.join(settings.upload_folder, safe_filename)
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"Downloaded attachment: {safe_filename}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to download attachment: {e}")
            return None
    
    def mark_as_processed(self, message_id: str) -> bool:
        """Mark email as processed by adding a label"""
        try:
            service = self._get_service()
            
            # Create or get the "Processed" label
            label_name = "AccountantAI/Processed"
            label_id = self._get_or_create_label(label_name)
            
            # Add label to message
            service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark email as processed: {e}")
            return False
    
    def _get_or_create_label(self, label_name: str) -> str:
        """Get or create a Gmail label"""
        service = self._get_service()
        
        # List existing labels
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])
        
        # Check if label exists
        for label in labels:
            if label['name'] == label_name:
                return label['id']
        
        # Create new label
        label_object = {
            'name': label_name,
            'labelListVisibility': 'labelShow',
            'messageListVisibility': 'show'
        }
        
        created_label = service.users().labels().create(
            userId='me',
            body=label_object
        ).execute()
        
        return created_label['id']
    
    def process_receipt_emails(self) -> int:
        """Process all unprocessed receipt emails"""
        db = SessionLocal()
        processed_count = 0
        
        try:
            # Search for receipt emails
            messages = self.search_receipt_emails()
            
            for msg in messages:
                # Check if already processed
                existing = db.query(Receipt).filter_by(
                    email_id=msg['id'],
                    source='email'
                ).first()
                
                if existing:
                    continue
                
                # Get email details
                email_data = self.get_email_with_attachments(msg['id'])
                if not email_data or not email_data.get('attachments'):
                    continue
                
                # Process each attachment
                for attachment in email_data['attachments']:
                    # Download attachment
                    file_path = self.download_attachment(
                        msg['id'],
                        attachment['attachmentId'],
                        attachment['filename']
                    )
                    
                    if file_path:
                        # Create receipt record
                        receipt = Receipt(
                            source='email',
                            email_id=msg['id'],
                            file_path=file_path,
                            original_filename=attachment['filename'],
                            status='pending'
                        )
                        db.add(receipt)
                        processed_count += 1
                
                # Mark email as processed
                self.mark_as_processed(msg['id'])
            
            db.commit()
            logger.info(f"Processed {processed_count} new receipts from email")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error processing receipt emails: {e}")
            db.rollback()
            return 0
            
        finally:
            db.close()


# Singleton instance
gmail_service = GmailService()