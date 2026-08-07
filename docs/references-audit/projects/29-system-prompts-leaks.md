# 28 - System Prompts Leaks

## 📝 Synthèse
* **Date d'audit** : 2026-08-07
* **Dépôt** : [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks)
* **Description** : Collection massive de prompts système "fuites" (leaked) provenant des principaux modèles d'IA du marché (OpenAI, Anthropic, Google, xAI, Perplexity, Microsoft, etc.).
* **Utilité** : Fournit un aperçu exceptionnel et non censuré des instructions système utilisées en production pour des modèles de pointe et des agents complexes (comme Claude Code, Antigravity CLI, OpenCode, Cursor).

## 🎯 Points Forts / Architecture
* **Diversité et Couverture** : Comprend les modèles les plus récents (jusqu'à juillet 2026) comme Claude Opus 5, ChatGPT 5.6 Sol, Gemini 3.5 Flash, et Grok 4.5.
* **Architecture d'Agents** : Les prompts de "Claude Code", "Antigravity CLI", "Cursor", et "Perplexity Computer" révèlent comment les grandes entreprises configurent leurs boucles d'agents, leurs garde-fous (safety rails), et l'utilisation de leurs outils (MCP, outils locaux, exécution de commandes).
* **Garde-fous (Guardrails)** : De nombreuses instructions traitent de la prévention des injections de prompts, de la sécurité d'exécution de code, et de la validation avant modification (ex. Git Safety Protocol).

## 🚫 Points d'Exclusion
* **Prompts obsolètes** : Les sous-dossiers "Old" contiennent des prompts dépréciés qui ne reflètent plus l'état de l'art.
* **Personas non techniques** : Les prompts de "Personalities" ou "Voice Assistant" ne sont pas pertinents pour l'orchestrateur de code et les sous-agents d'usine logicielle.

## 📦 Composants Pertinents pour le Projet

1. **Claude Code / Claude Design (Anthropic)** : Instructions détaillées pour des agents développeurs et concepteurs de haute volée. Intègre des instructions strictes d'utilisation des outils et de revue de code avant l'écriture.
2. **Antigravity CLI (Google)** : Instructions d'un agent CLI puissant. Utile pour modéliser notre interface en ligne de commande.
3. **Cursor / OpenCode / GitHub Copilot** : Modèles d'agents IDE et éditeurs avec une attention particulière à la manipulation des fichiers, à la limitation de la boucle et au gating.
4. **Perplexity Deep Research / Computer** : Patterns de recherche web profonde et d'utilisation de l'ordinateur par un LLM.

## 🚀 Recommandations pour l'Usine Logicielle
* **Mise à jour des prompts système (Priorité 14)** : Intégrer les meilleures pratiques extraites (notamment sur la sécurité et le test-driven editing) dans les signatures DSPy des nœuds `Architect`, `Coder`, `Tester` et `Judge`.
* **Sécurité & Isolation (Priorité 8)** : Renforcer les middlewares d'auto-réparation en s'inspirant des instructions de repli (fallback instructions) de Claude Code et Cursor.
