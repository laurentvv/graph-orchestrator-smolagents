import requests
import json
from pydantic import BaseModel

# Schéma Pydantic désiré
class CodeJudgeOutput(BaseModel):
    is_approved: bool
    final_feedback: str

def test_qwen_json():
    # Construction du schéma JSON à partir de Pydantic
    schema = CodeJudgeOutput.model_json_schema()
    
    # Payload natif pour Ollama (Guided Decoding)
    payload = {
        "model": "Qwen3.5-9B-Q4_K_M",
        "messages": [
            {
                "role": "system",
                "content": "Tu es un juge. Réponds STRICTEMENT en JSON."
            },
            {
                "role": "user",
                "content": "Le code est parfait, pas de failles."
            }
        ],
        "format": schema, # La magie : on passe le schéma exact à Ollama
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }
    
    try:
        print("🚀 Appel de Qwen-2B via Ollama avec format JSON strict...")
        response = requests.post("http://localhost:11434/api/chat", json=payload)
        response.raise_for_status()
        
        data = response.json()
        raw_json = data["message"]["content"]
        
        print("\n--- JSON BRUT REÇU DU MODÈLE ---")
        print(raw_json)
        print("--------------------------------\n")
        
        # Validation Pydantic
        validated = CodeJudgeOutput.model_validate_json(raw_json)
        print("✅ SUCCÈS ! JSON parsé parfaitement par Pydantic :")
        print(validated)
        
    except Exception as e:
        print("❌ ERREUR :", e)

if __name__ == "__main__":
    test_qwen_json()
