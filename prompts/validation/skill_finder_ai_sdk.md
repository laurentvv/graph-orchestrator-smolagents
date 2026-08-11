---
id: skill-finder-ai-sdk-chatbot
title: Chatbot Vercel AI SDK (force la recherche de skill — F-82)
purpose: >
  Prompt de validation F-82 (Skill Finder). "ai-sdk" / "ai sdk" n'est dans AUCUNE
  regex locale (EXTERNAL_LIB_PATTERN ne le liste pas) → gap de compétence garanti.
  Domaine vercel-labs (le Vercel AI SDK est édité par Vercel) → install de confiance
  probable. Le ReAct SkillResearchSignature de l'Architect DOIT appeler
  search_and_install_skill. Critère de réussite : voir "Skill installé" dans le log
  + une entrée dans skills/installed-skills.json avec sa regex dédiée.
target_files:
  - index.html
  - src/App.jsx
  - src/main.jsx
  - server/api/chat.js
expected_skill_finder: search "ai-sdk" → install d'un skill vercel-labs
note_validation: >
  Le but est de valider l'étape Architect (ReAct + install + manifeste), pas de
  livrer un app React parfaite. Préférer debug/run_architect.py (isolation, ~minutes)
  plutôt qu'un E2E complet (30 min). Observer : log "[+] Architect : Résultat de la
  recherche de skills", fichier skills/installed-skills.json, et skills/<name>/SKILL.md.
---

Construis une application web (React + Vite) de chatbot alimenté par le **Vercel AI SDK** (`ai` package) : streaming des réponses token par token, hook `useChat`, route backend `/api/chat`, champ de saisie + historique des messages, indicateur « typing » pendant la génération.

Fonctionnalités attendues :
- un champ de saisie + bouton « Envoyer » qui poste le message utilisateur ;
- affichage de l'historique (user vs assistant) avec distinction visuelle ;
- **streaming** : la réponse assistant apparaît token par token (via `useChat` du AI SDK) ;
- un indicateur « typing / génération… » pendant que l'assistant répond ;
- route backend `/api/chat` qui proxie vers le modèle (signature compatible `streamText`).

Contraintes techniques : React fonctionnel (hooks), fichier de configuration Vite propre, structure de fichiers lisible, sans framework UI lourd (CSS vanilla ou Tailwind au choix). Typage soigné.
