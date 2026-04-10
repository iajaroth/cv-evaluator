"""
n8n Setup Script - Configura credenciales y workflows automaticamente
Uso: python n8n_setup.py
"""
import os
import json
import sys
import time
import httpx
from typing import Optional

# ============================================
# Configuracion
# ============================================
# n8n URL (interna desde la red de Coolify)
N8N_URL = os.getenv("N8N_URL", "http://n8n:5678")
# n8n API key (se genera desde la UI de n8n la primera vez)
N8N_API_KEY = os.getenv("N8N_API_KEY", "")

# CV Evaluator
CV_EVALUATOR_URL = os.getenv("CV_EVALUATOR_URL", "http://cv-evaluator:8000")
CV_API_KEY = os.getenv("CV_API_KEY", "cv-eval-k3y-s3cur3-2026-automate")


class N8nSetup:
    """Configura n8n con credenciales y workflows"""
    
    def __init__(self):
        if not N8N_API_KEY:
            print("⚠ N8N_API_KEY no configurada")
            print("  Para obtenerla:")
            print("  1. Abre n8n en tu navegador (necesitas exponerlo temporalmente)")
            print("  2. Ve a Settings > API > Generate API Key")
            print("  3. Copia la key y exportala como N8N_API_KEY")
            print()
            print("  URL temporal de n8n (genera un FQDN publico en Coolify):")
            print(f"  {N8N_URL}")
            sys.exit(1)
        
        self.base_url = N8N_URL.rstrip('/')
        self.headers = {
            "X-N8N-API-KEY": N8N_API_KEY,
            "Content-Type": "application/json"
        }
    
    def _get(self, endpoint: str) -> dict:
        url = f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"
        response = httpx.get(url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def _post(self, endpoint: str, data: dict) -> dict:
        url = f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"
        response = httpx.post(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def _put(self, endpoint: str, data: dict) -> dict:
        url = f"{self.base_url}/api/v1/{endpoint.lstrip('/')}"
        response = httpx.put(url, headers=self.headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def check_connection(self) -> bool:
        """Verifica que puede conectarse a n8n"""
        try:
            response = httpx.get(f"{self.base_url}/healthz", timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"✗ No se pudo conectar a n8n: {e}")
            return False
    
    def list_credentials(self) -> list:
        """Lista credenciales existentes"""
        try:
            return self._get("credentials")
        except Exception as e:
            print(f"Error listando credenciales: {e}")
            return []
    
    def create_credential(self, name: str, type: str, data: dict) -> str:
        """Crea una credencial en n8n"""
        credential_data = {
            "name": name,
            "type": type,
            "data": data
        }
        
        try:
            result = self._post("credentials", credential_data)
            print(f"✓ Credencial creada: {name}")
            return result.get("id", "")
        except Exception as e:
            print(f"✗ Error creando credencial {name}: {e}")
            return ""
    
    def create_gmail_credential(self, client_id: str, client_secret: str, 
                                 refresh_token: str) -> str:
        """Crea credencial de Gmail OAuth2"""
        return self.create_credential(
            name="Gmail Account - CV Evaluator",
            type="gmailOAuth2",
            data={
                "clientId": client_id,
                "clientSecret": client_secret,
                "refreshToken": refresh_token
            }
        )
    
    def create_header_auth_credential(self, name: str, header_name: str, 
                                        header_value: str) -> str:
        """Crea credencial de Header Auth para HTTP Request"""
        return self.create_credential(
            name=name,
            type="httpHeaderAuth",
            data={
                "name": header_name,
                "value": header_value
            }
        )
    
    def create_workflow(self, workflow_data: dict) -> str:
        """Crea un workflow desde su definicion JSON"""
        try:
            result = self._post("workflows", workflow_data)
            workflow_id = result.get("id", "")
            print(f"✓ Workflow creado: {result.get('name', 'Sin nombre')}")
            return workflow_id
        except Exception as e:
            print(f"✗ Error creando workflow: {e}")
            return ""
    
    def activate_workflow(self, workflow_id: str) -> bool:
        """Activa un workflow"""
        try:
            self._put(f"workflows/{workflow_id}/activate", {"active": True})
            print(f"✓ Workflow activado: {workflow_id}")
            return True
        except Exception as e:
            print(f"✗ Error activando workflow: {e}")
            return False
    
    def setup_cv_evaluator_workflow(self) -> bool:
        """
        Crea el workflow completo de CV Evaluator
        """
        print("\n=== Creando workflow de CV Evaluator ===\n")
        
        workflow_json = {
            "name": "CV Evaluator - Gmail to CV Evaluator",
            "nodes": [
                {
                    "parameters": {
                        "pollTimes": {
                            "item": [
                                {
                                    "mode": "everyMinute"
                                }
                            ]
                        },
                        "triggerOn": "message",
                        "options": {
                            "downloadAttachments": True
                        }
                    },
                    "id": "gmail-trigger",
                    "name": "Gmail Trigger",
                    "type": "n8n-nodes-base.gmailTrigger",
                    "typeVersion": 1,
                    "position": [240, 300],
                    "credentials": {
                        "gmailOAuth2": {
                            "id": "__GMAIL_CRED_ID__",
                            "name": "Gmail Account - CV Evaluator"
                        }
                    }
                },
                {
                    "parameters": {
                        "conditions": {
                            "options": {
                                "caseSensitive": False,
                                "leftValue": "",
                                "typeValidation": "strict",
                                "version": 2
                            },
                            "conditions": [
                                {
                                    "id": "cond1",
                                    "leftValue": "={{ $json.headers.subject.toLowerCase() }}",
                                    "rightValue": "cv",
                                    "operator": {
                                        "type": "string",
                                        "operation": "contains"
                                    }
                                },
                                {
                                    "id": "cond2",
                                    "leftValue": "={{ $json.headers.subject.toLowerCase() }}",
                                    "rightValue": "curriculum",
                                    "operator": {
                                        "type": "string",
                                        "operation": "contains"
                                    }
                                },
                                {
                                    "id": "cond3",
                                    "leftValue": "={{ $json.headers.subject.toLowerCase() }}",
                                    "rightValue": "hoja de vida",
                                    "operator": {
                                        "type": "string",
                                        "operation": "contains"
                                    }
                                },
                                {
                                    "id": "cond4",
                                    "leftValue": "={{ $json.headers.subject.toLowerCase() }}",
                                    "rightValue": "resume",
                                    "operator": {
                                        "type": "string",
                                        "operation": "contains"
                                    }
                                }
                            ],
                            "combinator": "or"
                        },
                        "options": {}
                    },
                    "id": "filter-cv",
                    "name": "Filtrar emails de CV",
                    "type": "n8n-nodes-base.filter",
                    "typeVersion": 2,
                    "position": [460, 300]
                },
                {
                    "parameters": {
                        "method": "POST",
                        "url": f"{CV_EVALUATOR_URL}/api/candidates/upload",
                        "authentication": "genericCredentialType",
                        "genericAuthType": "httpHeaderAuth",
                        "sendBody": True,
                        "contentType": "multipart-form-data",
                        "bodyParameters": {
                            "parameters": [
                                {
                                    "parameterType": "formBinaryData",
                                    "name": "file",
                                    "inputDataFieldName": "data"
                                }
                            ]
                        },
                        "sendQuery": True,
                        "queryParameters": {
                            "parameters": [
                                {
                                    "name": "email",
                                    "value": "={{ $json.headers.from }}"
                                }
                            ]
                        },
                        "options": {}
                    },
                    "id": "upload-cv",
                    "name": "Enviar a CV Evaluator",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [680, 300],
                    "credentials": {
                        "httpHeaderAuth": {
                            "id": "__HEADER_AUTH_ID__",
                            "name": "CV Evaluator API Key"
                        }
                    }
                },
                {
                    "parameters": {
                        "fieldToSplitOut": "attachments",
                        "options": {}
                    },
                    "id": "split-attachments",
                    "name": "Separar Adjuntos",
                    "type": "n8n-nodes-base.splitOut",
                    "typeVersion": 1,
                    "position": [570, 300]
                }
            ],
            "connections": {
                "Gmail Trigger": {
                    "main": [
                        [
                            {
                                "node": "Filtrar emails de CV",
                                "type": "main",
                                "index": 0
                            }
                        ]
                    ]
                },
                "Filtrar emails de CV": {
                    "main": [
                        [
                            {
                                "node": "Separar Adjuntos",
                                "type": "main",
                                "index": 0
                            }
                        ]
                    ]
                },
                "Separar Adjuntos": {
                    "main": [
                        [
                            {
                                "node": "Enviar a CV Evaluator",
                                "type": "main",
                                "index": 0
                            }
                        ]
                    ]
                }
            },
            "pinData": {},
            "settings": {
                "executionOrder": "v1",
                "saveManualExecutions": True,
                "saveDataErrorExecution": "all",
                "saveDataSuccessExecution": "all",
                "saveExecutionProgress": True,
                "executionTimeout": 300
            },
            "staticData": None,
            "tags": [
                {
                    "name": "cv-evaluator"
                }
            ],
            "triggerCount": 1,
            "active": False,
            "versionId": "1"
        }
        
        workflow_id = self.create_workflow(workflow_json)
        return bool(workflow_id)
    
    def setup(self, gmail_client_id: str, gmail_client_secret: str, 
              gmail_refresh_token: str) -> bool:
        """
        Setup completo de n8n para CV Evaluator
        """
        print("=" * 60)
        print("  n8n Setup - CV Evaluator Integration")
        print("=" * 60)
        
        # 1. Verificar conexion
        print("\n1. Verificando conexion a n8n...")
        if not self.check_connection():
            print("✗ No se pudo conectar a n8n")
            return False
        print("✓ Conexion exitosa")
        
        # 2. Crear credencial de Gmail
        print("\n2. Creando credencial de Gmail...")
        gmail_cred_id = self.create_gmail_credential(
            gmail_client_id, gmail_client_secret, gmail_refresh_token
        )
        if not gmail_cred_id:
            return False
        
        # 3. Crear credencial de Header Auth para CV Evaluator
        print("\n3. Creando credencial de API Key...")
        header_auth_id = self.create_header_auth_credential(
            name="CV Evaluator API Key",
            header_name="X-API-Key",
            header_value=CV_API_KEY
        )
        if not header_auth_id:
            return False
        
        # 4. Crear workflow
        print("\n4. Creando workflow...")
        
        # Leer el workflow template
        workflow_path = os.path.join(os.path.dirname(__file__), "cv-evaluator-workflow.json")
        if os.path.exists(workflow_path):
            with open(workflow_path) as f:
                workflow_data = json.load(f)
        else:
            print("✗ Workflow template no encontrado")
            return False
        
        workflow_id = self.create_workflow(workflow_data)
        if not workflow_id:
            return False
        
        # 5. Activar workflow
        print("\n5. Activando workflow...")
        if self.activate_workflow(workflow_id):
            print("\n" + "=" * 60)
            print("  ✓ Setup completado exitosamente!")
            print("=" * 60)
            print(f"\n  Workflow ID: {workflow_id}")
            print(f"  Gmail Credential ID: {gmail_cred_id}")
            print(f"  Header Auth Credential ID: {header_auth_id}")
            print("\n  El workflow revisara Gmail cada minuto buscando CVs.")
            print("  Cuando encuentre un email con adjunto y asunto de CV,")
            print("  lo enviara automaticamente al CV Evaluator.")
            return True
        
        return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="n8n Setup para CV Evaluator")
    parser.add_argument("--check", action="store_true", help="Solo verificar conexion")
    parser.add_argument("--gmail-client-id", help="Gmail OAuth2 Client ID")
    parser.add_argument("--gmail-client-secret", help="Gmail OAuth2 Client Secret")
    parser.add_argument("--gmail-refresh-token", help="Gmail OAuth2 Refresh Token")
    parser.add_argument("--api-key", help="n8n API Key")
    args = parser.parse_args()
    
    if args.api_key:
        os.environ["N8N_API_KEY"] = args.api_key
    
    setup = N8nSetup()
    
    if args.check:
        if setup.check_connection():
            print("✓ n8n accessible")
        else:
            print("✗ n8n no accessible")
        return
    
    if not all([args.gmail_client_id, args.gmail_client_secret, args.gmail_refresh_token]):
        print("Error: Se necesitan las credenciales de Gmail OAuth2")
        print("Uso:")
        print("  python n8n_setup.py \\")
        print("    --api-key TU_N8N_API_KEY \\")
        print("    --gmail-client-id CLIENT_ID \\")
        print("    --gmail-client-secret CLIENT_SECRET \\")
        print("    --gmail-refresh-token REFRESH_TOKEN")
        return
    
    success = setup.setup(
        args.gmail_client_id,
        args.gmail_client_secret,
        args.gmail_refresh_token
    )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
