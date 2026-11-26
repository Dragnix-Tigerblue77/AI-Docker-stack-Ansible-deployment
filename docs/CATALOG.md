<!--
SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
SPDX-License-Identifier: AGPL-3.0-only
-->

# Catalogue de la passerelle LiteLLM

> Ce fichier est généré par `python3 .github/scripts/generate_catalog.py` à partir du modèle de configuration de LiteLLM (`templates/LiteLLM_config.yaml.j2`), des contrats des routeurs (`.github/LiteLLM_router_contracts.yaml`) et des scores lus en ligne (`docs/catalog_scores.json`). Ne le modifiez pas à la main : la CI refuse un fichier qui n'est pas ce que ces sources produisent, et un changement de l'une d'elles le régénère dans le même commit.

Ce catalogue dit tout ce que la passerelle sert : les groupes d'accès, les routeurs et leurs membres, les fournisseurs, et chaque modèle, avec ses limites et ses scores. Il décrit la configuration rendue avec la clé de tous les fournisseurs donnée.

## Sommaire

- [Les groupes d'accès et les types de LiteLLM](#les-groupes-daccès-et-les-types-de-litellm)
- [Les routeurs](#les-routeurs)
  - [`Auto`](#auto)
  - [`Auto-Pro`](#auto-pro)
  - [`Auto-Flash`](#auto-flash)
  - [`Auto-Flash-Lite`](#auto-flash-lite)
  - [`Auto-Code`](#auto-code)
  - [`Auto-Claude-Code`](#auto-claude-code)
  - [`Auto-STT`](#auto-stt)
  - [`Auto-TTS`](#auto-tts)
  - [`Auto-Decision`](#auto-decision)
  - [`Auto-Extraction`](#auto-extraction)
  - [`Auto-Fiction`](#auto-fiction)
  - [`Auto-Paid`](#auto-paid)
- [Les fournisseurs](#les-fournisseurs)
- [Les modèles](#les-modèles)
  - [Les scores d'Artificial Analysis et d'Epoch AI](#les-scores-dartificial-analysis-et-depoch-ai)

## Les groupes d'accès et les types de LiteLLM

Chaque entrée est dans le groupe de son type, ce qui permet de limiter une clé virtuelle à un type de modèles dans l'interface de LiteLLM. Les groupes sont des étiquettes que ce dépôt pose sur les entrées (`model_info.access_groups`), alors que le type est le `model_info.mode` de LiteLLM, un ensemble borné : une entrée sans `mode` est un modèle de conversation. Un routeur suit sa tête : une clé qui atteint l'entrée atteint les routeurs dont elle est la tête.

| Groupe | Type LiteLLM | Usage | Remarque |
| --- | --- | --- | --- |
| `LLM` | chat (aucun `mode`) | Texte : conversation et complétion | — |
| `STT` | `audio_transcription` | Transcription de la parole (`/audio/transcriptions`) | — |
| `TTS` | `audio_speech` | Synthèse vocale (`/audio/speech`) | — |
| `Embeddings` | `embedding` | Vecteurs d'un texte (`/embeddings`) | — |
| `Decisions` | `evaluation` | Décisions typées | — |
| `Extraction` | `extraction` | Extraction typée | — |
| `Images` | `image_generation` | Génération d'images (`/images/generations`) | — |
| `Videos` | `video_generation` | Génération de vidéos (`/videos`) | — |
| `Rerank` | `rerank` | Reclassement de documents (`/rerank`) | — |
| `Moderation` | `moderation` | Modération de contenu (`/moderations`) | — |
| `OCR` | `ocr` | Lecture du texte d'une image ou d'un PDF (`/ocr`) | — |
| `Fiction` | chat (aucun `mode`) | Texte : conversation et complétion | mis à part : seules les entrées qui lisent la clé de Aion Labs en font partie, et aucune clé qui n'a que `LLM` ne les atteint |

Ces groupes s'ajoutent au groupe du type : une entrée qui en porte un est aussi dans celui de son type, et la ligne dit sur quel groupe de type il se trouve.

| Groupe supplémentaire | Groupe de type |
| --- | --- |
| `Private-Data` | `Decisions` |
| `Private-Data` | `Embeddings` |
| `Private-Data` | `Extraction` |
| `Private-Data` | `Fiction` |
| `Private-Data` | `LLM` |
| `Private-Data` | `STT` |
| `Private-Data` | `TTS` |
| `Claude-Code` | `LLM` |
| `Public-Data-Only` | `Embeddings` |
| `Public-Data-Only` | `LLM` |
| `Public-Data-Only` | `STT` |
| `Public-Data-Only` | `TTS` |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les routeurs

Un routeur est un nom que le client écrit et derrière lequel LiteLLM essaie les membres de sa cascade dans l'ordre, en passant au suivant quand un membre échoue. Les cascades ci-dessous sont celles du modèle rendu avec la clé de tous les fournisseurs : sans la clé d'un fournisseur, ses entrées disparaissent et l'ordre des autres ne change pas. Le rôle d'un routeur est la première phrase du commentaire qui ouvre sa cascade dans le modèle, en anglais comme lui ; le reste vient des contrats des routeurs. Les membres d'une cascade sont dans l'ordre de ses lignes, le premier d'abord.

| Routeur | Rôle | Tête |
| --- | --- | --- |
| `Auto` | Aiguille chaque requête vers `Auto-Flash-Lite`, `Auto-Flash`, `Auto-Pro` selon sa complexité | — |
| `Auto-Pro` | Pure reasoning, multi-step logic, architecture | `gemini-4-hydrogen` |
| `Auto-Flash` | Balanced daily driver | `gemini-4-hydrogen` |
| `Auto-Flash-Lite` | Simple, short asks | `gemini-3-5-flash-lite` |
| `Auto-Code` | Refactoring, Ansible playbooks, Bash/Python scripts | `gemini-4-hydrogen` |
| `Auto-Claude-Code` | 100% agentic CLI (strict tool/function calling, 128k+ context) | `gemini-4-hydrogen` |
| `Auto-STT` | Speech to text, for "/audio/transcriptions" | `whisper-large-v3-groq` |
| `Auto-TTS` | Text to speech, for /audio/speech | `gemini-3-8-flash-tts` |
| `Auto-Decision` | Clef's typed decisions, for "/v1/systemone" and "/v1/decisions" | `clef-cloudflare` |
| `Auto-Extraction` | Clairic's typed extraction, for "/v1/extraction" | `clairic-cloudflare` |
| `Auto-Fiction` | The role-play and fiction models of Aion Labs, and only those | `aion-3-5-aion-labs` |
| `Auto-Paid` | The models paid from a credit, Anthropic's, and only those | `claude-fable-5-2-anthropic` |

### `Auto`

Cette entrée n'a pas de cascade : le routeur qu'elle choisit a la sienne.

| Complexité de la requête | Routeur choisi |
| --- | --- |
| `SIMPLE` | `Auto-Flash-Lite` |
| `MEDIUM` | `Auto-Flash` |
| `COMPLEX` | `Auto-Pro` |
| `REASONING` | `Auto-Pro` |

### `Auto-Pro`

- Classement : indice d'intelligence
- Derniers recours : `deepseek-v4-pro-direct`, `omniroute-free-reasoning`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `inkling-2-small-vercel` | Vercel AI Gateway | — | — |
| `ling-3-1-flash-requesty` | Requesty | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-vercel` | Vercel AI Gateway | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `ling-3-1-flash-1019-vercel` | Vercel AI Gateway | — | — |
| `muse-spark-open-vercel` | Vercel AI Gateway | — | — |
| `mimo-v2-6-flash-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-2-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-2-fast-vercel` | Vercel AI Gateway | — | — |
| `beam-kilo` | Kilo | — | — |
| `nemotron-ultra-free` | OpenRouter | `high` | — |
| `nemotron-ultra-requesty` | Requesty | `max` | — |
| `nemotron-ultra-nvidia` | NVIDIA | — | — |
| `nemotron-ultra-vercel` | Vercel AI Gateway | — | — |
| `nemotron-ultra-kilo` | Kilo | `high` | — |
| `nemotron-reasoning-free` | OpenRouter | — | — |
| `nemotron-reasoning-requesty` | Requesty | `max` | — |
| `nemotron-reasoning-nvidia` | NVIDIA | — | — |
| `nemotron-reasoning-kilo` | Kilo | — | — |
| `nemotron-super-vl-free` | OpenRouter | — | — |
| `nemotron-super-vl-nvidia` | NVIDIA | — | — |
| `nemotron-super-vl-vercel` | Vercel AI Gateway | — | — |
| `nemotron-super-vl-kilo` | Kilo | — | — |
| `hy4-flash-cent-ai` | Cent AI | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | défaut : high | dernier recours |
| `omniroute-free-reasoning` | OmniRoute | — | dernier recours |

### `Auto-Flash`

- Classement : indice d'intelligence
- Derniers recours : `deepseek-flash-direct`, `omniroute-free-auto`, `openrouter-auto-free`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `inkling-2-small-vercel` | Vercel AI Gateway | — | — |
| `ling-3-1-flash-requesty` | Requesty | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-vercel` | Vercel AI Gateway | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `ling-3-1-flash-1019-vercel` | Vercel AI Gateway | — | — |
| `muse-spark-open-vercel` | Vercel AI Gateway | — | — |
| `mimo-v2-6-flash-vercel` | Vercel AI Gateway | — | — |
| `gemini-3-6-flash` | Gemini | `high` | — |
| `gpt-5-2-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-2-fast-vercel` | Vercel AI Gateway | — | — |
| `gemini-3-flash-preview` | Gemini | `high` | — |
| `kimi-k2-7-code-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-1-thinking-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-1-thinking-fast-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-fast-vercel` | Vercel AI Gateway | — | — |
| `qwen3-6-plus-vercel` | Vercel AI Gateway | — | — |
| `inkling-vercel` | Vercel AI Gateway | — | — |
| `o3-pro-vercel` | Vercel AI Gateway | — | — |
| `qwen3-5-plus-vercel` | Vercel AI Gateway | — | — |
| `o3-vercel` | Vercel AI Gateway | — | — |
| `o3-fast-vercel` | Vercel AI Gateway | — | — |
| `qwen3-6-27b-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-4-nano-vercel` | Vercel AI Gateway | — | — |
| `deepseek-v3-2-thinking-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-mini-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-mini-fast-vercel` | Vercel AI Gateway | — | — |
| `o4-mini-vercel` | Vercel AI Gateway | — | — |
| `gpt-oss-120b-groq` | Groq | défaut : medium | — |
| `gpt-oss-120b-cloudflare` | Cloudflare | défaut : medium | — |
| `gpt-oss-120b-vercel` | Vercel AI Gateway | — | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `gemma-4-31b-gemini` | Gemini | — | — |
| `gemma-4-31b-free` | OpenRouter | — | — |
| `gemma-4-31b-requesty` | Requesty | `high` | — |
| `gemma-4-31b-nvidia` | NVIDIA | — | — |
| `qwen3-6-35b-vercel` | Vercel AI Gateway | — | — |
| `qwen3-5-flash-vercel` | Vercel AI Gateway | — | — |
| `glm-4-7-vercel` | Vercel AI Gateway | — | — |
| `kimi-k2-vercel` | Vercel AI Gateway | — | — |
| `o1-vercel` | Vercel AI Gateway | — | — |
| `deepseek-v3-1-vercel` | Vercel AI Gateway | — | — |
| `gemini-2-5-flash-vercel` | Vercel AI Gateway | — | — |
| `o3-mini-vercel` | Vercel AI Gateway | — | — |
| `mistral-medium-3-5-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-nano-vercel` | Vercel AI Gateway | — | — |
| `particle-1-free` | OpenRouter | `xhigh` | — |
| `particle-1-kilo` | Kilo | `max` | — |
| `ernie-5-5-flash-free` | OpenRouter | `high` | — |
| `ernie-5-5-flash-kilo` | Kilo | `high` | — |
| `beam-kilo` | Kilo | — | — |
| `nemotron-super-vl-free` | OpenRouter | — | — |
| `nemotron-super-vl-nvidia` | NVIDIA | — | — |
| `nemotron-super-vl-vercel` | Vercel AI Gateway | — | — |
| `muse-glimmer-nvidia` | NVIDIA | — | — |
| `muse-glimmer-requesty` | Requesty | — | — |
| `nemotron-super-vl-kilo` | Kilo | — | — |
| `flint-free` | OpenRouter | — | — |
| `flint-kilo` | Kilo | — | — |
| `glyph-cluster-kilo` | Kilo | — | — |
| `dots-3-note-preview-free` | OpenRouter | — | — |
| `dots-3-note-preview-kilo` | Kilo | — | — |
| `openrouter-auto-free` | OpenRouter | — | dernier recours |
| `kilo-auto-free` | Kilo | — | — |
| `kilo-openrouter-free` | Kilo | — | — |
| `ling-3-2-flash-free` | OpenRouter | — | — |
| `ling-3-2-flash-kilo` | Kilo | — | — |
| `hy4-flash-cent-ai` | Cent AI | — | — |
| `qwen-3-14b-vercel` | Vercel AI Gateway | — | — |
| `qwen-3-30b-vercel` | Vercel AI Gateway | — | — |
| `qwen-3-32b-vercel` | Vercel AI Gateway | — | — |
| `qwen3-coder-30b-a3b-vercel` | Vercel AI Gateway | — | — |
| `qwen3-vl-instruct-vercel` | Vercel AI Gateway | — | — |
| `qwen3-7-flash-vercel` | Vercel AI Gateway | — | — |
| `qwen3-8-omni-flash-vercel` | Vercel AI Gateway | — | — |
| `nova-2-lite-vercel` | Vercel AI Gateway | — | — |
| `seed-2-1-turbo-vercel` | Vercel AI Gateway | — | — |
| `apex-vercel` | Vercel AI Gateway | — | — |
| `glimpse-vercel` | Vercel AI Gateway | — | — |
| `mercury-3-vercel` | Vercel AI Gateway | — | — |
| `ling-3-0-flash-fin-vercel` | Vercel AI Gateway | — | — |
| `ling-3-0-flash-sante-vercel` | Vercel AI Gateway | — | — |
| `ling-3-0-flash-vl-vercel` | Vercel AI Gateway | — | — |
| `schematron-v2-small-vercel` | Vercel AI Gateway | — | — |
| `schematron-v2-turbo-vercel` | Vercel AI Gateway | — | — |
| `interfaze-beta-vercel` | Vercel AI Gateway | — | — |
| `lfm2-5-24b-a2b-vercel` | Vercel AI Gateway | — | — |
| `longcat-2-5-vercel` | Vercel AI Gateway | — | — |
| `llama-3-1-70b-vercel` | Vercel AI Gateway | — | — |
| `llama-3-1-8b-vercel` | Vercel AI Gateway | — | — |
| `muse-ember-vercel` | Vercel AI Gateway | — | — |
| `minimax-m2-1-vercel` | Vercel AI Gateway | — | — |
| `codestral-vercel` | Vercel AI Gateway | — | — |
| `ministral-14b-vercel` | Vercel AI Gateway | — | — |
| `ministral-3b-vercel` | Vercel AI Gateway | — | — |
| `ministral-8b-vercel` | Vercel AI Gateway | — | — |
| `mistral-nemo-vercel` | Vercel AI Gateway | — | — |
| `toast-1-vercel` | Vercel AI Gateway | — | — |
| `morph-v3-fast-vercel` | Vercel AI Gateway | — | — |
| `morph-v3-large-vercel` | Vercel AI Gateway | — | — |
| `nemotron-3-super-120b-a12b-vercel` | Vercel AI Gateway | — | — |
| `nemotron-nano-12b-v2-vl-vercel` | Vercel AI Gateway | — | — |
| `nemotron-nano-9b-v2-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-1-codex-max-vercel` | Vercel AI Gateway | — | — |
| `gpt-oss-safeguard-120b-vercel` | Vercel AI Gateway | — | — |
| `gpt-oss-safeguard-20b-vercel` | Vercel AI Gateway | — | — |
| `ultramarine-1-flash-vercel` | Vercel AI Gateway | — | — |
| `sonar-vercel` | Vercel AI Gateway | — | — |
| `arrow-2-vercel` | Vercel AI Gateway | — | — |
| `arrow-2-telos-vercel` | Vercel AI Gateway | — | — |
| `flint-v1-0-vercel` | Vercel AI Gateway | — | — |
| `scaledown-summarize-1-vercel` | Vercel AI Gateway | — | — |
| `hy-mt2-lite-vercel` | Vercel AI Gateway | — | — |
| `hy-mt2-plus-vercel` | Vercel AI Gateway | — | — |
| `hy-mt2-pro-vercel` | Vercel AI Gateway | — | — |
| `hy4-flash-vercel` | Vercel AI Gateway | — | — |
| `glm-4-5-vercel` | Vercel AI Gateway | — | — |
| `glm-4-5v-vercel` | Vercel AI Gateway | — | — |
| `glm-4-6-vercel` | Vercel AI Gateway | — | — |
| `glm-4-7-flash-vercel` | Vercel AI Gateway | — | — |
| `glm-4-7-flashx-vercel` | Vercel AI Gateway | — | — |
| `glm-5v-turbo-vercel` | Vercel AI Gateway | — | — |
| `mistral-small-vercel` | Vercel AI Gateway | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | — | — |
| `llama-3-3-70b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-ovh` | OVHcloud | — | — |
| `qwen3-6-27b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| `qwen3-6-35b-ovh` | OVHcloud | — | — |
| `nemotron3-omni-30b-ovh` | OVHcloud | — | — |
| `mistral-small-3-2-ovh` | OVHcloud | — | — |
| `mistral-medium` | Mistral | — | — |
| `mistral-small` | Mistral | — | — |
| `ministral-14b` | Mistral | — | — |
| `ministral-8b` | Mistral | — | — |
| `deepseek-flash-direct` | DeepSeek | défaut : high | dernier recours |
| `omniroute-free-auto` | OmniRoute | — | dernier recours |

### `Auto-Flash-Lite`

- Classement : indice d'intelligence, moins le temps jusqu'au premier jeton de la réponse
- Quota partagé avec : `Auto-Pro`, `Auto-Flash` : un membre qui est le même modèle chez le même fournisseur que l'un de leurs membres passe en dernier
- Derniers recours : `ministral-3b`, `omniroute-free-fast`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-3-5-flash-lite` | Gemini | défaut : minimal | — |
| `gemini-3-1-flash-lite` | Gemini | défaut : minimal | — |
| `lfm-3-1-7b-free` | OpenRouter | — | — |
| `lfm-3-1-7b-kilo` | Kilo | — | — |
| `nemotron-lightning-free` | OpenRouter | — | — |
| `nemotron-lightning-requesty` | Requesty | — | — |
| `nemotron-lightning-nvidia` | NVIDIA | — | — |
| `nemotron-lightning-vercel` | Vercel AI Gateway | — | — |
| `nemotron-lightning-kilo` | Kilo | — | — |
| `gemini-2-5-flash-lite-vercel` | Vercel AI Gateway | — | — |
| `gpt-4-1-nano-vercel` | Vercel AI Gateway | — | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | — | — |
| `llama-4-scout-vercel` | Vercel AI Gateway | — | — |
| `llama-4-maverick-vercel` | Vercel AI Gateway | — | — |
| `nova-micro-vercel` | Vercel AI Gateway | — | — |
| `qwen3-next-80b-a3b-instruct-vercel` | Vercel AI Gateway | — | — |
| `qwen3-coder-next-vercel` | Vercel AI Gateway | — | — |
| `gpt-4-1-fast-vercel` | Vercel AI Gateway | — | — |
| `gpt-4-1-vercel` | Vercel AI Gateway | — | — |
| `gpt-4-1-mini-fast-vercel` | Vercel AI Gateway | — | — |
| `gpt-4-1-mini-vercel` | Vercel AI Gateway | — | — |
| `gemma-3-4b-nvidia` | NVIDIA | — | — |
| `gpt-4o-mini-fast-vercel` | Vercel AI Gateway | — | — |
| `gpt-4o-mini-vercel` | Vercel AI Gateway | — | — |
| `nova-lite-vercel` | Vercel AI Gateway | — | — |
| `gpt-4o-fast-vercel` | Vercel AI Gateway | — | — |
| `gpt-4o-vercel` | Vercel AI Gateway | — | — |
| `llama-3-3-70b-cloudflare` | Cloudflare | — | — |
| `llama-3-3-70b-vercel` | Vercel AI Gateway | — | — |
| `gemma-3-12b-nvidia` | NVIDIA | — | — |
| `nova-pro-vercel` | Vercel AI Gateway | — | — |
| `mistral-large-3-vercel` | Vercel AI Gateway | — | — |
| `command-a-vercel` | Vercel AI Gateway | — | — |
| `ling-3-0-flash-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-codex-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-1-codex-vercel` | Vercel AI Gateway | — | — |
| `gpt-5-1-codex-mini-vercel` | Vercel AI Gateway | — | — |
| `glm-4-5-air-vercel` | Vercel AI Gateway | — | — |
| `deepseek-r1-vercel` | Vercel AI Gateway | — | — |
| `step-3-7-flash-vercel` | Vercel AI Gateway | — | — |
| `minimax-m2-7-vercel` | Vercel AI Gateway | — | — |
| `minimax-m2-5-vercel` | Vercel AI Gateway | — | — |
| `hy3-vercel` | Vercel AI Gateway | — | — |
| `ling-3-1-flash-vercel` | Vercel AI Gateway | — | — |
| `gpt-oss-20b-groq` | Groq | défaut : medium | — |
| `gpt-oss-20b-cloudflare` | Cloudflare | défaut : medium | — |
| `gpt-oss-20b-vercel` | Vercel AI Gateway | — | — |
| `gemma-4-26b-gemini` | Gemini | — | — |
| `gemma-4-26b-free` | OpenRouter | — | — |
| `gemma-4-26b-vercel` | Vercel AI Gateway | — | — |
| `gemma-4-26b-cloudflare` | Cloudflare | — | — |
| `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | — | — |
| `phonellm-mini-alpha-2-cloudflare` | Cloudflare | — | — |
| `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | — | — |
| `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | — | — |
| `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | — | — |
| `mistral-7b-instruct-v0-2-lora-cloudflare` | Cloudflare | — | — |
| `granite-4-0-h-micro-cloudflare` | Cloudflare | — | — |
| `nemotron-bolt-e4b-nvidia` | NVIDIA | — | — |
| `nemotron-3-nano-30b-requesty` | Requesty | — | — |
| `gpt-oss-20b-ovh` | OVHcloud | — | — |
| `gemma-4-26b-ovh` | OVHcloud | — | — |
| `nemotron3-nano-30b-ovh` | OVHcloud | — | — |
| `qwen3-5-9b-ovh` | OVHcloud | — | — |
| `olala-mini-ovh` | OVHcloud | — | — |
| `gemini-3-8-flash-low` | Gemini | `low` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `gemini-4-hydrogen-low` | Gemini | `low` | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `hy4-flash-cent-ai` | Cent AI | — | — |
| `ministral-3b` | Mistral | — | dernier recours |
| `omniroute-free-fast` | OmniRoute | — | dernier recours |

### `Auto-Code`

- Classement : position dans les benchmarks de code
- Derniers recours : `deepseek-v4-pro-direct`, `omniroute-free-code`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `gemini-3-6-flash` | Gemini | `high` | — |
| `muse-glimmer-nvidia` | NVIDIA | — | — |
| `laguna-xs-2-1-nvidia` | NVIDIA | — | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | — | — |
| `glm-4-7-flash-zai` | Zai | — | — |
| `glm-4-5-flash-zai` | Zai | — | — |
| `phonellm-mini-alpha-2-cloudflare` | Cloudflare | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| `qwen3-6-35b-ovh` | OVHcloud | — | — |
| `laguna-xs-2-1-ovh` | OVHcloud | — | — |
| `codestral` | Mistral | — | — |
| `codestral-2508` | Mistral | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | défaut : high | dernier recours |
| `omniroute-free-code` | OmniRoute | — | dernier recours |

### `Auto-Claude-Code`

- Dérive de : `Auto-Code`, ordonné de la même façon, sans les membres qui ne répondent pas aux exigences ci-dessous
- Exige des membres : les appels d'outils

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `gemini-3-6-flash` | Gemini | `high` | — |
| `muse-glimmer-nvidia` | NVIDIA | — | — |
| `laguna-xs-2-1-nvidia` | NVIDIA | — | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | — | — |
| `glm-4-7-flash-zai` | Zai | — | — |
| `glm-4-5-flash-zai` | Zai | — | — |
| `phonellm-mini-alpha-2-cloudflare` | Cloudflare | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| `codestral` | Mistral | — | — |
| `codestral-2508` | Mistral | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | défaut : high | — |

### `Auto-STT`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `whisper-large-v3-groq` | Groq | — | — |
| `whisper-large-v3-turbo-groq` | Groq | — | — |
| `gemini-3-5-transcribe` | Gemini | — | — |
| `voxtral-mini-mistral` | Mistral | — | — |

### `Auto-TTS`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-3-8-flash-tts` | Gemini | — | — |
| `gemini-3-8-flash-lite-tts` | Gemini | — | — |

### `Auto-Decision`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `clef-cloudflare` | Cloudflare | — | — |
| `clef-omni-cloudflare` | Cloudflare | — | — |
| `clef-flash-cloudflare` | Cloudflare | — | — |

### `Auto-Extraction`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `clairic-cloudflare` | Cloudflare | — | — |
| `clairic-flash-cloudflare` | Cloudflare | — | — |

### `Auto-Fiction`

- Classement : indice d'intelligence

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `aion-3-5-aion-labs` | Aion Labs | — | — |
| `aion-3-5-mini-aion-labs` | Aion Labs | — | — |
| `aion-3-0-aion-labs` | Aion Labs | — | — |
| `aion-3-0-mini-aion-labs` | Aion Labs | — | — |
| `aion-2-0-aion-labs` | Aion Labs | — | — |
| `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | — | — |

### `Auto-Paid`

- Classement : indice d'intelligence

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `claude-fable-5-2-anthropic` | Anthropic | défaut : high | — |
| `claude-opus-5-5-anthropic` | Anthropic | défaut : medium | — |
| `claude-fable-5-1-anthropic` | Anthropic | défaut : high | — |
| `claude-sonnet-5-5-anthropic` | Anthropic | défaut : high | — |
| `claude-opus-5-anthropic` | Anthropic | — | — |
| `claude-fable-5-anthropic` | Anthropic | défaut : high | — |
| `claude-haiku-5-5-anthropic` | Anthropic | défaut : medium | — |
| `claude-opus-4-8-anthropic` | Anthropic | — | — |
| `claude-opus-4-7-anthropic` | Anthropic | — | — |
| `claude-sonnet-5-anthropic` | Anthropic | — | — |
| `claude-opus-4-6-anthropic` | Anthropic | — | — |
| `claude-sonnet-4-6-anthropic` | Anthropic | — | — |
| `claude-haiku-4-5-anthropic` | Anthropic | défaut : non-reasoning | — |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les fournisseurs

Un fournisseur est celui que lit l'entrée : la clé dont la variable est donnée, ou une passerelle qui n'en demande aucune. Un fournisseur dont la clé n'est pas donnée n'a aucune entrée dans la configuration rendue. La couleur de la pastille est celle du logo du fournisseur, et le générateur dit d'où chacune vient.

Les limites gratuites de chaque fournisseur, avec la page lue et le jour, sont dans [le tableau de ROUTAGE.md](../ROUTAGE.md#les-limites-gratuites-des-fournisseurs), et ce catalogue n'en garde pas de copie. Celles que le modèle de configuration fixe à une entrée, `rpm`, `tpm` et `rpd`, sont dans le tableau des modèles.

| Fournisseur | Variable de la clé |
| --- | --- |
| ![Gemini](https://img.shields.io/badge/Gemini-3186FF) Gemini | `Artificial_Intelligence_LiteLLM_Gemini_API_key` |
| ![Mistral](https://img.shields.io/badge/Mistral-FA500F) Mistral | `Artificial_Intelligence_LiteLLM_Mistral_API_key` |
| ![Groq](https://img.shields.io/badge/Groq-F43E01) Groq | `Artificial_Intelligence_LiteLLM_Groq_API_key` |
| ![OpenRouter](https://img.shields.io/badge/OpenRouter-7624F4) OpenRouter | `Artificial_Intelligence_LiteLLM_OpenRouter_API_key` |
| ![DeepSeek](https://img.shields.io/badge/DeepSeek-4D6BFE) DeepSeek | `Artificial_Intelligence_LiteLLM_DeepSeek_API_key` |
| ![Cloudflare](https://img.shields.io/badge/Cloudflare-F48220) Cloudflare | `Artificial_Intelligence_LiteLLM_Cloudflare_API_key` |
| ![Zai](https://img.shields.io/badge/Zai-808080) Zai | `Artificial_Intelligence_LiteLLM_Zai_API_key` |
| ![Requesty](https://img.shields.io/badge/Requesty-1677FF) Requesty | `Artificial_Intelligence_LiteLLM_Requesty_API_key` |
| ![NVIDIA](https://img.shields.io/badge/NVIDIA-76B900) NVIDIA | `Artificial_Intelligence_LiteLLM_NVIDIA_API_key` |
| ![Cent AI](https://img.shields.io/badge/Cent%20AI-FBBF24) Cent AI | `Artificial_Intelligence_LiteLLM_Cent_AI_API_key` |
| ![Aion Labs](https://img.shields.io/badge/Aion%20Labs-061929) Aion Labs | `Artificial_Intelligence_LiteLLM_Aion_Labs_API_key` |
| ![Vercel AI Gateway](https://img.shields.io/badge/Vercel%20AI%20Gateway-000000) Vercel AI Gateway | `Artificial_Intelligence_LiteLLM_Vercel_AI_Gateway_API_key` |
| ![Anthropic](https://img.shields.io/badge/Anthropic-D97757) Anthropic | `Artificial_Intelligence_LiteLLM_Anthropic_API_key` |
| ![Kilo](https://img.shields.io/badge/Kilo-FFDD00) Kilo | sans clé |
| ![OVHcloud](https://img.shields.io/badge/OVHcloud-000E9C) OVHcloud | sans clé |
| ![OmniRoute](https://img.shields.io/badge/OmniRoute-E54D5E) OmniRoute | sans clé |

### ![Gemini](https://img.shields.io/badge/Gemini-3186FF) Gemini

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Gemini_API_key`
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-STT`, `Auto-TTS`

### ![Mistral](https://img.shields.io/badge/Mistral-FA500F) Mistral

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Mistral_API_key`
- Routeurs où il figure : `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-STT`

### ![Groq](https://img.shields.io/badge/Groq-F43E01) Groq

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Groq_API_key`
- Routeurs où il figure : `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-STT`

### ![OpenRouter](https://img.shields.io/badge/OpenRouter-7624F4) OpenRouter

- Variable de la clé : `Artificial_Intelligence_LiteLLM_OpenRouter_API_key`
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`

### ![DeepSeek](https://img.shields.io/badge/DeepSeek-4D6BFE) DeepSeek

- Variable de la clé : `Artificial_Intelligence_LiteLLM_DeepSeek_API_key`
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code`

### ![Cloudflare](https://img.shields.io/badge/Cloudflare-F48220) Cloudflare

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Cloudflare_API_key`
- Routeurs où il figure : `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-Decision`, `Auto-Extraction`

### ![Zai](https://img.shields.io/badge/Zai-808080) Zai

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Zai_API_key`
- Routeurs où il figure : `Auto-Code`, `Auto-Claude-Code`

### ![Requesty](https://img.shields.io/badge/Requesty-1677FF) Requesty

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Requesty_API_key`
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`

### ![NVIDIA](https://img.shields.io/badge/NVIDIA-76B900) NVIDIA

- Variable de la clé : `Artificial_Intelligence_LiteLLM_NVIDIA_API_key`
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`

### ![Cent AI](https://img.shields.io/badge/Cent%20AI-FBBF24) Cent AI

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Cent_AI_API_key`
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`

### ![Aion Labs](https://img.shields.io/badge/Aion%20Labs-061929) Aion Labs

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Aion_Labs_API_key`
- Routeurs où il figure : `Auto-Fiction`

### ![Vercel AI Gateway](https://img.shields.io/badge/Vercel%20AI%20Gateway-000000) Vercel AI Gateway

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Vercel_AI_Gateway_API_key`
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`

### ![Anthropic](https://img.shields.io/badge/Anthropic-D97757) Anthropic

- Variable de la clé : `Artificial_Intelligence_LiteLLM_Anthropic_API_key`
- Routeurs où il figure : `Auto-Paid`

### ![Kilo](https://img.shields.io/badge/Kilo-FFDD00) Kilo

- Variable de la clé : aucune, il est sans clé
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`

### ![OVHcloud](https://img.shields.io/badge/OVHcloud-000E9C) OVHcloud

- Variable de la clé : aucune, il est sans clé
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`

### ![OmniRoute](https://img.shields.io/badge/OmniRoute-E54D5E) OmniRoute

- Variable de la clé : aucune, il est sans clé
- Routeurs où il figure : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les modèles

Une ligne par entrée de la liste des modèles, dans l'ordre du modèle. La fenêtre de contexte et la réponse la plus longue sont celles que le fournisseur sert, `model_info.max_input_tokens` et `model_info.max_output_tokens`. Le niveau est le `reasoning_effort` que le modèle fixe, sinon celui auquel les contrats disent que le fournisseur appelle l'entrée par défaut. `rpm`, `tpm` et `rpd` sont les limites que le modèle de configuration pose à l'entrée, `litellm_params.rpm`, `tpm` et `rpd` : des requêtes par minute, des jetons par minute et des requêtes par jour, que LiteLLM applique à l'entrée. Un tiret veut dire qu'aucune source ne donne la valeur, ou que le modèle de configuration n'en fixe aucune : les limites d'un fournisseur entier sont dans [le tableau de ROUTAGE.md](../ROUTAGE.md#les-limites-gratuites-des-fournisseurs). Les scores d'Artificial Analysis et d'Epoch AI sont dans la section qui suit.

| Entrée | Fournisseur | Type | Groupes | Routeurs | Niveau | Contexte | Sortie max | rpm | tpm | rpd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | `xhigh` | 1 048 576 | 65 536 | 5 | 250 000 | 20 |
| `gemini-4-hydrogen-low` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | `low` | 1 048 576 | 65 536 | 5 | 250 000 | 20 |
| `gemini-3-8-flash` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | `high` | 1 048 576 | 65 536 | 5 | 250 000 | 20 |
| `gemini-3-8-flash-low` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | `low` | 1 048 576 | 65 536 | 5 | 250 000 | 20 |
| `gemini-3-7-flash` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code` | — | 1 048 576 | 65 536 | — | — | — |
| `gemini-3-6-flash` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | `high` | 1 048 576 | 65 536 | 5 | 250 000 | 20 |
| `gemini-3-5-flash-lite` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | défaut : minimal | 1 048 576 | 65 536 | 15 | 250 000 | 500 |
| `gemini-3-1-flash-lite` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | défaut : minimal | 1 048 576 | 65 536 | 15 | 250 000 | 500 |
| `gemini-3-flash-preview` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash` | `high` | 1 048 576 | 65 536 | 5 | 250 000 | 20 |
| `gemma-4-31b-gemini` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — | 30 | 16 000 | 14 400 |
| `gemma-4-26b-gemini` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | — | 30 | 16 000 | 14 400 |
| `gemini-flash-latest` | Gemini | chat | `LLM`, `Private-Data` | — | — | — | — | — | — | — |
| `gemini-flash-lite-latest` | Gemini | chat | `LLM`, `Private-Data` | — | — | — | — | — | — | — |
| `gemini-3-8-live` | Gemini | `realtime` | `LLM`, `Private-Data` | — | — | — | — | — | — | — |
| `gemini-3-8-live-extended-thinking` | Gemini | `realtime` | `LLM`, `Private-Data` | — | — | — | — | — | — | — |
| `gemini-3-1-flash-live-preview` | Gemini | `realtime` | `LLM`, `Private-Data` | — | — | — | — | — | — | — |
| `gemini-3-5-live-translate-preview` | Gemini | `realtime` | `LLM`, `Private-Data` | — | — | — | — | — | — | — |
| `gemini-embedding-2` | Gemini | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | 100 | 30 000 | 1 000 |
| `gemini-3-8-flash-tts` | Gemini | `audio_speech` | `TTS`, `Private-Data` | `Auto-TTS` | — | — | — | 3 | 10 000 | 10 |
| `gemini-3-8-flash-lite-tts` | Gemini | `audio_speech` | `TTS`, `Private-Data` | `Auto-TTS` | — | — | — | 3 | 10 000 | 10 |
| `gemini-3-5-transcribe` | Gemini | `audio_transcription` | `STT`, `Private-Data` | `Auto-STT` | — | — | — | 3 | 10 000 | 25 |
| `codestral` | Mistral | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 128 000 | — | — | — | — |
| `codestral-2508` | Mistral | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 128 000 | — | — | — | — |
| `mistral-medium` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — | — | — | — |
| `mistral-small` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — | — | — | — |
| `ministral-14b` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — | — | — | — |
| `ministral-8b` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — | — | — | — |
| `ministral-3b` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | — | — | — | — |
| `mistral-embed` | Mistral | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `codestral-embed` | Mistral | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `voxtral-mini-mistral` | Mistral | `audio_transcription` | `STT`, `Private-Data` | `Auto-STT` | — | — | — | — | — | — |
| `voxtral-mini-tts-mistral` | Mistral | `audio_speech` | `TTS`, `Private-Data` | — | — | — | — | — | — | — |
| `gpt-oss-120b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | défaut : medium | 131 072 | 65 536 | 30 | 8 000 | 1 000 |
| `gpt-oss-20b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | défaut : medium | 131 072 | 65 536 | 30 | 8 000 | 1 000 |
| `qwen3-8-27b-groq` | Groq | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code` | défaut : non-reasoning | 131 072 | 16 384 | 30 | 8 000 | 1 000 |
| `whisper-large-v3-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | `Auto-STT` | — | — | — | 20 | — | 2 000 |
| `whisper-large-v3-turbo-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | `Auto-STT` | — | — | — | 20 | — | 2 000 |
| `orpheus-v1-english-groq` | Groq | `audio_speech` | `TTS`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `orpheus-arabic-saudi-groq` | Groq | `audio_speech` | `TTS`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Code`, `Auto-Claude-Code` | défaut : high | 1 000 000 | 393 216 | — | — | — |
| `deepseek-flash-direct` | DeepSeek | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | défaut : high | 1 000 000 | 393 216 | — | — | — |
| `nemotron-ultra-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `high` | 1 000 000 | 65 536 | — | — | — |
| `nemotron-reasoning-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 256 000 | 65 536 | — | — | — |
| `nemotron-lightning-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 000 000 | 65 536 | — | — | — |
| `nemotron-super-vl-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 000 000 | 131 072 | — | — | — |
| `gemma-4-31b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 32 768 | — | — | — |
| `gemma-4-26b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 32 768 | — | — | — |
| `openrouter-auto-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | — | — | — | — | — |
| `particle-1-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `xhigh` | 1 048 576 | 131 072 | — | — | — |
| `ernie-5-5-flash-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `high` | 1 024 000 | 921 600 | — | — | — |
| `lfm-3-1-7b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 8 192 | — | — | — |
| `dots-3-note-preview-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 512 000 | 460 800 | — | — | — |
| `flint-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 235 929 | — | — | — |
| `ling-3-2-flash-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 048 576 | 262 144 | — | — | — |
| `nemotron-3-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-3-5-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-3-5-embed-8b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `gpt-oss-120b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash` | défaut : medium | 128 000 | — | — | — | — |
| `gpt-oss-20b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | défaut : medium | 128 000 | — | — | — | — |
| `gemma-4-26b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 256 000 | — | — | — | — |
| `llama-3-3-70b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 24 000 | — | — | — | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 131 072 | — | — | — | — |
| `phonellm-mini-alpha-2-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code` | — | 262 140 | — | — | — | — |
| `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — | — | — | — |
| `clef-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — | — | — | — |
| `clef-omni-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — | — | — | — |
| `clef-flash-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — | — | — | — |
| `clairic-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | `Auto-Extraction` | — | — | — | — | — | — |
| `clairic-flash-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | `Auto-Extraction` | — | — | — | — | — | — |
| `granite-4-0-h-micro-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 000 | — | — | — | — |
| `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — | — | — | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 000 | — | — | — | — |
| `mistral-7b-instruct-v0-2-lora-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 15 000 | — | — | — | — |
| `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — | — | — | — |
| `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 32 768 | — | — | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | défaut : xhigh | 262 144 | — | — | — | — |
| `bge-m3-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `embeddinggemma-2-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `qwen3-embedding-0-6b-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `plamo-embedding-1b-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `bge-small-en-v1-5-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `bge-base-en-v1-5-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `bge-large-en-v1-5-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `glm-4-7-flash-zai` | Zai | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 200 000 | 128 000 | — | — | — |
| `glm-4-5-flash-zai` | Zai | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 128 000 | 96 000 | — | — | — |
| `glm-4-6v-flash-zai` | Zai | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-ultra-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `high` | 1 000 000 | 65 536 | — | — | — |
| `nemotron-reasoning-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 256 000 | 65 536 | — | — | — |
| `nemotron-lightning-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 000 000 | 65 536 | — | — | — |
| `nemotron-super-vl-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 000 000 | 131 072 | — | — | — |
| `particle-1-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `max` | 1 048 576 | 131 072 | — | — | — |
| `ernie-5-5-flash-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `high` | 1 024 000 | 921 600 | — | — | — |
| `lfm-3-1-7b-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 8 192 | — | — | — |
| `beam-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | 131 072 | — | — | — |
| `flint-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 235 929 | — | — | — |
| `glyph-cluster-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 256 000 | — | — | — |
| `dots-3-note-preview-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 512 000 | 460 800 | — | — | — |
| `kilo-auto-free` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 32 768 | — | — | — |
| `kilo-openrouter-free` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | — | — | — | — |
| `ling-3-2-flash-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 048 576 | 262 144 | — | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Pro`, `Auto-Flash`, `Auto-Code` | — | 1 048 576 | 262 144 | — | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Pro`, `Auto-Flash`, `Auto-Code` | — | 262 144 | 262 144 | — | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Pro`, `Auto-Flash`, `Auto-Code` | — | 131 072 | 131 072 | — | — | — |
| `qwen3-8-27b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash`, `Auto-Code` | — | 262 144 | 262 144 | — | — | — |
| `qwen3-6-35b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash`, `Auto-Code` | — | 262 144 | 65 536 | — | — | — |
| `nemotron3-omni-30b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 131 072 | 65 536 | — | — | — |
| `mistral-small-3-2-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `gpt-oss-20b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 072 | 65 536 | — | — | — |
| `gemma-4-26b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | 65 536 | — | — | — |
| `nemotron3-nano-30b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | 65 536 | — | — | — |
| `qwen3-5-9b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | 65 536 | — | — | — |
| `olala-mini-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 32 768 | 16 384 | — | — | — |
| `laguna-xs-2-1-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Code` | — | 131 072 | 65 536 | — | — | — |
| `llama-3-3-70b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `qwen3-6-27b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | 262 144 | — | — | — |
| `olala-summarise-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | — | — | 32 768 | 16 384 | — | — | — |
| `olala-translate-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | — | — | 8 192 | 8 192 | — | — | — |
| `qwen3-vl-30b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | — | — | 32 768 | 16 384 | — | — | — |
| `qwen2-5-vl-72b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | — | — | 32 768 | 32 768 | — | — | — |
| `qwen3guard-gen-0-6b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | — | — | 32 768 | 16 384 | — | — | — |
| `qwen3guard-gen-8b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | — | — | 32 768 | 16 384 | — | — | — |
| `bge-m3-ovh` | OVHcloud | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `bge-multilingual-gemma2-ovh` | OVHcloud | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `qwen3-embedding-8b-ovh` | OVHcloud | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `whisper-large-v3-ovh` | OVHcloud | `audio_transcription` | `STT`, `Private-Data` | — | — | — | — | — | — | — |
| `whisper-large-v3-turbo-ovh` | OVHcloud | `audio_transcription` | `STT`, `Private-Data` | — | — | — | — | — | — | — |
| `nvr-tts-en-us-ovh` | OVHcloud | `audio_speech` | `TTS`, `Private-Data` | — | — | — | — | — | — | — |
| `nvr-tts-es-es-ovh` | OVHcloud | `audio_speech` | `TTS`, `Private-Data` | — | — | — | — | — | — | — |
| `nvr-tts-it-it-ovh` | OVHcloud | `audio_speech` | `TTS`, `Private-Data` | — | — | — | — | — | — | — |
| `nvr-tts-de-de-ovh` | OVHcloud | `audio_speech` | `TTS`, `Private-Data` | — | — | — | — | — | — | — |
| `nemotron-ultra-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `max` | 1 048 576 | 65 536 | — | — | — |
| `nemotron-reasoning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `max` | 131 072 | 20 480 | — | — | — |
| `nemotron-lightning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 048 576 | 65 536 | — | — | — |
| `gemma-4-31b-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `high` | 262 144 | 8 192 | — | — | — |
| `ling-3-1-flash-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 262 144 | 32 768 | — | — | — |
| `muse-glimmer-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 20 480 | — | — | — |
| `nemotron-3-nano-30b-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | — | — | — | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 1 048 576 | — | — | — | — |
| `mistral-large-4-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | défaut : high | 1 048 576 | — | — | — | — |
| `nemotron-ultra-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 1 048 576 | — | — | — | — |
| `nemotron-reasoning-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 262 144 | — | — | — | — |
| `nemotron-lightning-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 048 576 | — | — | — | — |
| `nemotron-super-vl-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | — | — | — | — |
| `nemotron-bolt-e4b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 65 536 | — | — | — | — |
| `glm-5-3-flash-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | défaut : max | — | — | — | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 1 000 000 | — | — | — | — |
| `step-5-preview-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 1 000 000 | 1 000 000 | — | — | — |
| `laguna-xs-2-1-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 262 144 | — | — | — | — |
| `muse-glimmer-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 131 072 | — | — | — | — |
| `gemma-4-31b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | — | — | — | — |
| `gemma-3-12b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | — | — | — | — | — |
| `gemma-3-4b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | — | — | — | — | — |
| `cosmos-reason2-8b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `ising-calibration-1-5-31b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `riva-translate-4b-instruct-v2-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemoguard-topic-control-8b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-safety-guard-8b-v3-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-3-5-content-safety-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `embed-qa-4-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemoretriever-1b-vlm-embed-v1-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nv-embedqa-1b-v1-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-3-5-embed-1b-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-3-5-embed-8b-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nv-embedqa-mistral-7b-v2-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `arctic-embed-l-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nvclip-nvidia` | NVIDIA | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `hy4-flash-cent-ai` | Cent AI | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` | — | 1 048 576 | — | — | — | — |
| `aion-3-5-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 262 144 | 32 768 | — | — | — |
| `aion-3-5-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 262 144 | 32 768 | — | — | — |
| `aion-3-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 | — | — | — |
| `aion-3-0-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 | — | — | — |
| `aion-2-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 | — | — | — |
| `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 32 768 | 32 768 | — | — | — |
| `muse-spark-open-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | 1 048 576 | — | — | — |
| `inkling-2-small-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | 262 144 | — | — | — |
| `mimo-v2-6-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | 131 072 | — | — | — |
| `ling-3-1-flash-1019-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 000 000 | 262 144 | — | — | — |
| `inkling-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 256 000 | — | — | — |
| `gpt-5-2-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-mini-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-4-nano-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `o3-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 100 000 | — | — | — |
| `o4-mini-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 100 000 | — | — | — |
| `qwen3-6-plus-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 64 000 | — | — | — |
| `qwen3-5-plus-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 64 000 | — | — | — |
| `qwen3-5-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 64 000 | — | — | — |
| `qwen3-6-35b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 65 536 | — | — | — |
| `deepseek-v3-2-thinking-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 8 000 | — | — | — |
| `deepseek-v3-1-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 163 840 | 128 000 | — | — | — |
| `kimi-k2-7-code-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 32 768 | — | — | — |
| `kimi-k2-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `glm-4-7-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 120 000 | — | — | — |
| `mistral-medium-3-5-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 256 000 | — | — | — |
| `gemini-2-5-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 65 535 | — | — | — |
| `gpt-oss-120b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `gpt-oss-20b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 131 072 | 8 192 | — | — | — |
| `gemini-2-5-flash-lite-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 048 576 | 65 535 | — | — | — |
| `gemma-4-26b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 131 072 | — | — | — |
| `nemotron-ultra-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 1 000 000 | 65 000 | — | — | — |
| `nemotron-super-vl-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | 1 048 576 | — | — | — |
| `nemotron-lightning-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 000 000 | 65 000 | — | — | — |
| `minimax-m3-1-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 000 000 | 524 288 | — | — | — |
| `llama-4-scout-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 8 192 | — | — | — |
| `llama-3-3-70b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 8 192 | — | — | — |
| `qwen-3-14b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 40 960 | 16 384 | — | — | — |
| `qwen-3-30b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 40 960 | 16 384 | — | — | — |
| `qwen-3-32b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 8 192 | — | — | — |
| `qwen3-coder-30b-a3b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 8 192 | — | — | — |
| `qwen3-coder-next-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 256 000 | 256 000 | — | — | — |
| `qwen3-next-80b-a3b-instruct-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 32 768 | — | — | — |
| `qwen3-vl-instruct-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 262 144 | — | — | — |
| `qwen3-6-27b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 256 000 | — | — | — |
| `qwen3-7-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 991 000 | 64 000 | — | — | — |
| `qwen3-8-omni-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 131 072 | — | — | — |
| `nova-2-lite-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 1 000 000 | — | — | — |
| `nova-lite-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 300 000 | 8 192 | — | — | — |
| `nova-micro-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 8 192 | — | — | — |
| `nova-pro-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 300 000 | 8 192 | — | — | — |
| `seed-2-1-turbo-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 262 144 | — | — | — |
| `apex-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 131 072 | — | — | — |
| `command-a-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 256 000 | 8 000 | — | — | — |
| `deepseek-r1-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 8 192 | — | — | — |
| `glimpse-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 220 000 | 4 096 | — | — | — |
| `mercury-3-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 131 072 | — | — | — |
| `ling-3-0-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 256 000 | 32 000 | — | — | — |
| `ling-3-0-flash-fin-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 32 000 | — | — | — |
| `ling-3-0-flash-sante-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 32 000 | — | — | — |
| `ling-3-0-flash-vl-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 32 000 | — | — | — |
| `ling-3-1-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 32 768 | — | — | — |
| `schematron-v2-small-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 4 096 | — | — | — |
| `schematron-v2-turbo-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 8 192 | — | — | — |
| `interfaze-beta-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 32 000 | — | — | — |
| `lfm2-5-24b-a2b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 8 200 | — | — | — |
| `longcat-2-5-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 048 576 | 131 072 | — | — | — |
| `llama-3-1-70b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 8 192 | — | — | — |
| `llama-3-1-8b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 8 192 | — | — | — |
| `llama-4-maverick-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 8 192 | — | — | — |
| `muse-ember-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 048 576 | 1 048 576 | — | — | — |
| `minimax-m2-1-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 204 800 | 131 072 | — | — | — |
| `minimax-m2-5-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 000 000 | 8 192 | — | — | — |
| `minimax-m2-7-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 204 800 | 131 072 | — | — | — |
| `codestral-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 4 000 | — | — | — |
| `ministral-14b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 256 000 | — | — | — |
| `ministral-3b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 4 000 | — | — | — |
| `ministral-8b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 4 000 | — | — | — |
| `mistral-large-3-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 256 000 | — | — | — |
| `mistral-nemo-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `toast-1-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 000 | 4 000 | — | — | — |
| `morph-v3-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 81 920 | 16 384 | — | — | — |
| `morph-v3-large-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 81 920 | 16 384 | — | — | — |
| `nemotron-3-super-120b-a12b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 32 000 | — | — | — |
| `nemotron-nano-12b-v2-vl-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `nemotron-nano-9b-v2-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `gpt-4-1-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 047 576 | 32 768 | — | — | — |
| `gpt-4-1-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 047 576 | 32 768 | — | — | — |
| `gpt-4-1-mini-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 047 576 | 32 768 | — | — | — |
| `gpt-4-1-mini-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 047 576 | 32 768 | — | — | — |
| `gpt-4-1-nano-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 047 576 | 32 768 | — | — | — |
| `gpt-4o-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 16 384 | — | — | — |
| `gpt-4o-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 16 384 | — | — | — |
| `gpt-4o-mini-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 16 384 | — | — | — |
| `gpt-4o-mini-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 16 384 | — | — | — |
| `gpt-5-codex-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-mini-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-nano-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-1-codex-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-1-codex-max-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-1-codex-mini-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-1-thinking-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-1-thinking-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-5-2-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 400 000 | 128 000 | — | — | — |
| `gpt-oss-safeguard-120b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 16 000 | — | — | — |
| `gpt-oss-safeguard-20b-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 16 000 | — | — | — |
| `o1-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 100 000 | — | — | — |
| `o3-fast-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 100 000 | — | — | — |
| `o3-mini-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 100 000 | — | — | — |
| `o3-pro-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 100 000 | — | — | — |
| `ultramarine-1-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 048 576 | 131 000 | — | — | — |
| `sonar-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 127 000 | 8 000 | — | — | — |
| `arrow-2-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `arrow-2-telos-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 131 072 | 131 072 | — | — | — |
| `flint-v1-0-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 262 144 | — | — | — |
| `scaledown-summarize-1-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 000 000 | 1 000 | — | — | — |
| `step-3-7-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 256 000 | 256 000 | — | — | — |
| `hy-mt2-lite-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 8 000 | 4 000 | — | — | — |
| `hy-mt2-plus-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 8 000 | 4 000 | — | — | — |
| `hy-mt2-pro-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 8 000 | 4 000 | — | — | — |
| `hy3-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 262 144 | — | — | — |
| `hy4-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 1 024 000 | 64 000 | — | — | — |
| `glm-4-5-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 128 000 | 96 000 | — | — | — |
| `glm-4-5-air-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 128 000 | 96 000 | — | — | — |
| `glm-4-5v-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 66 000 | 16 000 | — | — | — |
| `glm-4-6-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 96 000 | — | — | — |
| `glm-4-7-flash-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 131 000 | — | — | — |
| `glm-4-7-flashx-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 128 000 | — | — | — |
| `glm-5v-turbo-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 200 000 | 128 000 | — | — | — |
| `mistral-small-vercel` | Vercel AI Gateway | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 4 000 | — | — | — |
| `qwen3-embedding-0-6b-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `qwen3-embedding-4b-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `qwen3-embedding-8b-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `titan-embed-text-v2-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `embed-v4-0-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `embed-v5-0-fast-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `embed-v5-0-pro-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `gemini-embedding-001-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `text-embedding-005-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `text-multilingual-embedding-002-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `codestral-embed-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `mistral-embed-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-3-large-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-3-5-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-3-5-lite-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-4-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-4-large-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-4-lite-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-code-2-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-code-3-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-finance-2-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `voyage-law-2-vercel` | Vercel AI Gateway | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `claude-fable-5-2-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | défaut : high | 1 000 000 | 128 000 | — | — | — |
| `claude-opus-5-5-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | défaut : medium | 1 000 000 | 128 000 | — | — | — |
| `claude-fable-5-1-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | défaut : high | 1 000 000 | 128 000 | — | — | — |
| `claude-sonnet-5-5-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | défaut : high | 1 000 000 | 128 000 | — | — | — |
| `claude-opus-5-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | — | 1 000 000 | 128 000 | — | — | — |
| `claude-fable-5-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | défaut : high | 1 000 000 | 128 000 | — | — | — |
| `claude-haiku-5-5-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | défaut : medium | 1 000 000 | 128 000 | — | — | — |
| `claude-opus-4-8-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | — | 1 000 000 | 128 000 | — | — | — |
| `claude-opus-4-7-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | — | 1 000 000 | 128 000 | — | — | — |
| `claude-sonnet-5-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | — | 1 000 000 | 128 000 | — | — | — |
| `claude-opus-4-6-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | — | 1 000 000 | 128 000 | — | — | — |
| `claude-sonnet-4-6-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | — | 1 000 000 | 128 000 | — | — | — |
| `claude-haiku-4-5-anthropic` | Anthropic | chat | `LLM`, `Private-Data` | `Auto-Paid` | défaut : non-reasoning | 200 000 | 64 000 | — | — | — |
| `omniroute-free-auto` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | — | — | — | — | — |
| `omniroute-free-code` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Code` | — | — | — | — | — | — |
| `omniroute-free-reasoning` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | — | — | — | — | — |
| `omniroute-free-fast` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | — | — | — | — | — |
| `omniroute-free-vision` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `omniroute-vision` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `omniroute-multimodal` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `Auto` | LiteLLM | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |

### Les scores d'Artificial Analysis et d'Epoch AI

Les chiffres sont ceux d'Artificial Analysis et d'Epoch AI : l'enregistrement et le niveau d'Artificial Analysis, et le modèle d'Epoch AI, sont ceux que dit `.github/LiteLLM_router_contracts.yaml` de l'entrée. La CI ne peut lire aucun de ces deux sites : la vérification hebdomadaire des modèles les lit et réécrit [`docs/catalog_scores.json`](catalog_scores.json) dans chaque pull request qu'elle ouvre. La CI tient ce fichier à sa forme (des nombres, et des entrées du modèle de configuration) et ce catalogue à ce fichier. Jours de lecture : Artificial Analysis le jamais, Epoch AI le 2026-11-25. Un tiret veut dire qu'aucune source ne donne le chiffre : l'enregistrement est introuvable ou n'est pas celui du niveau où l'entrée est appelée, le modèle n'est pas à l'indice d'Epoch AI, ou moins de deux de ses benchmarks de code ont un score pour lui.

- **Indice AA** : l'indice d'intelligence de l'enregistrement, plus haut est meilleur.
- **Premier mot AA** : le temps moyen jusqu'au premier jeton de la réponse, en secondes, que le temps de réflexion compte.
- **ECI Epoch** : l'indice de capacités du modèle, plus haut est meilleur.
- **Position de code Epoch** : la médiane, en pour cent, de la position du modèle dans les benchmarks de code où il a un score, deux au moins, où 100 est le dernier : plus petit est meilleur.

Sources : Artificial Analysis (artificialanalysis.ai) et Epoch AI, benchmark data, CC BY 4.0.

| Entrée | Enregistrement AA | Indice AA | Premier mot AA (s) | Modèle Epoch | ECI Epoch | Position de code Epoch (%) |
| --- | --- | --- | --- | --- | --- | --- |
| `gemini-4-hydrogen` | `gemini-4-hydrogen` (`xhigh`) | — | — | `Gemini 4 Hydrogen` | 166,81 | 9,98 |
| `gemini-4-hydrogen-low` | `gemini-4-hydrogen-low` (`low`) | — | — | `Gemini 4 Hydrogen` | 166,81 | — |
| `gemini-3-8-flash` | `gemini-3-8-flash-medium` (`high`) | — | — | `Gemini 3.8 Flash` | 158,81 | 17,66 |
| `gemini-3-8-flash-low` | `gemini-3-8-flash-low` (`low`) | — | — | `Gemini 3.8 Flash` | 158,81 | — |
| `gemini-3-7-flash` | `gemini-3-7-flash` | — | — | `Gemini 3.7 Flash` | 158,4 | 46,05 |
| `gemini-3-6-flash` | `gemini-3-6-flash` (`high`) | — | — | `Gemini 3.6 Flash` | 155,24 | 71,78 |
| `gemini-3-5-flash-lite` | `gemini-3-5-flash-lite` (`minimal`) | — | — | `Gemini 3.5 Flash-Lite` | 145,63 | — |
| `gemini-3-1-flash-lite` | `gemini-3-1-flash-lite-preview` (`minimal`) | — | — | `Gemini 3.1 Flash-Lite` | 144,97 | — |
| `gemini-3-flash-preview` | `gemini-3-flash-reasoning` (`reasoning`) | — | — | `Gemini 3 Flash` | 152,35 | 26,9 |
| `gemma-4-31b-gemini` | `gemma-4-31b` | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `gemma-4-26b-gemini` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `mistral-medium` | `mistral-medium-3-5` | — | — | `Mistral Medium 3.5` | 141,58 | — |
| `mistral-small` | `mistral-small-4` | — | — | — | — | — |
| `ministral-14b` | `ministral-3-14b` | — | — | — | — | — |
| `ministral-8b` | `ministral-3-8b` | — | — | — | — | — |
| `ministral-3b` | `ministral-3-3b` | — | — | — | — | — |
| `gpt-oss-120b-groq` | `gpt-oss-120b` (`medium`) | — | — | `gpt-oss-120b` | 140,21 | 84,41 |
| `gpt-oss-20b-groq` | `gpt-oss-20b` (`medium`) | — | — | `gpt-oss-20b` | 134,89 | 89,84 |
| `qwen3-8-27b-groq` | `qwen3-8-27b-non-reasoning` (`non-reasoning`) | — | — | `Qwen 3.8 27B` | 152,63 | — |
| `deepseek-v4-pro-direct` | `deepseek-v4-pro-high` (`high`) | — | — | `DeepSeek V4 Pro 0813` | 155,96 | 22,19 |
| `deepseek-flash-direct` | `deepseek-v4-1-flash-1017-high` (`high`) | — | — | `DeepSeek V4.1 Flash 1017` | 159,41 | — |
| `nemotron-ultra-free` | `nvidia-nemotron-3-ultra-550b-a55b` (`reasoning`) | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-reasoning-free` | `nemotron-3-nano-omni-30b-a3b` | — | — | — | — | — |
| `nemotron-lightning-free` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `nemotron-super-vl-free` | `nemotron-3-5-super-vl` | — | — | — | — | — |
| `gemma-4-31b-free` | `gemma-4-31b` | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `gemma-4-26b-free` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `lfm-3-1-7b-free` | `lfm3-1-7b` | — | — | — | — | — |
| `gpt-oss-120b-cloudflare` | `gpt-oss-120b` (`medium`) | — | — | `gpt-oss-120b` | 140,21 | 84,41 |
| `gpt-oss-20b-cloudflare` | `gpt-oss-20b` (`medium`) | — | — | `gpt-oss-20b` | 134,89 | 89,84 |
| `gemma-4-26b-cloudflare` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `llama-3-3-70b-cloudflare` | `llama-3-3-instruct-70b` | — | — | `Llama 3.3 70B` | 126,18 | — |
| `glm-4-7-flash-cloudflare` | `glm-4-7-flash` | — | — | — | — | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | `llama-4-scout` | — | — | `Llama 4 Scout` | 127,75 | — |
| `qwen3-8-27b-cloudflare` | `qwen3-8-27b` (`xhigh`) | — | — | `Qwen 3.8 27B` | 152,63 | — |
| `glm-4-7-flash-zai` | `glm-4-7-flash` | — | — | — | — | — |
| `nemotron-ultra-kilo` | `nvidia-nemotron-3-ultra-550b-a55b` (`reasoning`) | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-reasoning-kilo` | `nemotron-3-nano-omni-30b-a3b` | — | — | — | — | — |
| `nemotron-lightning-kilo` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `nemotron-super-vl-kilo` | `nemotron-3-5-super-vl` | — | — | — | — | — |
| `lfm-3-1-7b-kilo` | `lfm3-1-7b` | — | — | — | — | — |
| `beam-kilo` | `reflection-beam` | — | — | `Beam 1.0` | 150,84 | — |
| `deepseek-v4-1-flash-ovh` | `deepseek-v4-1-flash-1017-high` | — | — | `DeepSeek V4.1 Flash 1017` | 159,41 | — |
| `gpt-oss-120b-ovh` | `gpt-oss-120b` | — | — | `gpt-oss-120b` | 140,21 | 84,41 |
| `qwen3-8-27b-ovh` | — | — | — | `Qwen 3.8 27B` | 152,63 | — |
| `nemotron3-omni-30b-ovh` | `nemotron-3-nano-omni-30b-a3b` | — | — | — | — | — |
| `gpt-oss-20b-ovh` | `gpt-oss-20b` | — | — | `gpt-oss-20b` | 134,89 | 89,84 |
| `gemma-4-26b-ovh` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `nemotron-ultra-requesty` | `nvidia-nemotron-3-ultra-550b-a55b` (`reasoning`) | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-reasoning-requesty` | `nemotron-3-nano-omni-30b-a3b` (`max`) | — | — | — | — | — |
| `nemotron-lightning-requesty` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `gemma-4-31b-requesty` | `gemma-4-31b` (`reasoning`) | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `ling-3-1-flash-requesty` | `ling-3-1-flash` | — | — | — | — | — |
| `muse-glimmer-requesty` | `muse-glimmer` | — | — | — | — | — |
| `kimi-k3-1-pro-nvidia` | `kimi-k3-1-pro` | — | — | `Kimi K3.1 Pro` | 161,2 | — |
| `mistral-large-4-nvidia` | `mistral-large-4` (`high`) | — | — | `Mistral Large 4` | 154,57 | — |
| `nemotron-ultra-nvidia` | `nvidia-nemotron-3-ultra-550b-a55b` | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-reasoning-nvidia` | `nemotron-3-nano-omni-30b-a3b` | — | — | — | — | — |
| `nemotron-lightning-nvidia` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `nemotron-super-vl-nvidia` | `nemotron-3-5-super-vl` | — | — | — | — | — |
| `glm-5-3-flash-nvidia` | `glm-5-3-flash` (`max`) | — | — | `GLM-5.3-Flash` | 153,77 | 68,29 |
| `minimax-m3-1-flash-nvidia` | `minimax-m3-1-flash` | — | — | — | — | — |
| `step-5-preview-nvidia` | `step-5` | — | — | — | — | — |
| `muse-glimmer-nvidia` | `muse-glimmer` | — | — | — | — | — |
| `gemma-4-31b-nvidia` | `gemma-4-31b` | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `gemma-3-12b-nvidia` | `gemma-3-12b` | — | — | — | — | — |
| `gemma-3-4b-nvidia` | `gemma-3-4b` | — | — | — | — | — |
| `muse-spark-open-vercel` | `muse-spark-open` | — | — | `Muse Spark Open` | 155,47 | — |
| `inkling-2-small-vercel` | `inkling-2-small` | — | — | — | — | — |
| `mimo-v2-6-flash-vercel` | `mimo-v2-6-flash` | — | — | — | — | — |
| `ling-3-1-flash-1019-vercel` | `ling-3-1-flash` | — | — | — | — | — |
| `inkling-vercel` | `inkling` | — | — | `Inkling` | 148,39 | — |
| `gpt-5-2-vercel` | `gpt-5-2` | — | — | `GPT-5.2` | 154,53 | 31,72 |
| `gpt-5-vercel` | `gpt-5` | — | — | `GPT-5` | 150 | 40 |
| `gpt-5-mini-vercel` | `gpt-5-mini` | — | — | `GPT-5 mini` | 146,04 | 66,1 |
| `gpt-5-4-nano-vercel` | `gpt-5-4-nano` | — | — | `GPT-5.4 Nano` | 146,36 | — |
| `o3-vercel` | `o3` | — | — | `o3` | 147,02 | 68,98 |
| `o4-mini-vercel` | `o4-mini` | — | — | `o4-mini` | 145,21 | — |
| `qwen3-6-plus-vercel` | `qwen3-6-plus` | — | — | `Qwen 3.6 Plus` | 148,87 | 81,66 |
| `qwen3-5-plus-vercel` | — | — | — | `Qwen 3.5 Plus (hosted 397B-A17B)` | 147,29 | — |
| `qwen3-5-flash-vercel` | — | — | — | `Qwen 3.5 Flash (hosted 35B-A3B)` | 143,83 | — |
| `qwen3-6-35b-vercel` | — | — | — | `Qwen 3.6 35B-A3B` | 144,07 | — |
| `deepseek-v3-2-thinking-vercel` | `deepseek-v3-2-reasoning` | — | — | `DeepSeek-V3.2` | 146,26 | — |
| `deepseek-v3-1-vercel` | `deepseek-v3-1-reasoning` | — | — | `DeepSeek-V3.1` | 140,88 | — |
| `kimi-k2-7-code-vercel` | `kimi-k2-7-code` | — | — | `Kimi K2.7 Code` | 151,17 | 73,89 |
| `kimi-k2-vercel` | `kimi-k2` | — | — | `Kimi K2 (Jul 2025)` | 141,27 | — |
| `glm-4-7-vercel` | `glm-4-7` | — | — | `GLM-4.7` | 143,34 | 77,35 |
| `mistral-medium-3-5-vercel` | `mistral-medium-3-5` | — | — | `Mistral Medium 3.5` | 141,58 | — |
| `gemini-2-5-flash-vercel` | `gemini-2-5-flash-reasoning` | — | — | `Gemini 2.5 Flash (Jun 2025)` | 140,79 | 83,16 |
| `gpt-oss-120b-vercel` | `gpt-oss-120b` | — | — | `gpt-oss-120b` | 140,21 | 84,41 |
| `gpt-oss-20b-vercel` | `gpt-oss-20b` | — | — | `gpt-oss-20b` | 134,89 | 89,84 |
| `gemini-2-5-flash-lite-vercel` | `gemini-2-5-flash-lite` | — | — | `Gemini 2.5 Flash-Lite (Jun 2025)` | 133,04 | — |
| `gemma-4-26b-vercel` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `nemotron-ultra-vercel` | `nvidia-nemotron-3-ultra-550b-a55b` | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-super-vl-vercel` | `nemotron-3-5-super-vl` | — | — | — | — | — |
| `nemotron-lightning-vercel` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `minimax-m3-1-flash-vercel` | `minimax-m3-1-flash` | — | — | — | — | — |
| `llama-4-scout-vercel` | `llama-4-scout` | — | — | `Llama 4 Scout` | 127,75 | — |
| `llama-3-3-70b-vercel` | `llama-3-3-instruct-70b` | — | — | `Llama 3.3 70B` | 126,18 | — |
| `qwen-3-14b-vercel` | — | — | — | `Qwen3-14B` | 136,06 | — |
| `qwen-3-30b-vercel` | — | — | — | `Qwen3-30B-A3B` | 134,16 | — |
| `qwen-3-32b-vercel` | — | — | — | `Qwen3-32B` | 136,85 | — |
| `qwen3-coder-next-vercel` | `qwen3-coder-next` | — | — | — | — | — |
| `qwen3-next-80b-a3b-instruct-vercel` | `qwen3-next-80b-a3b-instruct` | — | — | — | — | — |
| `qwen3-6-27b-vercel` | `qwen3-6-27b` | — | — | `Qwen3.6 27B` | 146,72 | — |
| `nova-lite-vercel` | `nova-lite` | — | — | — | — | — |
| `nova-micro-vercel` | `nova-micro` | — | — | — | — | — |
| `nova-pro-vercel` | `nova-pro` | — | — | — | — | — |
| `command-a-vercel` | `command-a` | — | — | — | — | — |
| `deepseek-r1-vercel` | `deepseek-r1-0120` | — | — | `DeepSeek-R1` | 138,62 | — |
| `ling-3-0-flash-vercel` | `ling-3-0-flash` | — | — | — | — | — |
| `ling-3-0-flash-fin-vercel` | `ling-3-0-flash-fin` | — | — | — | — | — |
| `ling-3-0-flash-vl-vercel` | `ling-3-0-flash-vl` | — | — | — | — | — |
| `ling-3-1-flash-vercel` | `ling-3-1-flash-1001` | — | — | — | — | — |
| `llama-3-1-70b-vercel` | — | — | — | `Llama 3.1-70B` | 124,7 | — |
| `llama-3-1-8b-vercel` | — | — | — | `Llama 3.1-8B` | 110,9 | — |
| `llama-4-maverick-vercel` | `llama-4-maverick` | — | — | `Llama 4 Maverick` | 132,19 | — |
| `muse-ember-vercel` | `muse-ember` | — | — | — | — | — |
| `minimax-m2-1-vercel` | `minimax-m2-1` | — | — | — | — | — |
| `minimax-m2-5-vercel` | `minimax-m2-5` | — | — | — | — | — |
| `minimax-m2-7-vercel` | `minimax-m2-7` | — | — | — | — | — |
| `mistral-large-3-vercel` | `mistral-large-3` | — | — | — | — | — |
| `mistral-nemo-vercel` | — | — | — | `Mistral NeMo` | 113,87 | — |
| `gpt-4-1-vercel` | `gpt-4-1` | — | — | `GPT-4.1` | 136,14 | — |
| `gpt-4-1-fast-vercel` | `gpt-4-1` | — | — | `GPT-4.1` | 136,14 | — |
| `gpt-4-1-mini-vercel` | `gpt-4-1-mini` | — | — | `GPT-4.1 mini` | 134,24 | — |
| `gpt-4-1-mini-fast-vercel` | `gpt-4-1-mini` | — | — | `GPT-4.1 mini` | 134,24 | — |
| `gpt-4-1-nano-vercel` | `gpt-4-1-nano` | — | — | `GPT-4.1 nano` | 126,79 | — |
| `gpt-4o-vercel` | `gpt-4o` | — | — | — | — | — |
| `gpt-4o-fast-vercel` | `gpt-4o` | — | — | — | — | — |
| `gpt-4o-mini-vercel` | `gpt-4o-mini` | — | — | `GPT-4o mini` | 123,81 | — |
| `gpt-4o-mini-fast-vercel` | `gpt-4o-mini` | — | — | `GPT-4o mini` | 123,81 | — |
| `gpt-5-codex-vercel` | `gpt-5-codex` | — | — | — | — | — |
| `gpt-5-fast-vercel` | `gpt-5` | — | — | `GPT-5` | 150 | — |
| `gpt-5-mini-fast-vercel` | `gpt-5-mini` | — | — | `GPT-5 mini` | 146,04 | — |
| `gpt-5-nano-vercel` | `gpt-5-nano` | — | — | `GPT-5 nano` | 139,07 | — |
| `gpt-5-1-codex-vercel` | `gpt-5-1-codex` | — | — | — | — | — |
| `gpt-5-1-codex-mini-vercel` | `gpt-5-1-codex-mini` | — | — | — | — | — |
| `gpt-5-1-thinking-vercel` | — | — | — | `GPT-5.1` | 150,93 | — |
| `gpt-5-1-thinking-fast-vercel` | — | — | — | `GPT-5.1` | 150,93 | — |
| `gpt-5-2-fast-vercel` | `gpt-5-2` | — | — | `GPT-5.2` | 154,53 | — |
| `o1-vercel` | `o1` | — | — | `o1` | 141,16 | — |
| `o3-fast-vercel` | `o3` | — | — | `o3` | 147,02 | — |
| `o3-mini-vercel` | `o3-mini` | — | — | `o3-mini` | 140,63 | — |
| `o3-pro-vercel` | `o3-pro` | — | — | `o3-pro` | 147,47 | — |
| `sonar-vercel` | `sonar` | — | — | — | — | — |
| `step-3-7-flash-vercel` | `step-3-7-flash` | — | — | — | — | — |
| `hy3-vercel` | `hy3` | — | — | — | — | — |
| `glm-4-5-air-vercel` | `glm-4-5-air` | — | — | — | — | — |
| `glm-4-5v-vercel` | `glm-4-5v` | — | — | — | — | — |
| `glm-4-6-vercel` | `glm-4-6` | — | — | — | — | — |
| `glm-4-7-flash-vercel` | `glm-4-7-flash` | — | — | — | — | — |
| `glm-5v-turbo-vercel` | `glm-5v-turbo` | — | — | — | — | — |
| `mistral-small-vercel` | `mistral-small-4` | — | — | — | — | — |
| `claude-fable-5-2-anthropic` | `claude-fable-5-2-high` (`high`) | — | — | `Claude Fable 5.2` | 173,4 | 6,79 |
| `claude-opus-5-5-anthropic` | `claude-opus-5-5-medium` (`medium`) | — | — | `Claude Opus 5.5` | 168,67 | 11,34 |
| `claude-fable-5-1-anthropic` | `claude-fable-5-1-high` (`high`) | — | — | `Claude Fable 5.1` | 167,06 | — |
| `claude-sonnet-5-5-anthropic` | `claude-sonnet-5-5-high` (`high`) | — | — | `Claude Sonnet 5.5` | 166,6 | 22,59 |
| `claude-opus-5-anthropic` | `claude-opus-5` | — | — | `Claude Opus 5` | 164,72 | 5,62 |
| `claude-fable-5-anthropic` | `claude-fable-5` (`high`) | — | — | `Claude Fable 5` | 164,18 | 13,52 |
| `claude-haiku-5-5-anthropic` | `claude-haiku-5-5-medium` (`medium`) | — | — | `Claude Haiku 5.5` | 160,33 | 31,7 |
| `claude-opus-4-8-anthropic` | `claude-opus-4-8` | — | — | `Claude Opus 4.8` | 159,9 | 35,33 |
| `claude-opus-4-7-anthropic` | `claude-opus-4-7` | — | — | `Claude Opus 4.7` | 157,49 | 5,08 |
| `claude-sonnet-5-anthropic` | `claude-sonnet-5` | — | — | `Claude Sonnet 5` | 156,9 | 42,12 |
| `claude-opus-4-6-anthropic` | `claude-opus-4-6-adaptive` | — | — | `Claude Opus 4.6` | 156,33 | 12,12 |
| `claude-sonnet-4-6-anthropic` | `claude-sonnet-4-6-adaptive` | — | — | `Claude Sonnet 4.6` | 152,85 | 38,16 |
| `claude-haiku-4-5-anthropic` | `claude-4-5-haiku` (`non-reasoning`) | — | — | `Claude Haiku 4.5` | 142,74 | 69,44 |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)
