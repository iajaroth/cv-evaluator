#!/bin/bash
# deploy.sh - Script de despliegue automatico del CV Evaluator
# Uso: ./deploy.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  CV Evaluator - Deploy Script"
echo "=========================================="
echo ""

# Verificar .env
if [ ! -f "$PARENT_DIR/.env" ]; then
    echo "✗ Error: No se encontro .env en $PARENT_DIR"
    exit 1
fi

# Cargar variables de entorno
source "$PARENT_DIR/.env"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "✗ Error: GITHUB_TOKEN no configurado en .env"
    exit 1
fi

if [ -z "$COOLIFY_URL" ]; then
    echo "✗ Error: COOLIFY_URL no configurado en .env"
    exit 1
fi

echo "✓ Variables de entorno cargadas"
echo ""

# Paso 1: Crear repo y subir codigo
echo "=== Paso 1: Crear repo privado en GitHub ==="
cd "$SCRIPT_DIR"
python3 execution/github_manager.py full-setup \
    --repo cv-evaluator \
    --path "$SCRIPT_DIR" \
    --description "Sistema automatico de evaluacion de candidatos para tecnico en electronica"

echo ""
echo "=== Paso 1 completado ==="
echo ""

# Paso 2: Configurar y desplegar en Coolify
echo "=== Paso 2: Desplegar en Coolify ==="

# Obtener el username de GitHub para el repo
GITHUB_USER=$(python3 -c "
import httpx, os
from dotenv import load_dotenv
load_dotenv('$PARENT_DIR/.env')
r = httpx.get('https://api.github.com/user', headers={'Authorization': f\"Bearer {os.getenv('GITHUB_TOKEN')}\"})
print(r.json()['login'])
")

REPO_FULL="$GITHUB_USER/cv-evaluator"

echo "Repo: $REPO_FULL"

# Verificar si OPENAI_API_KEY esta configurada
if [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "⚠ Warning: OPENAI_API_KEY no configurada en .env"
    echo "   El sistema no podra evaluar CVs sin esta key."
    echo "   Puedes agregarla despues en Coolify > Environment Variables"
    echo ""
    read -p "¿Deseas continuar sin OPENAI_API_KEY? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Preparar env vars para Coolify
ENV_VARS_JSON="{"
if [ -n "$OPENAI_API_KEY" ]; then
    ENV_VARS_JSON+="\"OPENAI_API_KEY\":\"$OPENAI_API_KEY\","
fi
# Generar API key si no existe
if [ -z "$SERVICE_API_KEY" ]; then
    GENERATED_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    ENV_VARS_JSON+="\"SERVICE_API_KEY\":\"$GENERATED_KEY\","
    echo "✓ SERVICE_API_KEY generada: $GENERATED_KEY"
    echo "  Guardala, la necesitaras para acceder a la API"
else
    ENV_VARS_JSON+="\"SERVICE_API_KEY\":\"$SERVICE_API_KEY\","
fi
ENV_VARS_JSON+="\"DATABASE_URL\":\"sqlite:///./candidates.db\","
ENV_VARS_JSON+="\"UPLOAD_DIR\":\"/app/uploads\""
ENV_VARS_JSON+="}"

echo ""
echo "Enviando variables de entorno a Coolify..."

python3 execution/coolify_manager.py full-deploy \
    --repo "$REPO_FULL" \
    --branch main \
    --alias cv-evaluator \
    --env-vars "$ENV_VARS_JSON"

echo ""
echo "=========================================="
echo "  ✓ Deploy completado"
echo "=========================================="
echo ""
echo "Proximos pasos:"
echo "1. Esperar ~90 segundos a que el deploy termine"
echo "2. Verificar en Coolify que el healthcheck este 'healthy'"
echo "3. Configurar Gmail integration (ver instrucciones en directives/README.md)"
echo "4. Acceder al panel via la red interna de Coolify"
echo ""
