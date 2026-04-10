"""
Motor de evaluacion de CVs con IA (OpenAI GPT-4o)
"""
import json
import os
from openai import AsyncOpenAI
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()


# Prompt del sistema basado en el perfil de tecnico en electronica de referencia
SYSTEM_PROMPT = """\
Eres un evaluador experto en perfiles de técnicos en electrónica. Tu trabajo es evaluar CVs de candidatos \
para determinar qué tan bien se ajustan al perfil que busca una empresa.

PERFIL DESEADO:
- Técnico en electrónica (formación técnica formal)
- Experiencia comprobable en electrónica
- Conocimientos sólidos en: mantenimiento, diagnóstico o instalación de equipos electrónicos
- Haber ejercido como técnico en trabajos anteriores
- Preferencia: experiencia en reparación de equipos, trabajo con circuitos, soldadura, instrumentación

CRITERIOS DE EVALUACION:
1. Formación técnica en electrónica (25%)
2. Experiencia laboral comprobable en el área (30%)
3. Conocimientos técnicos específicos (25%)
4. Estabilidad laboral y progresión (10%)
5. Presentación y claridad del CV (10%)

Debes responder ÚNICAMENTE con un JSON válido con esta estructura exacta:
{
    "score": <número del 1 al 10, con un decimal>,
    "summary": "<resumen ejecutivo de 2-3 lineas sobre el candidato>",
    "strengths": ["<fortaleza 1>", "<fortaleza 2>", ...],
    "weaknesses": ["<debilidad 1>", "<debilidad 2>", ...],
    "relevant_experience": "<descripcion de la experiencia relevante encontrada>",
    "technical_skills": ["<habilidad 1>", "<habilidad 2>", ...],
    "education": "<formación técnica/académica encontrada>",
    "years_of_experience": "<cadena con los años de experiencia estimados>",
    "recommendation": "<recomendación final: contratar, considerar o descartar con justificación>"
}

REGLAS:
- Si el candidato NO tiene formación técnica en electrónica, el score debe ser menor a 4.
- Si no tiene experiencia laboral comprobable, el score debe ser menor a 3.
- Si cumple con formación Y experiencia, el score debe ser 7 o superior.
- Si cumple con todo y tiene experiencia destacada, puede ser 9 o 10.
- Responde SOLO el JSON, sin texto adicional antes o después.
"""


class CVEvaluator:
    """Motor de evaluacion de CVs con OpenAI"""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY no configurada en las variables de entorno")
        
        self.client = AsyncOpenAI(api_key=api_key)
    
    async def evaluate_cv(self, cv_text: str) -> Dict:
        """
        Evalua un CV y retorna el resultado estructurado.
        """
        user_prompt = f"""Evalúa el siguiente CV y responde SOLO con un JSON válido según las instrucciones.

CV:
{cv_text}
"""
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            # Validar que tiene el score
            if "score" not in result:
                result["score"] = 0.0
            
            # Asegurar que el score sea un float
            result["score"] = float(result["score"])
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"Error parseando respuesta de IA: {e}")
            print(f"Respuesta raw: {result_text if 'result_text' in dir() else 'N/A'}")
            return self._default_evaluation()
        except Exception as e:
            print(f"Error evaluando CV con IA: {e}")
            return self._default_evaluation()
    
    def _default_evaluation(self) -> Dict:
        """Retorna una evaluación por defecto si la IA falla"""
        return {
            "score": 0.0,
            "summary": "Error al evaluar el CV. Se requiere revisión manual.",
            "strengths": [],
            "weaknesses": [],
            "relevant_experience": "No se pudo determinar",
            "technical_skills": [],
            "education": "No se pudo determinar",
            "years_of_experience": "No se pudo determinar",
            "recommendation": "Requiere revisión manual debido a un error en la evaluación automática."
        }
