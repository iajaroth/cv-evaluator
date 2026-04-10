"""
Gmail Integration - Revisa correos y descarga CVs adjuntos
Se ejecuta periodicamente para buscar nuevos candidatos.
"""
import os
import base64
import tempfile
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httpx
import json

# Scopes necesarios
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Keywords para identificar emails con CVs
CV_KEYWORDS = [
    'cv', 'curriculum', 'curriculum vitae', 'hoja de vida', 'resume',
    'candidato', 'aplicacion', 'postulacion', 'oferta de empleo',
    'adjunto mi cv', 'mi curriculum', 'mi perfil', 'solicitud'
]

# Extensiones de archivos CV
CV_EXTENSIONS = ['.pdf', '.docx', '.doc', '.txt']


class GmailCVFetcher:
    """Cliente para revisar correos y descargar CVs adjuntos"""
    
    def __init__(self):
        self.creds = None
        self.service = None
        self.callback_url = os.getenv("CV_EVALUATOR_URL", "http://localhost:8000")
        self.api_key = os.getenv("SERVICE_API_KEY", "")
        
    def authenticate(self, token_path: str = "token.json", credentials_path: str = "credentials.json"):
        """
        Autentica con Gmail API.
        La primera vez abre un navegador para OAuth.
        """
        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not os.path.exists(credentials_path):
                    raise FileNotFoundError(
                        f"No se encontro {credentials_path}. "
                        "Descargalo de Google Cloud Console > APIs & Services > Credentials"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            # Guardar credenciales
            with open(token_path, 'w') as token:
                token.write(self.creds.to_json())
        
        self.service = build('gmail', 'v1', credentials=self.creds)
    
    def search_cv_emails(self, days_back: int = 7) -> List[Dict]:
        """Busca emails que probablemente contengan CVs"""
        if not self.service:
            raise RuntimeError("No autenticado. Llama a authenticate() primero")
        
        # Buscar emails con adjuntos en los ultimos dias
        date_from = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y/%m/%d')
        query = f"has:attachment after:{date_from}"
        
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=100
            ).execute()
            
            messages = results.get('messages', [])
            cv_emails = []
            
            for msg in messages:
                msg_detail = self.service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()
                
                headers = {h['name'].lower(): h['value'] for h in msg_detail.get('payload', {}).get('headers', [])}
                subject = headers.get('subject', '').lower()
                from_email = headers.get('from', '')
                
                # Verificar si el asunto contiene keywords de CV
                if any(kw in subject for kw in CV_KEYWORDS):
                    cv_emails.append({
                        'id': msg['id'],
                        'from': from_email,
                        'subject': headers.get('subject', ''),
                        'date': headers.get('date', '')
                    })
            
            return cv_emails
            
        except HttpError as error:
            print(f"Error buscando emails: {error}")
            return []
    
    def get_message_with_attachments(self, message_id: str) -> Dict:
        """Obtiene un email completo con sus adjuntos"""
        if not self.service:
            raise RuntimeError("No autenticado")
        
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            return message
        except HttpError as error:
            print(f"Error obteniendo mensaje: {error}")
            return None
    
    def extract_attachments(self, message: Dict) -> List[Dict]:
        """Extrae los archivos adjuntos de un mensaje"""
        if not self.service:
            raise RuntimeError("No autenticado")
        
        attachments = []
        parts = self._get_message_parts(message.get('payload', {}))
        
        for part in parts:
            filename = part.get('filename', '')
            mime_type = part.get('mimeType', '')
            body = part.get('body', {})
            attachment_id = body.get('attachmentId')
            
            if not attachment_id or not filename:
                continue
            
            # Verificar si es un archivo CV
            ext = os.path.splitext(filename)[1].lower()
            if ext not in CV_EXTENSIONS:
                continue
            
            try:
                attachment = self.service.users().messages().attachments().get(
                    userId='me',
                    messageId=message['id'],
                    id=attachment_id
                ).execute()
                
                file_data = attachment.get('data', '')
                if file_data:
                    file_bytes = base64.urlsafe_b64decode(file_data)
                    attachments.append({
                        'filename': filename,
                        'data': file_bytes,
                        'mime_type': mime_type
                    })
            
            except HttpError as error:
                print(f"Error descargando adjunto: {error}")
        
        return attachments
    
    def _get_message_parts(self, payload: Dict) -> List[Dict]:
        """Recursivamente obtiene todas las partes de un mensaje"""
        parts = []
        
        if 'parts' in payload:
            for part in payload['parts']:
                parts.append(part)
                parts.extend(self._get_message_parts(part))
        
        return parts
    
    def upload_to_evaluator(self, attachment: Dict, from_email: str) -> bool:
        """Sube un adjunto al sistema de evaluacion"""
        if not self.callback_url:
            print("CV_EVALUATOR_URL no configurada, saltando upload")
            return False
        
        url = f"{self.callback_url}/api/candidates/upload"
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        # Crear archivo temporal
        ext = os.path.splitext(attachment['filename'])[1].lower()
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(attachment['data'])
            tmp_path = tmp.name
        
        try:
            with open(tmp_path, 'rb') as f:
                files = {'file': (attachment['filename'], f, attachment['mime_type'])}
                response = httpx.post(
                    url,
                    headers=headers,
                    files=files,
                    params={'email': from_email},
                    timeout=60
                )
            
            if response.status_code == 200:
                print(f"CV subido exitosamente: {attachment['filename']} de {from_email}")
                return True
            else:
                print(f"Error subiendo CV: {response.status_code} - {response.text}")
                return False
        
        finally:
            os.unlink(tmp_path)
    
    def fetch_and_process(self, days_back: int = 7) -> int:
        """
        Flujo completo: busca emails, descarga adjuntos y los sube al evaluador
        Retorna el numero de CVs procesados
        """
        emails = self.search_cv_emails(days_back)
        print(f"Encontrados {len(emails)} emails potencialmente con CVs")
        
        processed = 0
        for email in emails:
            message = self.get_message_with_attachments(email['id'])
            if not message:
                continue
            
            attachments = self.extract_attachments(message)
            for attachment in attachments:
                if self.upload_to_evaluator(attachment, email['from']):
                    processed += 1
        
        return processed


def main():
    """Ejecucion standalone del fetcher"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Busca CVs en Gmail y los envia al evaluador")
    parser.add_argument('--days', type=int, default=7, help='Dias atras para buscar')
    parser.add_argument('--init-oauth', action='store_true', help='Inicia el flujo OAuth')
    args = parser.parse_args()
    
    fetcher = GmailCVFetcher()
    
    if args.init_oauth:
        print("Iniciando autenticacion OAuth con Gmail...")
        fetcher.authenticate()
        print("Autenticacion completada. Puedes ejecutar sin --init-oauth ahora.")
    else:
        fetcher.authenticate()
        processed = fetcher.fetch_and_process(args.days)
        print(f"Proceso completado. {processed} CVs procesados.")


if __name__ == "__main__":
    main()
