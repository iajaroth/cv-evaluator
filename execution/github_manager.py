"""
GitHub Manager - Crea repos privados y vincula GitHub App de Coolify
"""
import os
import sys
import json
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# GitHub API base
GITHUB_API = "https://api.github.com"


class GitHubManager:
    """Gestiona repositorios en GitHub"""
    
    def __init__(self):
        if not GITHUB_TOKEN:
            raise ValueError("GITHUB_TOKEN no configurado en .env")
        
        self.headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    
    def create_private_repo(self, name: str, description: str = "") -> bool:
        """Crea un repositorio privado"""
        print(f"Creando repositorio privado: {name}")
        
        data = {
            "name": name,
            "description": description,
            "private": True,
            "auto_init": False,
            "delete_branch_on_merge": True
        }
        
        response = httpx.post(
            f"{GITHUB_API}/user/repos",
            headers=self.headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 201:
            repo_data = response.json()
            print(f"✓ Repositorio creado: {repo_data['html_url']}")
            return True
        else:
            print(f"✗ Error creando repo: {response.status_code}")
            print(response.text)
            return False
    
    def grant_github_app_access(self, repo_name: str) -> bool:
        """
        Vincula la GitHub App de Coolify al repositorio.
        Requiere que el usuario haya instalado la GitHub App en Coolify con 'All repositories'.
        """
        print(f"Vinculando GitHub App de Coolify a {repo_name}...")
        
        # Obtener la instalacion de la GitHub App
        try:
            response = httpx.get(
                f"{GITHUB_API}/user/installations",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"Error obteniendo instalaciones: {response.status_code}")
                return False
            
            installations = response.json().get("installations", [])
            
            if not installations:
                print("No se encontraron GitHub Apps instaladas")
                print("El usuario debe crear la GitHub App en Coolify primero")
                return False
            
            # Usar la primera instalacion (Coolify)
            installation_id = installations[0]["id"]
            print(f"  - Instalacion encontrada: {installation_id}")
            
            # Verificar permisos del repo
            repos_response = httpx.get(
                f"{GITHUB_API}/user/installations/{installation_id}/repositories",
                headers=self.headers,
                timeout=30
            )
            
            if repos_response.status_code == 200:
                repos = repos_response.json().get("repositories", [])
                repo_names = [r["full_name"] for r in repos]
                
                if repo_name in repo_names:
                    print(f"✓ GitHub App ya tiene acceso a {repo_name}")
                    return True
                else:
                    print(f"Warning: {repo_name} no esta en la lista de repos de la GitHub App")
                    print("Asegurate de que la GitHub App tenga permisos 'All repositories'")
            
            return True
            
        except Exception as e:
            print(f"Error vinculando GitHub App: {e}")
            return False
    
    def initialize_and_push(self, local_path: str, repo_name: str, branch: str = "main") -> bool:
        """Inicializa un repo local y sube el codigo"""
        import subprocess
        
        full_repo = f"git@github.com:{repo_name}.git"
        print(f"Inicializando y subiendo codigo a {full_repo}...")
        
        commands = [
            f'cd {local_path} && git init',
            f'cd {local_path} && git checkout -b {branch}',
            f'cd {local_path} && git add .',
            f'cd {local_path} && git commit -m "Initial commit: CV Evaluator system"',
            f'cd {local_path} && git remote add origin {full_repo}',
            f'cd {local_path} && git push -u origin {branch}'
        ]
        
        for cmd in commands:
            print(f"  Ejecutando: {cmd.split('&&')[-1].strip()}")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"  ✗ Error: {result.stderr}")
                return False
        
        print(f"✓ Codigo subido a {full_repo}")
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="GitHub Manager")
    parser.add_argument("command", choices=["create", "grant", "push", "full-setup"])
    parser.add_argument("--repo", help="Nombre del repo (ej: cv-evaluator)")
    parser.add_argument("--path", help="Ruta local del proyecto")
    parser.add_argument("--description", default="CV Evaluator System")
    args = parser.parse_args()
    
    manager = GitHubManager()
    
    if args.command == "create":
        if not args.repo:
            print("Error: --repo es requerido")
            sys.exit(1)
        success = manager.create_private_repo(args.repo, args.description)
        sys.exit(0 if success else 1)
    
    elif args.command == "grant":
        if not args.repo:
            print("Error: --repo es requerido")
            sys.exit(1)
        success = manager.grant_github_app_access(args.repo)
        sys.exit(0 if success else 1)
    
    elif args.command == "push":
        if not args.repo or not args.path:
            print("Error: --repo y --path son requeridos")
            sys.exit(1)
        success = manager.initialize_and_push(args.path, args.repo)
        sys.exit(0 if success else 1)
    
    elif args.command == "full-setup":
        """Crea repo, vincula GitHub App y sube codigo"""
        if not args.repo or not args.path:
            print("Error: --repo y --path son requeridos")
            sys.exit(1)
        
        # Obtener username de GitHub
        response = httpx.get(f"{GITHUB_API}/user", headers=manager.headers)
        if response.status_code != 200:
            print("Error obteniendo usuario de GitHub")
            sys.exit(1)
        
        github_user = response.json()["login"]
        full_repo = f"{github_user}/{args.repo}"
        
        print(f"=== Full Setup para {full_repo} ===")
        
        # 1. Crear repo
        if not manager.create_private_repo(args.repo, args.description):
            sys.exit(1)
        
        # 2. Vincular GitHub App
        manager.grant_github_app_access(full_repo)
        
        # 3. Subir codigo
        success = manager.initialize_and_push(args.path, full_repo)
        
        if success:
            print(f"\n✓ Setup completado!")
            print(f"  Repo: https://github.com/{full_repo}")
            print(f"  Para Coolify usa: {full_repo}")
        
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
