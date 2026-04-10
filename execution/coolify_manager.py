"""
Coolify Manager - Gestiona despliegues en Coolify via REST API
Uso: python coolify_manager.py <comando> [argumentos]
"""
import os
import sys
import json
import time
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

COOLIFY_URL = os.getenv("COOLIFY_URL", "https://coolify.automate-n8n.online")
COOLIFY_TOKEN = os.getenv("COOLIFY_TOKEN", "")
COOLIFY_PROJECT_UUID = os.getenv("COOLIFY_PROJECT_UUID", "")

# Timeout para deploys (segundos)
DEPLOY_TIMEOUT = 300  # 5 minutos


class CoolifyManager:
    """Gestiona aplicaciones en Coolify via REST API"""
    
    def __init__(self):
        if not COOLIFY_TOKEN:
            raise ValueError("COOLIFY_TOKEN no configurado en .env")
        if not COOLIFY_PROJECT_UUID:
            raise ValueError("COOLIFY_PROJECT_UUID no configurado en .env")
        
        self.base_url = COOLIFY_URL.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {COOLIFY_TOKEN}",
            "Content-Type": "application/json"
        }
        self.project_uuid = COOLIFY_PROJECT_UUID
    
    def _get(self, endpoint: str) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = httpx.get(url, headers=self.headers, timeout=60)
        response.raise_for_status()
        return response.json()
    
    def _post(self, endpoint: str, data: dict) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = httpx.post(url, headers=self.headers, json=data, timeout=60)
        response.raise_for_status()
        return response.json()
    
    def _patch(self, endpoint: str, data: dict) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = httpx.patch(url, headers=self.headers, json=data, timeout=60)
        response.raise_for_status()
        return response.json()
    
    def _delete(self, endpoint: str) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = httpx.delete(url, headers=self.headers, timeout=60)
        if response.status_code != 204:
            response.raise_for_status()
            return response.json()
        return {}
    
    def create_application(self, repo_owner: str, repo_name: str, branch: str = "main") -> str:
        """
        Crea una aplicacion desde un repo privado de GitHub.
        Retorna el UUID de la aplicacion.
        """
        print(f"Creando aplicacion desde {repo_owner}/{repo_name}...")
        
        data = {
            "project_uuid": self.project_uuid,
            "environment_name": "production",
            "github_app_uuid": "me",  # Usa la GitHub App por defecto
            "repository": f"{repo_owner}/{repo_name}",
            "branch": branch,
            "build_pack": "dockerfile",
            "is_static": False,
            "name": f"cv-evaluator",
            "description": "Sistema de evaluacion automatica de CVs"
        }
        
        result = self._post("/api/v1/applications/private-github-app", data)
        app_uuid = result.get("uuid")
        
        if not app_uuid:
            print(f"Respuesta de Creacion: {json.dumps(result, indent=2)}")
            raise ValueError("No se recibio el UUID de la aplicacion")
        
        print(f"Aplicacion creada: {app_uuid}")
        return app_uuid
    
    def configure_application(self, app_uuid: str, network_alias: str = "cv-evaluator"):
        """
        Configura la aplicacion:
        - Elimina FQDN publico
        - Configura red interna
        - Activa healthcheck
        """
        print(f"Configurando aplicacion {app_uuid}...")
        
        # 1. Eliminar FQDN publico (usar campo domains)
        print("  - Eliminando FQDN publico...")
        self._patch(f"/api/v1/applications/{app_uuid}", {"domains": ""})
        
        # 2. Configurar alias de red interna
        print(f"  - Configurando alias de red: {network_alias}")
        self._patch(f"/api/v1/applications/{app_uuid}", {"custom_network_aliases": network_alias})
        
        # 3. Configurar healthcheck
        print("  - Configurando healthcheck...")
        self._patch(f"/api/v1/applications/{app_uuid}", {
            "health_check_enabled": True,
            "health_check_path": "/health",
            "health_check_port": 8000,
            "health_check_host": "0.0.0.0"
        })
        
        # 4. Puerto interno
        print("  - Configurando puerto interno...")
        self._patch(f"/api/v1/applications/{app_uuid}", {"internal_port": 8000})
        
        print("Configuracion completada")
    
    def set_env_vars(self, app_uuid: str, env_vars: dict):
        """
        Establece variables de entorno.
        NOTA: Debido a limitaciones de la API, primero elimina variables existentes.
        """
        print(f"Configurando variables de entorno...")
        
        # Coolify no tiene endpoint facil para env vars en aplicaciones
        # Las env vars se pueden setear en el compose file o via UI
        # Por ahora, las agregamos al cuerpo del PATCH
        
        # Intentar PATCH directo
        for key, value in env_vars.items():
            try:
                self._patch(f"/api/v1/applications/{app_uuid}", {
                    "runtime_environment_variables": [
                        {"key": key, "value": value, "is_build_time": False}
                    ]
                })
                print(f"  - Variable {key} configurada")
            except Exception as e:
                print(f"  - Warning: No se pudo configurar {key}: {e}")
        
        print("Variables de entorno configuradas")
    
    def deploy_application(self, app_uuid: str, force: bool = True) -> bool:
        """Inicia el deploy de la aplicacion"""
        print(f"Iniciando deploy de {app_uuid}...")
        
        # Forzar deploy
        self._get(f"/api/v1/deploy?uuid={app_uuid}&force={'true' if force else 'false'}")
        
        print("Deploy iniciado, monitoreando estado...")
        return self._monitor_deploy(app_uuid)
    
    def _monitor_deploy(self, app_uuid: str) -> bool:
        """Monitorea el estado del deploy hasta que termine o timeout"""
        start_time = time.time()
        last_log_position = 0
        
        while time.time() - start_time < DEPLOY_TIMEOUT:
            try:
                # Verificar estado de recursos
                status = self._get(f"/api/v1/applications/{app_uuid}")
                deploy_status = status.get("status", "unknown")
                
                if deploy_status == "finished":
                    print("✓ Deploy completado exitosamente!")
                    return True
                
                if deploy_status == "failed":
                    print("✗ Deploy fallido")
                    return False
                
                # Obtener logs recientes
                try:
                    logs = self._get(f"/api/v1/logs?type=deploy&uuid={app_uuid}")
                    log_text = logs.get("logs", "")
                    
                    if len(log_text) > last_log_position:
                        new_logs = log_text[last_log_position:]
                        last_log_position = len(log_text)
                        
                        # Mostrar lineas importantes
                        for line in new_logs.split('\n')[-5:]:
                            if any(kw in line.lower() for kw in ['healthcheck', 'error', 'finished', 'deploy', 'roll']):
                                print(f"  {line.strip()}")
                
                except Exception:
                    pass
                
                time.sleep(10)
                
            except Exception as e:
                print(f"Error monitoreando: {e}")
                time.sleep(10)
        
        print(f"✗ Timeout de deploy despues de {DEPLOY_TIMEOUT}s")
        return False
    
    def get_application_status(self, app_uuid: str) -> dict:
        """Obtiene el estado actual de una aplicacion"""
        return self._get(f"/api/v1/applications/{app_uuid}")
    
    def list_applications(self) -> list:
        """Lista todas las aplicaciones del proyecto"""
        return self._get(f"/api/v1/projects/{self.project_uuid}/applications")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Coolify Manager")
    parser.add_argument("command", choices=[
        "create", "configure", "deploy", "status", "list", "full-deploy"
    ], help="Comando a ejecutar")
    parser.add_argument("--repo", help="Repo en formato owner/name")
    parser.add_argument("--branch", default="main", help="Branch del repo")
    parser.add_argument("--app-uuid", help="UUID de aplicacion existente")
    parser.add_argument("--alias", default="cv-evaluator", help="Alias de red")
    parser.add_argument("--env-vars", help="JSON de variables de entorno")
    args = parser.parse_args()
    
    manager = CoolifyManager()
    
    if args.command == "create":
        if not args.repo:
            print("Error: --repo es requerido para 'create'")
            sys.exit(1)
        owner, name = args.repo.split('/')
        uuid = manager.create_application(owner, name, args.branch)
        print(f"APP_UUID={uuid}")
    
    elif args.command == "configure":
        if not args.app_uuid:
            print("Error: --app-uuid es requerido para 'configure'")
            sys.exit(1)
        manager.configure_application(args.app_uuid, args.alias)
    
    elif args.command == "deploy":
        if not args.app_uuid:
            print("Error: --app-uuid es requerido para 'deploy'")
            sys.exit(1)
        success = manager.deploy_application(args.app_uuid)
        sys.exit(0 if success else 1)
    
    elif args.command == "status":
        if not args.app_uuid:
            print("Error: --app-uuid es requerido para 'status'")
            sys.exit(1)
        status = manager.get_application_status(args.app_uuid)
        print(json.dumps(status, indent=2))
    
    elif args.command == "list":
        apps = manager.list_applications()
        print(json.dumps(apps, indent=2))
    
    elif args.command == "full-deploy":
        """Crea, configura y despliega"""
        if not args.repo:
            print("Error: --repo es requerido para 'full-deploy'")
            sys.exit(1)
        
        owner, name = args.repo.split('/')
        uuid = manager.create_application(owner, name, args.branch)
        manager.configure_application(uuid, args.alias)
        
        if args.env_vars:
            env_vars = json.loads(args.env_vars)
            manager.set_env_vars(uuid, env_vars)
        
        success = manager.deploy_application(uuid)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
