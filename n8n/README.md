# n8n Integration - CV Evaluator

## Opcion 1: Workflow Manual en n8n (Recomendado)

### Paso 1: Exponer n8n temporalmente

1. Ve a tu panel de Coolify: https://coolify.automate-n8n.online
2. Abre el servicio **N8N**
3. En **Domains**, agrega un FQDN temporal (ej: `n8n.automate-n8n.online`)
4. Guarda y espera el deploy
5. Abre n8n en tu navegador: `https://n8n.automate-n8n.online`

### Paso 2: Generar API Key en n8n

1. En n8n, ve a **Settings** (icono engranaje, esquina inferior izquierda)
2. Ve a **API**
3. Click en **Generate API Key**
4. Copia la key y guardala

### Paso 3: Configurar credencial de Gmail en n8n

#### 3a. Crear OAuth credentials en Google Cloud

1. Ve a https://console.cloud.google.com/
2. Selecciona tu proyecto (o crea uno nuevo)
3. Ve a **APIs & Services** > **Credentials**
4. Click **Create Credentials** > **OAuth client ID**
5. Si es la primera vez, configura el **OAuth consent screen**:
   - User Type: **External**
   - App name: `CV Evaluator Gmail`
   - User support email: tu email
   - Developer contact: tu email
   - Scopes: agrega `https://www.googleapis.com/auth/gmail.readonly`
   - Test users: agrega tu email de Gmail
6. De vuelta a crear OAuth client ID:
   - Application type: **Desktop app**
   - Name: `CV Evaluator`
   - Click **Create**
7. Descarga el JSON de credenciales

#### 3b. Conectar Gmail en n8n

1. En n8n, ve a **Credentials** > **Add Credential**
2. Busca **Gmail OAuth2**
3. Name: `Gmail Account - CV Evaluator`
4. Click en **Sign in with Google**
5. Sigue el flujo de OAuth (inicia sesion con tu cuenta de Gmail y acepta los permisos)
6. Guarda la credencial

### Paso 4: Crear el workflow

#### 4a. Importar workflow

1. En n8n, click en los **3 puntos** (menu superior derecho) > **Import from File**
2. Selecciona el archivo: `cv-evaluator/cv-evaluator-workflow.json`

#### 4b. Configurar nodos

**Nodo "Gmail Trigger":**
- Selecciona la credencial `Gmail Account - CV Evaluator` que creaste
- Poll Times: **Every minute**
- Trigger On: **message**
- Options: **Download Attachments** = true

**Nodo "Filtrar emails de CV":**
- Ya viene configurado con las keywords: cv, curriculum, hoja de vida, resume

**Nodo "Separar Adjuntos":**
- Field to Split Out: `attachments`

**Nodo "Enviar a CV Evaluator":**
- Method: **POST**
- URL: `http://cv-evaluator:8000/api/candidates/upload`
- Authentication: **Header Auth**
  - Create new credential:
    - Name: `CV Evaluator API Key`
    - Header Name: `X-API-Key`
    - Header Value: `cv-eval-k3y-s3cur3-2026-automate`
- Body: **multipart/form-data**
  - Parameter Type: **Form Binary Data**
  - Name: `file`
  - Input Data Field Name: `data`
- Query Parameters:
  - Name: `email`
  - Value: `{{ $json.headers.from }}`

#### 4c. Activar workflow

1. Click en el toggle **Active** (esquina superior derecha)
2. Guarda el workflow

### Paso 5: Probar

1. Enviate un email a ti mismo con un CV adjunto y asunto "CV - Tu Nombre"
2. En n8n, ve a **Executions** y verifica que el workflow se ejecuto
3. En el panel de CV Evaluator, verifica que el candidato aparecio

### Paso 6: Eliminar FQDN publico de n8n (seguridad)

Una vez configurado, elimina el FQDN publico de n8n en Coolify para que solo sea accesible desde la red interna.

---

## Opcion 2: Gmail Poller Service (Alternativa sin n8n)

Si prefieres no usar n8n, puedes ejecutar un servicio ligero de polling directamente.

### Requisitos:
- Credenciales de **Google Service Account** (no OAuth)

### Configuracion:

1. En Google Cloud Console, crea una **Service Account**:
   - IAM & Admin > Service Accounts > Create
   - Name: `cv-evaluator-gmail`
   - Grants: ninguna (no necesita roles)
   - Descarga la clave JSON

2. **Comparte tu inbox** con el email de la service account:
   - Abre Gmail con tu cuenta personal
   - Settings (engranaje) > See all settings
   - Accounts and Import > Grant access to your account
   - Agrega el email de la service account

3. Guarda la clave JSON como `/app/gmail-credentials.json` en el contenedor

4. Ejecuta el poller:
```bash
export GMAIL_CREDENTIALS_PATH=/app/gmail-credentials.json
export CV_EVALUATOR_URL=http://cv-evaluator:8000
export CV_API_KEY=cv-eval-k3y-s3cur3-2026-automate
export POLL_INTERVAL=60
python3 gmail_poller_service.py
```

---

## Variables de Entorno del Workflow

| Variable | Valor | Descripcion |
|----------|-------|-------------|
| `CV_EVALUATOR_URL` | `http://cv-evaluator:8000` | URL interna del servicio |
| `CV_API_KEY` | `cv-eval-k3y-s3cur3-2026-automate` | API Key del servicio |

---

## Troubleshooting

### El workflow no se ejecuta
- Verifica que el toggle **Active** este encendido
- Revisa los **Executions** para ver errores
- Verifica que la credencial de Gmail tenga permisos

### Error de autenticacion en HTTP Request
- Verifica que el Header Auth tenga:
  - Name: `X-API-Key`
  - Value: `cv-eval-k3y-s3cur3-2026-automate`

### El CV Evaluator no recibe el archivo
- Verifica que la URL sea `http://cv-evaluator:8000/api/candidates/upload` (red interna)
- El body debe ser `multipart/form-data` con campo `file` de tipo binary

### n8n no es accesible
- Verifica en Coolify que el servicio N8N este `running:healthy`
- Si eliminaste el FQDN publico, necesitas recrearlo temporalmente
