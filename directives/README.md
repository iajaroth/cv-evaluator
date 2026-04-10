# CV Evaluator - Sistema Automatico de Evaluacion de Candidatos

## Descripcion

Sistema que automatiza la recepcion y evaluacion de CVs de candidatos para puestos de **tecnico en electronica**. Los candidatos llegan por correo electronico, son evaluados por IA (GPT-4o) y se muestran en un panel web con un score del 1 al 10.

## Arquitectura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│   Gmail     │────>│  Gmail       │────>│   FastAPI   │────>│  SQLite  │
│   (CVs)     │     │  Fetcher     │     │   API       │     │   DB     │
└─────────────┘     └──────────────┘     └──────┬──────┘     └──────────┘
                                                │
                                                v
                                         ┌─────────────┐
                                         │  OpenAI     │
                                         │  GPT-4o     │
                                         └─────────────┘
```

## Estructura del Proyecto

```
cv-evaluator/
├── main.py                 # FastAPI principal con endpoints y frontend
├── database.py             # Modelos SQLAlchemy (Candidate, Evaluation)
├── cv_parser.py            # Parser de CVs (DOCX, PDF, TXT)
├── ai_evaluator.py         # Motor de evaluacion con OpenAI GPT-4o
├── gmail_fetcher.py        # Integracion con Gmail para recibir CVs
├── Dockerfile              # Contenedor para despliegue
├── requirements.txt        # Dependencias Python
├── .env.example            # Plantilla de variables de entorno
└── directives/
    └── README.md           # Este archivo
```

## Endpoints

### Publicos
- `GET /` - Panel de visualizacion de candidatos (frontend)
- `GET /health` - Healthcheck

### API
- `POST /api/candidates/upload` - Sube un CV para evaluacion
  - Query params: `email` (opcional)
  - Body: multipart/form-data con campo `file`
  
- `GET /api/candidates` - Lista todos los candidatos con evaluaciones
- `GET /api/candidates/{id}` - Detalle de un candidato
- `DELETE /api/candidates/{id}` - Elimina un candidato
- `POST /api/candidates/{id}/re-evaluate` - Re-evalua un candidato

### Autenticacion
Si se configura `SERVICE_API_KEY`, todos los endpoints `/api/*` requieren el header:
```
X-API-Key: <tu-api-key>
```

## Criterios de Evaluacion IA

El sistema evalua los CVs basandose en:

| Criterio | Peso | Descripcion |
|----------|------|-------------|
| Formacion tecnica | 25% | Titulo/certificacion en electronica o areas relacionadas |
| Experiencia laboral | 30% | Experiencia comprobable como tecnico en electronica |
| Conocimientos tecnicos | 25% | Mantenimiento, diagnostico, instalacion de equipos |
| Estabilidad laboral | 10% | Permanencia en empleos anteriores |
| Presentacion del CV | 10% | Claridad y organizacion del documento |

### Reglas de Score
- **Score < 4**: Sin formacion tecnica en electronica o sin experiencia
- **Score 4-6.9**: Cumple parcialmente (formacion O experiencia, no ambos)
- **Score 7-10**: Cumple con formacion Y experiencia, con posible experiencia destacada

## Variables de Entorno

| Variable | Requerida | Descripcion |
|----------|-----------|-------------|
| `OPENAI_API_KEY` | **SI** | API key de OpenAI para GPT-4o |
| `SERVICE_API_KEY` | No | Key para proteger la API (se genera auto si no se provee) |
| `CV_EVALUATOR_URL` | No | URL del servicio para Gmail fetcher |
| `DATABASE_URL` | No | Connection string de BD (default: SQLite local) |
| `UPLOAD_DIR` | No | Directorio para archivos subidos (default: ./uploads) |

## Despliegue

### Local
```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
uvicorn main:app --reload
```

### Docker
```bash
docker build -t cv-evaluator .
docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... cv-evaluator
```

### Coolify
1. Crear repo privado en GitHub
2. Vincular GitHub App de Coolify
3. Crear aplicacion en Coolify desde repo
4. Configurar env vars (especialmente `OPENAI_API_KEY`)
5. Deploy

## Integracion con Gmail

### Opcion 1: Gmail Fetcher (cron)
Ejecutar periodicamente el `gmail_fetcher.py`:

```bash
# Primera vez: iniciar OAuth
python gmail_fetcher.py --init-oauth

# Luego ejecutar periodicamente (cron cada 30 min)
python gmail_fetcher.py --days 1
```

### Opcion 2: Gmail Forwarding + Webhook (Recomendado)
1. Crear regla en Gmail: emails con asunto que contenga "CV" o "curriculum" -> forward a `tu-servicio@api-domain.com`
2. Usar un servicio como Mailgun/SendGrid para recibir emails y hacer POST al endpoint `/api/candidates/upload`

### Opcion 3: n8n Integration
Crear workflow en n8n:
1. Trigger: Gmail node (watch emails with attachments)
2. Filter: Subject contains CV keywords
3. Action: HTTP Request -> POST to `/api/candidates/upload`

## Uso del Panel Web

1. Abrir `http://<tu-servicio>:8000/`
2. Ver estadisticas generales (total, scores altos/medios/bajos)
3. Filtrar candidatos por rango de score
4. Click en un candidato para ver detalle completo:
   - Score
   - Fortalezas y debilidades
   - Experiencia relevante
   - Habilidades tecnicas
   - Recomendacion de la IA

## API Docs para n8n

### Subir CV desde n8n

**Nodo HTTP Request:**
- **Method**: POST
- **URL**: `http://<alias-red-interna>:8000/api/candidates/upload?email={{$json.from}}`
- **Authentication**: None (si es red interna) o Header `X-API-Key`
- **Body**: multipart/form-data
  - Field: `file`
  - File: `{{$json.attachment}}`

### Obtener lista de candidatos

**Nodo HTTP Request:**
- **Method**: GET
- **URL**: `http://<alias-red-interna>:8000/api/candidates`
- **Response**: JSON array de candidatos
