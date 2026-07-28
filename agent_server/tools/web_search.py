"""Outil de recherche web (DuckDuckGo, sans clé API).

Wrapper autour de DuckDuckGoSearchTool de smolagents avec graceful degradation :
si la dépendance `ddgs` manque, l'outil renvoie un message d'erreur clair au lieu
de crasher le serveur au démarrage (pattern repris de my-claw).
"""

from smolagents import Tool


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Recherche sur le web (DuckDuckGo) et retourne les premiers résultats. "
        "Aucune clé API requise. Utile pour chercher de la documentation, des "
        "exemples de code, des issues GitHub, ou des informations récentes."
    )
    inputs = {
        "query": {
            "type": "string",
            "description": "La requête de recherche.",
        },
        "max_results": {
            "type": "integer",
            "nullable": True,
            "description": "Nombre max de résultats (défaut 5).",
        },
    }
    output_type = "string"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ddg = None
        try:
            from smolagents import DuckDuckGoSearchTool
            self._ddg = DuckDuckGoSearchTool()
        except Exception:
            # Dépendance ddgs manquante ou erreur — l'outil reste enregistré mais inopérant.
            self._ddg = None

    def forward(self, query: str, max_results: int = 5) -> str:
        if self._ddg is None:
            return ("[ERREUR] Recherche web indisponible : dépendance 'ddgs' manquante. "
                    "Installez-la avec : uv add ddgs")
        try:
            # DuckDuckGoSearchTool.forward ne prend que query ; on adapte.
            return self._ddg(query=query) if "query" in self._ddg.inputs else self._ddg(query)
        except Exception as e:
            return f"[ERREUR] Échec de la recherche web : {e}"
