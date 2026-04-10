"""
Gmail Polling Service - Servicio ligero que revisa Gmail periodicamente
y envia CVs al CV Evaluator automaticamente.
Alternativa a n8n que no requiere configuracion OAuth compleja.
"""
import os
import sys
import json
import time
import tempfile
import logging
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Configuracion desde variables de entorno
GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "/app/gmail-credentials.json")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))  # segundos
CV_EVALUATOR_URL = os.getenv("CV_EVALUATOR_URL", "http://cv-evaluator:8000")
CV_API_KEY = os.getenv("CV_API_KEY", "")
STATE_FILE = os.getenv("STATE_FILE", "/app/gmail-state.json")
SEEN_DAYS = int(os.getenv("SEEN_DAYS", "7"))

# Keywords para identificar emails con CVs
CV_KEYWORDS = ["cv", "curriculum", "curriculum vitae", "hoja de vida", "resume",
               "candidato", "aplicacion", "postulacion", "oferta de empleo"]

CV_EXTENSIONS = [".pdf", ".docx", ".doc", ".txt"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("gmail-poller")


class SimpleGmailPoller:
    """
    Poller simple que usa la API de Gmail con un token de servicio (Service Account)
    o un token de OAuth pre-configurado.
    """
    
    def __init__(self):
        self.credentials = None
        self.service = None
        self.seen_message_ids = self._load_state()
    
    def _load_state(self) -> set:
        """Carga IDs de mensajes ya procesados"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    return set(data.get("seen_ids", []))
        except Exception as e:
            logger.warning(f"Error cargando estado: {e}")
        return set()
    
    def _save_state(self):
        """Guarda IDs de mensajes procesados"""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({"seen_ids": list(self.seen_message_ids)}, f)
        except Exception as e:
            logger.warning(f"Error guardando estado: {e}")
    
    def authenticate(self):
        """
        Autentica con Gmail usando credenciales de Service Account
        o un token de OAuth pre-configurado.
        """
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        if not os.path.exists(GMAIL_CREDENTIALS_PATH):
            logger.error(f"Credenciales de Gmail no encontradas en {GMAIL_CREDENTIALS_PATH}")
            logger.info("Para obtener credenciales:")
            logger.info("1. Ve a https://console.cloud.google.com/")
            logger.info("2. Crea una Service Account")
            logger.info("3. Descarga la clave JSON y guardala como gmail-credentials.json")
            logger.info("4. Comparte tu inbox con el email de la service account")
            sys.exit(1)
        
        with open(GMAIL_CREDENTIALS_PATH) as f:
            cred_data = json.load(f)
        
        self.credentials = service_account.Credentials.from_service_account_file(
            GMAIL_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"]
        )
        
        self.service = build("gmail", "v1", credentials=self.credentials)
        logger.info("Autenticacion con Gmail exitosa")
    
    def search_new_cv_emails(self) -> List[Dict]:
        """Busca emails nuevos que probablemente contengan CVs"""
        if not self.service:
            return []
        
        date_from = (datetime.utcnow() - timedelta(days=SEEN_DAYS)).strftime("%Y/%m/%d")
        query = f"has:attachment after:{date_from}"
        
        try:
            results = self.service.users().messages().list(
                userId="me",
                q=query,
                maxResults=50
            ).execute()
            
            messages = results.get("messages", [])
            cv_emails = []
            
            for msg in messages:
                # Saltar ya procesados
                if msg["id"] in self.seen_message_ids:
                    continue
                
                msg_detail = self.service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ).execute()
                
                headers = {h["name"].lower(): h["value"] 
                          for h in msg_detail.get("payload", {}).get("headers", [])}
                subject = headers.get("subject", "").lower()
                
                # Verificar keywords de CV
                if any(kw in subject for kw in CV_KEYWORDS):
                    cv_emails.append({
                        "id": msg["id"],
                        "from": headers.get("from", ""),
                        "subject": headers.get("subject", ""),
                        "date": headers.get("date", "")
                    })
            
            return cv_emails
            
        except Exception as e:
            logger.error(f"Error buscando emails: {e}")
            return []
    
    def get_attachments(self, message_id: str) -> List[Dict]:
        """Obtiene los adjuntos de un mensaje"""
        if not self.service:
            return []
        
        attachments = []
        try:
            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()
            
            parts = self._get_parts(message.get("payload", {}))
            
            for part in parts:
                filename = part.get("filename", "")
                attachment_id = part.get("body", {}).get("attachmentId")
                
                if not attachment_id or not filename:
                    continue
                
                ext = os.path.splitext(filename)[1].lower()
                if ext not in CV_EXTENSIONS:
                    continue
                
                try:
                    attachment = self.service.users().messages().attachments().get(
                        userId="me",
                        messageId=message_id,
                        id=attachment_id
                    ).execute()
                    
                    import base64
                    file_data = attachment.get("data", "")
                    if file_data:
                        file_bytes = base64.urlsafe_b64decode(file_data)
                        attachments.append({
                            "filename": filename,
                            "data": file_bytes
                        })
                except Exception as e:
                    logger.error(f"Error descargando adjunto: {e}")
            
        except Exception as e:
            logger.error(f"Error obteniendo mensaje: {e}")
        
        return attachments
    
    def _get_parts(self, payload: Dict) -> List[Dict]:
        """Recursivamente obtiene partes de un mensaje"""
        parts = []
        if "parts" in payload:
            for part in payload["parts"]:
                parts.append(part)
                parts.extend(self._get_parts(part))
        return parts
    
    def send_to_evaluator(self, attachment: Dict, from_email: str) -> bool:
        """Envia un adjunto al CV Evaluator"""
        try:
            url = f"{CV_EVALUATOR_URL}/api/candidates/upload"
            headers = {}
            if CV_API_KEY:
                headers["X-API-Key"] = CV_API_KEY
            
            with tempfile.NamedTemporaryFile(
                suffix=os.path.splitext(attachment["filename"])[1],
                delete=False
            ) as tmp:
                tmp.write(attachment["data"])
                tmp_path = tmp.name
            
            try:
                with open(tmp_path, "rb") as f:
                    files = {"file": (attachment["filename"], f, "application/octet-stream")}
                    response = httpx.post(
                        url,
                        headers=headers,
                        files=files,
                        params={"email": from_email},
                        timeout=120
                    )
                
                if response.status_code == 200:
                    logger.info(f"✓ CV enviado: {attachment['filename']} de {from_email}")
                    return True
                else:
                    logger.error(f"✗ Error enviando CV: {response.status_code} - {response.text}")
                    return False
            finally:
                os.unlink(tmp_path)
                
        except Exception as e:
            logger.error(f"Error enviando a evaluator: {e}")
            return False
    
    def poll_once(self) -> int:
        """Ejecuta un ciclo de polling"""
        emails = self.search_new_cv_emails()
        
        if not emails:
            logger.info("No hay nuevos emails con CVs")
            return 0
        
        logger.info(f"Encontrados {len(emails)} nuevos emails con CVs")
        
        processed = 0
        for email in emails:
            attachments = self.get_attachments(email["id"])
            for attachment in attachments:
                if self.send_to_evaluator(attachment, email["from"]):
                    processed += 1
                    self.seen_message_ids.add(email["id"])
            
            # Limitar tamaño del set de vistos
            if len(self.seen_message_ids) > 1000:
                self.seen_message_ids = set(list(self.seen_message_ids)[-500:])
        
        self._save_state()
        return processed
    
    def run(self):
        """Loop principal"""
        logger.info(f"Iniciando Gmail Poller (intervalo: {POLL_INTERVAL}s)")
        logger.info(f"CV Evaluator URL: {CV_EVALUATOR_URL}")
        
        while True:
            try:
                processed = self.poll_once()
                if processed > 0:
                    logger.info(f"Procesados {processed} CVs en este ciclo")
            except Exception as e:
                logger.error(f"Error en ciclo de polling: {e}")
            
            time.sleep(POLL_INTERVAL)


def main():
    poller = SimpleGmailPoller()
    poller.authenticate()
    poller.run()


if __name__ == "__main__":
    main()
