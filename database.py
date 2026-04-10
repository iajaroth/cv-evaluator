"""
Modelos de base de datos para el sistema de evaluacion de CVs
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./candidates.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Candidate(Base):
    """Registro de un candidato que envio su CV"""
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)
    cv_file_path = Column(String, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)
    
    # Relacion con evaluacion
    evaluation = relationship("Evaluation", back_populates="candidate", uselist=False)


class Evaluation(Base):
    """Evaluacion IA del perfil del candidato"""
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, nullable=False)
    score = Column(Float, nullable=True)  # 1-10
    summary = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)  # JSON list como string
    weaknesses = Column(Text, nullable=True)  # JSON list como string
    relevant_experience = Column(Text, nullable=True)
    technical_skills = Column(Text, nullable=True)  # JSON list como string
    education = Column(String, nullable=True)
    years_of_experience = Column(String, nullable=True)
    recommendation = Column(Text, nullable=True)
    evaluated_at = Column(DateTime, default=datetime.utcnow)
    raw_ai_response = Column(Text, nullable=True)
    
    # Relacion
    candidate = relationship("Candidate", back_populates="evaluation")


def init_db():
    """Inicializa la base de datos y crea las tablas"""
    Base.metadata.create_all(bind=engine)
    print("Base de datos inicializada correctamente")


def get_db():
    """Obtiene una sesion de base de datos"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
