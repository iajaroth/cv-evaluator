"""
Parser para extraer texto de archivos CV (DOCX, PDF, TXT)
"""
import os
from docx import Document
from pypdf import PdfReader
from typing import Optional


def extract_text_from_docx(file_path: str) -> str:
    """Extrae texto de un archivo .docx"""
    try:
        doc = Document(file_path)
        text = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text.append(paragraph.text)
        return "\n".join(text)
    except Exception as e:
        print(f"Error extrayendo texto de DOCX: {e}")
        return ""


def extract_text_from_pdf(file_path: str) -> str:
    """Extrae texto de un archivo .pdf"""
    try:
        reader = PdfReader(file_path)
        text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text and page_text.strip():
                text.append(page_text)
        return "\n".join(text)
    except Exception as e:
        print(f"Error extrayendo texto de PDF: {e}")
        return ""


def extract_text_from_txt(file_path: str) -> str:
    """Extrae texto de un archivo .txt"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, 'r', encoding='latin-1') as f:
            return f.read()
    except Exception as e:
        print(f"Error extrayendo texto de TXT: {e}")
        return ""


def parse_cv(file_path: str) -> Optional[str]:
    """
    Parsea un archivo CV y extrae el texto.
    Soporta .docx, .pdf, .txt
    """
    if not os.path.exists(file_path):
        print(f"Archivo no encontrado: {file_path}")
        return None
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.docx':
        return extract_text_from_docx(file_path)
    elif ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext == '.txt':
        return extract_text_from_txt(file_path)
    else:
        print(f"Formato no soportado: {ext}")
        return None
