"""
API principal - Sistema de evaluacion automatica de CVs
"""
import os
import sys
import logging
from logging import basicConfig

# Configurar logging ANTES de cualquier importacion
basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("cv-evaluator")

logger.info("Python %s", sys.version)
logger.info("Working dir: %s", os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

logger.info("FastAPI importado correctamente")

import json
import shutil
import secrets
import asyncio

# Ahora si importar dependencias
try:
    from database import init_db, get_db, Candidate, Evaluation, SessionLocal
    logger.info("Database module OK")
except Exception as e:
    logger.error(f"Database module ERROR: {e}")
    raise

try:
    from cv_parser import parse_cv
    logger.info("CV parser module OK")
except Exception as e:
    logger.error(f"CV parser module ERROR: {e}")
    raise

try:
    from ai_evaluator import CVEvaluator
    logger.info("AI evaluator module OK")
except Exception as e:
    logger.error(f"AI evaluator module ERROR: {e}")
    raise

# ============================================
# Configuracion
# ============================================
API_KEY = os.getenv("SERVICE_API_KEY", "")
if not API_KEY:
    API_KEY = secrets.token_hex(32)
    print(f"[IMPORTANTE] SERVICE_API_KEY generada automaticamente: {API_KEY}")
    print("Guardala en tu .env para futuros despliegues")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

api_key_header = APIKeyHeader(name="X-API-Key")

# Evaluador IA (se inicializa bajo demanda)
evaluator = None


def get_evaluator() -> CVEvaluator:
    global evaluator
    if evaluator is None:
        evaluator = CVEvaluator()
    return evaluator


async def verify_api_key(key: str = Security(api_key_header)):
    """Verifica la API key si esta configurada"""
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    return key


# ============================================
# Templates HTML
# ============================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panel de Evaluacion de Candidatos</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">
    <style>
        :root {{
            --score-high: #198754;
            --score-medium: #ffc107;
            --score-low: #dc3545;
        }}
        body {{ background: #f0f2f5; font-family: 'Segoe UI', system-ui, sans-serif; }}
        .navbar {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }}
        .score-badge {{
            font-size: 1.5rem;
            font-weight: 700;
            padding: 0.5rem 1rem;
            border-radius: 12px;
            min-width: 70px;
            text-align: center;
        }}
        .score-high {{ background: var(--score-high); color: white; }}
        .score-medium {{ background: var(--score-medium); color: #333; }}
        .score-low {{ background: var(--score-low); color: white; }}
        .candidate-card {{
            border: none;
            border-radius: 16px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            transition: transform 0.2s, box-shadow 0.2s;
            margin-bottom: 1rem;
        }}
        .candidate-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.12);
        }}
        .strength-item {{ color: var(--score-high); }}
        .weakness-item {{ color: var(--score-low); }}
        .filter-btn {{ border-radius: 20px; }}
        .stat-card {{
            background: white;
            border-radius: 16px;
            padding: 1.5rem;
            text-align: center;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        }}
        .stat-number {{ font-size: 2.5rem; font-weight: 700; }}
        .loading-spinner {{ display: none; }}
        .empty-state {{ text-align: center; padding: 4rem 2rem; }}
        .empty-state i {{ font-size: 4rem; color: #ccc; }}
        .modal-lg {{ max-width: 800px; }}
    </style>
</head>
<body>
    <nav class="navbar navbar-dark mb-4">
        <div class="container">
            <span class="navbar-brand mb-0 h1">
                <i class="fas fa-robot me-2"></i>Panel de Evaluacion de Candidatos
            </span>
            <span class="text-white-50" id="lastUpdate"></span>
        </div>
    </nav>

    <div class="container">
        <!-- Estadisticas -->
        <div class="row mb-4" id="statsRow">
            <div class="col-6 col-md-3 mb-2">
                <div class="stat-card">
                    <div class="stat-number text-primary" id="statTotal">0</div>
                    <div class="text-muted">Total Candidatos</div>
                </div>
            </div>
            <div class="col-6 col-md-3 mb-2">
                <div class="stat-card">
                    <div class="stat-number text-success" id="statHigh">0</div>
                    <div class="text-muted">Score 7-10</div>
                </div>
            </div>
            <div class="col-6 col-md-3 mb-2">
                <div class="stat-card">
                    <div class="stat-number text-warning" id="statMedium">0</div>
                    <div class="text-muted">Score 4-6.9</div>
                </div>
            </div>
            <div class="col-6 col-md-3 mb-2">
                <div class="stat-card">
                    <div class="stat-number text-danger" id="statLow">0</div>
                    <div class="text-muted">Score < 4</div>
                </div>
            </div>
        </div>

        <!-- Filtros -->
        <div class="d-flex flex-wrap gap-2 mb-4">
            <button class="btn btn-outline-primary filter-btn active" onclick="filterCandidates('all')">
                <i class="fas fa-list me-1"></i>Todos
            </button>
            <button class="btn btn-success filter-btn" onclick="filterCandidates('high')">
                <i class="fas fa-star me-1"></i>Top (7-10)
            </button>
            <button class="btn btn-warning filter-btn" onclick="filterCandidates('medium')">
                <i class="fas fa-minus me-1"></i>Medio (4-6.9)
            </button>
            <button class="btn btn-danger filter-btn" onclick="filterCandidates('low')">
                <i class="fas fa-times me-1"></i>Bajo (< 4)
            </button>
            <button class="btn btn-outline-secondary filter-btn" onclick="filterCandidates('pending')">
                <i class="fas fa-clock me-1"></i>Pendientes
            </button>
            <div class="ms-auto">
                <button class="btn btn-outline-primary" onclick="loadCandidates()">
                    <i class="fas fa-sync-alt me-1"></i>Actualizar
                </button>
            </div>
        </div>

        <!-- Lista de candidatos -->
        <div id="candidatesList"></div>

        <!-- Estado vacio -->
        <div class="empty-state" id="emptyState" style="display:none;">
            <i class="fas fa-inbox d-block mb-3"></i>
            <h4>No hay candidatos</h4>
            <p class="text-muted">Los CVs recibidos apareceran aqui despues de ser evaluados.</p>
        </div>
    </div>

    <!-- Modal de detalle -->
    <div class="modal fade" id="candidateModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content" style="border-radius:16px;">
                <div class="modal-header" style="background:linear-gradient(135deg,#667eea,#764ba2);">
                    <h5 class="modal-title text-white" id="modalTitle">Detalle del Candidato</h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body" id="modalBody"></div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let allCandidates = [];
        let currentFilter = 'all';

        async function loadCandidates() {{
            try {{
                const res = await fetch('/api/candidates');
                allCandidates = await res.json();
                renderStats();
                renderCandidates();
                document.getElementById('lastUpdate').textContent = 'Ultima actualizacion: ' + new Date().toLocaleTimeString();
            }} catch(e) {{
                console.error('Error cargando candidatos:', e);
            }}
        }}

        function renderStats() {{
            const total = allCandidates.length;
            const high = allCandidates.filter(c => c.evaluation && c.evaluation.score >= 7).length;
            const medium = allCandidates.filter(c => c.evaluation && c.evaluation.score >= 4 && c.evaluation.score < 7).length;
            const low = allCandidates.filter(c => c.evaluation && c.evaluation.score < 4).length;
            
            document.getElementById('statTotal').textContent = total;
            document.getElementById('statHigh').textContent = high;
            document.getElementById('statMedium').textContent = medium;
            document.getElementById('statLow').textContent = low;
        }}

        function getScoreClass(score) {{
            if (score >= 7) return 'score-high';
            if (score >= 4) return 'score-medium';
            return 'score-low';
        }}

        function renderCandidates() {{
            const container = document.getElementById('candidatesList');
            const emptyState = document.getElementById('emptyState');
            
            let filtered = allCandidates;
            if (currentFilter === 'high') filtered = allCandidates.filter(c => c.evaluation && c.evaluation.score >= 7);
            else if (currentFilter === 'medium') filtered = allCandidates.filter(c => c.evaluation && c.evaluation.score >= 4 && c.evaluation.score < 7);
            else if (currentFilter === 'low') filtered = allCandidates.filter(c => c.evaluation && c.evaluation.score < 4);
            else if (currentFilter === 'pending') filtered = allCandidates.filter(c => !c.processed);
            
            if (filtered.length === 0) {{
                container.innerHTML = '';
                emptyState.style.display = 'block';
                return;
            }}
            
            emptyState.style.display = 'none';
            
            container.innerHTML = filtered.map(c => {{
                const eval = c.evaluation || {{}};
                const scoreDisplay = c.processed 
                    ? `<span class="score-badge ${'{getScoreClass(eval.score || 0)}'}'>{eval.score?.toFixed(1) || 'N/A'}</span>`
                    : '<span class="badge bg-secondary">Pendiente</span>';
                
                return `
                <div class="candidate-card card p-3" onclick="showDetail(${c.id})" style="cursor:pointer;">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <h5 class="mb-1">${c.full_name || 'Nombre no disponible'}</h5>
                            <small class="text-muted">
                                <i class="fas fa-envelope me-1"></i>${c.email || 'Sin email'}
                                ${c.received_at ? ' | <i class="fas fa-calendar me-1"></i>' + new Date(c.received_at).toLocaleDateString() : ''}
                            </small>
                        </div>
                        <div>${scoreDisplay}</div>
                    </div>
                    ${eval.summary ? `<p class="mb-0 mt-2 text-muted small">${eval.summary.substring(0, 120)}...</p>` : ''}
                </div>`;
            }}).join('');
        }}

        function filterCandidates(filter) {{
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.closest('.filter-btn').classList.add('active');
            renderCandidates();
        }}

        async function showDetail(id) {{
            const c = allCandidates.find(x => x.id === id);
            if (!c) return;
            
            const eval = c.evaluation || {{}};
            const modal = new bootstrap.Modal(document.getElementById('candidateModal'));
            
            document.getElementById('modalTitle').textContent = c.full_name || 'Candidato';
            
            let html = `
                <div class="row mb-3">
                    <div class="col-md-6">
                        <p><strong>Email:</strong> ${c.email || 'N/A'}</p>
                        <p><strong>Telefono:</strong> ${c.phone || 'N/A'}</p>
                        <p><strong>Recibido:</strong> ${c.received_at ? new Date(c.received_at).toLocaleString() : 'N/A'}</p>
                    </div>
                    <div class="col-md-6 text-center">
                        ${c.processed 
                            ? `<span class="score-badge ${getScoreClass(eval.score || 0)}" style="font-size:2.5rem;padding:1rem 2rem;">${(eval.score || 0).toFixed(1)}</span>
                               <div class="mt-2 text-muted">Score de evaluacion</div>`
                            : '<span class="badge bg-secondary fs-5">Pendiente de evaluacion</span>'
                        }
                    </div>
                </div>
            `;
            
            if (eval.summary) {{
                html += `
                    <hr>
                    <h6><i class="fas fa-clipboard-check me-2"></i>Resumen</h6>
                    <p>${eval.summary}</p>
                    
                    <div class="row">
                        <div class="col-md-6">
                            <h6><i class="fas fa-check-circle me-2 text-success"></i>Fortalezas</h6>
                            <ul class="list-unstyled">
                                ${(eval.strengths || []).map(s => `<li class="strength-item"><i class="fas fa-check me-1"></i>${s}</li>`).join('') || '<li class="text-muted">N/A</li>'}
                            </ul>
                        </div>
                        <div class="col-md-6">
                            <h6><i class="fas fa-times-circle me-2 text-danger"></i>Debilidades</h6>
                            <ul class="list-unstyled">
                                ${(eval.weaknesses || []).map(w => `<li class="weakness-item"><i class="fas fa-times me-1"></i>${w}</li>`).join('') || '<li class="text-muted">N/A</li>'}
                            </ul>
                        </div>
                    </div>
                    
                    <hr>
                    <div class="row">
                        <div class="col-md-6">
                            <h6><i class="fas fa-briefcase me-2"></i>Experiencia Relevante</h6>
                            <p class="text-muted small">${eval.relevant_experience || 'N/A'}</p>
                        </div>
                        <div class="col-md-6">
                            <h6><i class="fas fa-graduation-cap me-2"></i>Educacion</h6>
                            <p>${eval.education || 'N/A'}</p>
                            <p><strong>Años de experiencia:</strong> ${eval.years_of_experience || 'N/A'}</p>
                        </div>
                    </div>
                    
                    <h6><i class="fas fa-tools me-2"></i>Habilidades Tecnicas</h6>
                    <div class="d-flex flex-wrap gap-2 mb-3">
                        ${(eval.technical_skills || []).map(s => `<span class="badge bg-info">${s}</span>`).join('') || '<span class="text-muted">N/A</span>'}
                    </div>
                    
                    <div class="alert ${eval.score >= 7 ? 'alert-success' : eval.score >= 4 ? 'alert-warning' : 'alert-danger'}">
                        <strong><i class="fas fa-lightbulb me-2"></i>Recomendacion:</strong> ${eval.recommendation || 'N/A'}
                    </div>
                `;
            }}
            
            document.getElementById('modalBody').innerHTML = html;
            modal.show();
        }}

        // Cargar al iniciar
        loadCandidates();
        // Actualizar cada 30 segundos
        setInterval(loadCandidates, 30000);
    </script>
</body>
</html>
"""


# ============================================
# App FastAPI
# ============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Inicializar el evaluador de IA al arranque
    global evaluator
    try:
        from ai_evaluator import CVEvaluator
        evaluator = CVEvaluator()
        print("[STARTUP] CV Evaluator inicializado correctamente")
    except ValueError as e:
        print(f"[STARTUP] OPENAI_API_KEY no configurada: {e}")
        print("[STARTUP] El sistema funcionara sin evaluacion automatica")
    except Exception as e:
        print(f"[STARTUP] Error inicializando evaluador: {e}")
    print("[STARTUP] CV Evaluator API iniciado en puerto 8000")
    yield


app = FastAPI(
    title="CV Evaluator",
    description="Sistema automatico de evaluacion de candidatos para tecnico en electronica",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================
# Endpoints publicos (sin auth)
# ============================================
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Panel de visualizacion de candidatos"""
    return HTMLResponse(content=HTML_TEMPLATE)


@app.get("/health")
async def health():
    """Healthcheck"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/debug")
async def debug_info():
    """Info de debug para diagnosticar problemas"""
    import sys
    import traceback
    
    info = {
        "python_version": sys.version,
        "evaluator_initialized": evaluator is not None,
        "upload_dir": UPLOAD_DIR,
        "upload_dir_exists": os.path.exists(UPLOAD_DIR),
    }
    
    # Probar la base de datos
    try:
        db = SessionLocal()
        from database import Candidate
        count = db.query(Candidate).count()
        info["db_candidates"] = count
        db.close()
        info["db_ok"] = True
    except Exception as e:
        info["db_ok"] = False
        info["db_error"] = str(e)
    
    # Probar el parser
    try:
        from cv_parser import parse_cv
        info["parser_ok"] = True
    except Exception as e:
        info["parser_ok"] = False
        info["parser_error"] = str(e)
    
    # Probar el evaluador
    try:
        if evaluator:
            info["evaluator_ok"] = True
        else:
            info["evaluator_ok"] = False
            info["evaluator_error"] = "Not initialized"
    except Exception as e:
        info["evaluator_ok"] = False
        info["evaluator_error"] = str(e)
    
    return info


# ============================================
# Endpoints de API (con auth opcional)
# ============================================
@app.post("/api/candidates/upload")
async def upload_cv(
    file: UploadFile = File(...),
    email: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Sube un CV para ser evaluado por IA.
    
    - **file**: Archivo del CV (.docx, .pdf, .txt)
    - **email**: Email del candidato (opcional)
    """
    try:
        # Validar extension
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ['.docx', '.pdf', '.txt']:
            raise HTTPException(status_code=400, detail=f"Formato no soportado: {ext}. Use .docx, .pdf o .txt")
        
        # Guardar archivo
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, safe_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Crear registro en BD
        candidate = Candidate(
            email=email,
            original_filename=file.filename,
            cv_file_path=file_path,
            received_at=datetime.utcnow()
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        
        # Evaluar con IA de forma sincrona
        try:
            result = await evaluate_candidate(candidate.id)
            return {
                "message": "CV recibido y evaluado",
                "candidate_id": candidate.id,
                "filename": file.filename,
                "evaluation": result
            }
        except Exception as eval_error:
            print(f"Error en evaluacion: {eval_error}")
            return {
                "message": "CV recibido pero falló la evaluacion",
                "candidate_id": candidate.id,
                "filename": file.filename,
                "error": str(eval_error)
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error general en upload: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/candidates")
async def list_candidates(db: Session = Depends(get_db)):
    """Lista todos los candidatos con sus evaluaciones"""
    candidates = db.query(Candidate).order_by(Candidate.received_at.desc()).all()
    
    result = []
    for c in candidates:
        candidate_dict = {
            "id": c.id,
            "email": c.email,
            "full_name": c.full_name,
            "phone": c.phone,
            "received_at": c.received_at.isoformat() if c.received_at else None,
            "processed": c.processed,
            "evaluation": None
        }
        
        if c.evaluation:
            candidate_dict["evaluation"] = {
                "id": c.evaluation.id,
                "score": c.evaluation.score,
                "summary": c.evaluation.summary,
                "strengths": json.loads(c.evaluation.strengths) if c.evaluation.strengths else [],
                "weaknesses": json.loads(c.evaluation.weaknesses) if c.evaluation.weaknesses else [],
                "relevant_experience": c.evaluation.relevant_experience,
                "technical_skills": json.loads(c.evaluation.technical_skills) if c.evaluation.technical_skills else [],
                "education": c.evaluation.education,
                "years_of_experience": c.evaluation.years_of_experience,
                "recommendation": c.evaluation.recommendation,
                "evaluated_at": c.evaluation.evaluated_at.isoformat() if c.evaluation.evaluated_at else None
            }
        
        result.append(candidate_dict)
    
    return result


@app.get("/api/candidates/{candidate_id}")
async def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Obtiene detalle de un candidato especifico"""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidato no encontrado")
    
    result = {
        "id": candidate.id,
        "email": candidate.email,
        "full_name": candidate.full_name,
        "phone": candidate.phone,
        "original_filename": candidate.original_filename,
        "received_at": candidate.received_at.isoformat() if candidate.received_at else None,
        "processed": candidate.processed,
        "evaluation": None
    }
    
    if candidate.evaluation:
        result["evaluation"] = {
            "score": candidate.evaluation.score,
            "summary": candidate.evaluation.summary,
            "strengths": json.loads(candidate.evaluation.strengths) if candidate.evaluation.strengths else [],
            "weaknesses": json.loads(candidate.evaluation.weaknesses) if candidate.evaluation.weaknesses else [],
            "relevant_experience": candidate.evaluation.relevant_experience,
            "technical_skills": json.loads(candidate.evaluation.technical_skills) if candidate.evaluation.technical_skills else [],
            "education": candidate.evaluation.education,
            "years_of_experience": candidate.evaluation.years_of_experience,
            "recommendation": candidate.evaluation.recommendation,
            "evaluated_at": candidate.evaluation.evaluated_at.isoformat() if candidate.evaluation.evaluated_at else None
        }
    
    return result


@app.delete("/api/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    db: Session = Depends(get_db)
):
    """Elimina un candidato y su evaluacion"""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidato no encontrado")
    
    # Eliminar archivo si existe
    if candidate.cv_file_path and os.path.exists(candidate.cv_file_path):
        os.remove(candidate.cv_file_path)
    
    # Eliminar evaluacion si existe
    if candidate.evaluation:
        db.delete(candidate.evaluation)
    
    db.delete(candidate)
    db.commit()
    
    return {"message": "Candidato eliminado correctamente"}


@app.post("/api/candidates/{candidate_id}/re-evaluate")
async def re_evaluate_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Re-evalua un candidato con IA"""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidato no encontrado")
    
    if not candidate.cv_file_path or not os.path.exists(candidate.cv_file_path):
        raise HTTPException(status_code=400, detail="Archivo CV no encontrado")
    
    result = await evaluate_candidate(candidate.id, force=True)
    return result


# ============================================
# Funcion de evaluacion en background
# ============================================
async def evaluate_candidate(candidate_id: int, force: bool = False) -> dict:
    """
    Evalua un candidato con IA y guarda el resultado.
    Se puede ejecutar en background o de forma sincrona.
    """
    db = SessionLocal()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return {"error": "Candidato no encontrado"}
        
        if candidate.processed and not force:
            return {"message": "Candidato ya evaluado"}
        
        # Parsear CV
        cv_text = parse_cv(candidate.cv_file_path)
        if not cv_text:
            candidate.processed = True
            db.commit()
            return {"error": "No se pudo extraer texto del CV"}
        
        # Extraer nombre del filename o del contenido
        # Intentar extraer email del nombre de archivo si tiene patron
        if not candidate.full_name:
            # Usar el nombre del archivo como nombre provisional
            candidate.full_name = os.path.splitext(candidate.original_filename or "CV_Desconocido")[0]
        
        # Evaluar con IA
        ai_eval = get_evaluator()
        result = await ai_eval.evaluate_cv(cv_text)
        
        # Intentar extraer nombre y telefono del texto del CV
        if not candidate.full_name or candidate.full_name.startswith("CV_"):
            lines = cv_text.split('\n')
            for line in lines[:10]:  # Buscar en las primeras 10 lineas
                line = line.strip()
                if len(line) > 3 and len(line) < 60:
                    candidate.full_name = line
                    break
        
        # Guardar evaluacion
        evaluation = Evaluation(
            candidate_id=candidate.id,
            score=result.get("score", 0.0),
            summary=result.get("summary", ""),
            strengths=json.dumps(result.get("strengths", []), ensure_ascii=False),
            weaknesses=json.dumps(result.get("weaknesses", []), ensure_ascii=False),
            relevant_experience=result.get("relevant_experience", ""),
            technical_skills=json.dumps(result.get("technical_skills", []), ensure_ascii=False),
            education=result.get("education", ""),
            years_of_experience=result.get("years_of_experience", ""),
            recommendation=result.get("recommendation", ""),
            raw_ai_response=json.dumps(result, ensure_ascii=False)
        )
        
        # Eliminar evaluacion previa si existe (re-evaluacion)
        if candidate.evaluation:
            db.delete(candidate.evaluation)
            db.flush()
        
        db.add(evaluation)
        candidate.processed = True
        db.commit()
        
        print(f"Candidato #{candidate_id} evaluado: score={result.get('score', 0)}")
        
        return {
            "message": "Evaluacion completada",
            "candidate_id": candidate.id,
            "score": result.get("score", 0.0)
        }
        
    except Exception as e:
        print(f"Error evaluando candidato #{candidate_id}: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# ============================================
# Montar estaticos
# ============================================
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
