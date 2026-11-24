<!--
SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
SPDX-License-Identifier: AGPL-3.0-only
-->

# Catalogue de la passerelle LiteLLM

> Ce fichier est généré par `python3 .github/scripts/generate_catalog.py` à partir du modèle de configuration de LiteLLM (`templates/LiteLLM_config.yaml.j2`) et des contrats des routeurs (`.github/LiteLLM_router_contracts.yaml`). Ne le modifiez pas à la main : la CI refuse un fichier qui n'est pas ce que ces sources produisent, et un changement de l'un ou de l'autre le régénère dans le même commit.

Ce catalogue dit tout ce que la passerelle sert : les groupes d'accès, les routeurs et leurs membres, les fournisseurs, et chaque modèle. Il décrit la configuration rendue avec la clé de tous les fournisseurs donnée.

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
  - [Les entrées qui ont un repli](#les-entrées-qui-ont-un-repli)
- [Les fournisseurs](#les-fournisseurs)
  - [Les quotas que déclarent les contrats](#les-quotas-que-déclarent-les-contrats)
- [Les modèles](#les-modèles)

## Les groupes d'accès et les types de LiteLLM

Chaque entrée est dans le groupe de son type, ce qui permet de limiter une clé virtuelle à un type de modèles dans l'interface de LiteLLM. Les groupes sont des étiquettes que ce dépôt pose sur les entrées (`model_info.access_groups`), alors que le type est le `model_info.mode` de LiteLLM, un ensemble borné : une entrée sans `mode` est un modèle de conversation. Un routeur suit sa tête : une clé qui atteint l'entrée atteint les routeurs dont elle est la tête.

| Groupe | Type LiteLLM | Usage | Entrées | Remarque |
| --- | --- | --- | --- | --- |
| `LLM` | chat (aucun `mode`) | Texte : conversation et complétion | 99 | — |
| `STT` | `audio_transcription` | Transcription de la parole (`/audio/transcriptions`) | 4 | — |
| `TTS` | `audio_speech` | Synthèse vocale (`/audio/speech`) | 2 | — |
| `Embeddings` | `embedding` | Vecteurs d'un texte (`/embeddings`) | 6 | — |
| `Decisions` | `evaluation` | Décisions typées | 3 | — |
| `Extraction` | `extraction` | Extraction typée | 2 | — |
| `Images` | `image_generation` | Génération d'images (`/images/generations`) | 0 | — |
| `Videos` | `video_generation` | Génération de vidéos (`/videos`) | 0 | — |
| `Rerank` | `rerank` | Reclassement de documents (`/rerank`) | 0 | — |
| `Moderation` | `moderation` | Modération de contenu (`/moderations`) | 0 | — |
| `OCR` | `ocr` | Lecture du texte d'une image ou d'un PDF (`/ocr`) | 0 | — |
| `Fiction` | chat (aucun `mode`) | Texte : conversation et complétion | 6 | mis à part : seules les entrées qui lisent la clé de Aion Labs en font partie, et aucune clé qui n'a que `LLM` ne les atteint |

Ces groupes s'ajoutent au groupe du type : une entrée qui en porte un est aussi dans celui de son type.

| Groupe supplémentaire | Entrées | Groupes de type des entrées |
| --- | --- | --- |
| `Private-Data` | 64 | `Decisions`, `Embeddings`, `Extraction`, `Fiction`, `LLM`, `STT`, `TTS` |
| `Public-Data-Only` | 58 | `Embeddings`, `LLM`, `STT` |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les routeurs

Un routeur est un nom que le client écrit et derrière lequel LiteLLM essaie les membres de sa cascade dans l'ordre, en passant au suivant quand un membre échoue. Les cascades ci-dessous sont celles du modèle rendu avec la clé de tous les fournisseurs : sans la clé d'un fournisseur, ses entrées disparaissent et l'ordre des autres ne change pas. Le rôle d'un routeur est la première phrase du commentaire qui ouvre sa cascade dans le modèle, en anglais comme lui ; le reste vient des contrats des routeurs.

| Routeur | Rôle | Tête | Membres |
| --- | --- | --- | --- |
| `Auto` | Aiguille chaque requête vers `Auto-Flash-Lite`, `Auto-Flash`, `Auto-Pro` selon sa complexité | — | — |
| `Auto-Pro` | Pure reasoning, multi-step logic, architecture | `gemini-4-hydrogen` | 26 |
| `Auto-Flash` | Balanced daily driver | `gemini-4-hydrogen` | 47 |
| `Auto-Flash-Lite` | Simple, short asks | `gemini-3-5-flash-lite` | 36 |
| `Auto-Code` | Refactoring, Ansible playbooks, Bash/Python scripts | `gemini-4-hydrogen` | 26 |
| `Auto-Claude-Code` | 100% agentic CLI (strict tool/function calling, 128k+ context) | `gemini-4-hydrogen` | 19 |
| `Auto-STT` | Speech to text, for "/audio/transcriptions" | `whisper-large-v3-groq` | 4 |
| `Auto-TTS` | Text to speech, for /audio/speech | `gemini-3-8-flash-tts` | 2 |
| `Auto-Decision` | Clef's typed decisions, for "/v1/systemone" and "/v1/decisions" | `clef-cloudflare` | 3 |
| `Auto-Extraction` | Clairic's typed extraction, for "/v1/extraction" | `clairic-cloudflare` | 2 |
| `Auto-Fiction` | The role-play and fiction models of Aion Labs, and only those | `aion-3-5-aion-labs` | 6 |

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

| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Gemini | `high` | — |
| 2 | `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| 3 | `gemini-3-8-flash` | Gemini | `medium` | — |
| 4 | `gemini-3-7-flash` | Gemini | — | — |
| 5 | `step-5-preview-nvidia` | NVIDIA | — | — |
| 6 | `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| 7 | `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| 8 | `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| 9 | `beam-kilo` | Kilo | — | — |
| 10 | `nemotron-ultra-free` | OpenRouter | — | — |
| 11 | `nemotron-ultra-requesty` | Requesty | — | — |
| 12 | `nemotron-ultra-nvidia` | NVIDIA | — | — |
| 13 | `nemotron-ultra-kilo` | Kilo | — | — |
| 14 | `nemotron-reasoning-free` | OpenRouter | — | — |
| 15 | `nemotron-reasoning-requesty` | Requesty | — | — |
| 16 | `nemotron-reasoning-nvidia` | NVIDIA | — | — |
| 17 | `nemotron-reasoning-kilo` | Kilo | — | — |
| 18 | `nemotron-super-vl-free` | OpenRouter | — | — |
| 19 | `nemotron-super-vl-nvidia` | NVIDIA | — | — |
| 20 | `nemotron-super-vl-kilo` | Kilo | — | — |
| 21 | `hy4-flash-cent-ai` | Cent AI | — | — |
| 22 | `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| 23 | `qwen3-5-397b-ovh` | OVHcloud | — | — |
| 24 | `gpt-oss-120b-ovh` | OVHcloud | — | — |
| 25 | `deepseek-v4-pro-direct` | DeepSeek | défaut : high | dernier recours |
| 26 | `omniroute-free-reasoning` | OmniRoute | — | dernier recours |

### `Auto-Flash`

- Classement : indice d'intelligence
- Derniers recours : `deepseek-flash-direct`, `omniroute-free-auto`, `openrouter-auto-free`

| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Gemini | `high` | — |
| 2 | `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| 3 | `gemini-3-8-flash-low` | Gemini | `low` | — |
| 4 | `gemini-3-7-flash` | Gemini | — | — |
| 5 | `step-5-preview-nvidia` | NVIDIA | — | — |
| 6 | `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| 7 | `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| 8 | `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| 9 | `gemini-3-6-flash` | Gemini | défaut : medium | — |
| 10 | `gemini-3-flash-preview` | Gemini | défaut : reasoning | — |
| 11 | `gpt-oss-120b-groq` | Groq | défaut : medium | — |
| 12 | `gpt-oss-120b-cloudflare` | Cloudflare | défaut : medium | — |
| 13 | `gemini-2-5-flash` | Gemini | — | — |
| 14 | `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| 15 | `gemma-4-31b-gemini` | Gemini | — | — |
| 16 | `gemma-4-31b-free` | OpenRouter | — | — |
| 17 | `gemma-4-31b-requesty` | Requesty | — | — |
| 18 | `gemma-4-31b-nvidia` | NVIDIA | — | — |
| 19 | `particle-1-free` | OpenRouter | — | — |
| 20 | `particle-1-kilo` | Kilo | — | — |
| 21 | `ernie-5-5-flash-free` | OpenRouter | — | — |
| 22 | `ernie-5-5-flash-kilo` | Kilo | — | — |
| 23 | `beam-kilo` | Kilo | — | — |
| 24 | `nemotron-super-vl-free` | OpenRouter | — | — |
| 25 | `nemotron-super-vl-nvidia` | NVIDIA | — | — |
| 26 | `muse-glimmer-nvidia` | NVIDIA | — | — |
| 27 | `nemotron-super-vl-kilo` | Kilo | — | — |
| 28 | `flint-kilo` | Kilo | — | — |
| 29 | `glyph-cluster-kilo` | Kilo | — | — |
| 30 | `dots-3-note-preview-free` | OpenRouter | — | — |
| 31 | `dots-3-note-preview-kilo` | Kilo | — | — |
| 32 | `openrouter-auto-free` | OpenRouter | — | dernier recours |
| 33 | `hy4-flash-cent-ai` | Cent AI | — | — |
| 34 | `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| 35 | `qwen3-5-397b-ovh` | OVHcloud | — | — |
| 36 | `gpt-oss-120b-ovh` | OVHcloud | — | — |
| 37 | `qwen3-8-27b-ovh` | OVHcloud | — | — |
| 38 | `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| 39 | `qwen3-6-35b-ovh` | OVHcloud | — | — |
| 40 | `nemotron3-omni-30b-ovh` | OVHcloud | — | — |
| 41 | `mistral-small-3-2-ovh` | OVHcloud | — | — |
| 42 | `mistral-medium` | Mistral | — | — |
| 43 | `mistral-small` | Mistral | — | — |
| 44 | `ministral-14b` | Mistral | — | — |
| 45 | `ministral-8b` | Mistral | — | — |
| 46 | `deepseek-flash-direct` | DeepSeek | défaut : high | dernier recours |
| 47 | `omniroute-free-auto` | OmniRoute | — | dernier recours |

### `Auto-Flash-Lite`

- Classement : indice d'intelligence, moins le temps jusqu'au premier jeton de la réponse
- Quota partagé avec : `Auto-Pro`, `Auto-Flash` : un membre qui est le même modèle chez le même fournisseur que l'un de leurs membres passe en dernier
- Derniers recours : `ministral-3b`, `omniroute-free-fast`

| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `gemini-3-5-flash-lite` | Gemini | défaut : minimal | — |
| 2 | `gemini-3-1-flash-lite` | Gemini | défaut : minimal | — |
| 3 | `lfm-3-1-7b-free` | OpenRouter | — | — |
| 4 | `lfm-3-1-7b-kilo` | Kilo | — | — |
| 5 | `nemotron-lightning-free` | OpenRouter | — | — |
| 6 | `nemotron-lightning-requesty` | Requesty | — | — |
| 7 | `nemotron-lightning-nvidia` | NVIDIA | — | — |
| 8 | `nemotron-lightning-kilo` | Kilo | — | — |
| 9 | `gemini-2-5-flash-lite` | Gemini | défaut : non-reasoning | — |
| 10 | `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | — | — |
| 11 | `gemma-3-4b-nvidia` | NVIDIA | — | — |
| 12 | `llama-3-3-70b-cloudflare` | Cloudflare | — | — |
| 13 | `gemma-3-12b-nvidia` | NVIDIA | — | — |
| 14 | `gpt-oss-20b-groq` | Groq | défaut : medium | — |
| 15 | `gpt-oss-20b-cloudflare` | Cloudflare | défaut : medium | — |
| 16 | `gemma-4-26b-gemini` | Gemini | — | — |
| 17 | `gemma-4-26b-free` | OpenRouter | — | — |
| 18 | `gemma-4-26b-cloudflare` | Cloudflare | — | — |
| 19 | `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | — | — |
| 20 | `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | — | — |
| 21 | `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | — | — |
| 22 | `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | — | — |
| 23 | `granite-4-0-h-micro-cloudflare` | Cloudflare | — | — |
| 24 | `nemotron-bolt-e4b-nvidia` | NVIDIA | — | — |
| 25 | `gpt-oss-20b-ovh` | OVHcloud | — | — |
| 26 | `gemma-4-26b-ovh` | OVHcloud | — | — |
| 27 | `nemotron3-nano-30b-ovh` | OVHcloud | — | — |
| 28 | `qwen3-5-9b-ovh` | OVHcloud | — | — |
| 29 | `olala-mini-ovh` | OVHcloud | — | — |
| 30 | `gemini-3-8-flash-low` | Gemini | `low` | — |
| 31 | `gemini-3-7-flash` | Gemini | — | — |
| 32 | `gemini-4-hydrogen-low` | Gemini | `low` | — |
| 33 | `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| 34 | `hy4-flash-cent-ai` | Cent AI | — | — |
| 35 | `ministral-3b` | Mistral | — | dernier recours |
| 36 | `omniroute-free-fast` | OmniRoute | — | dernier recours |

### `Auto-Code`

- Classement : position dans les benchmarks de code
- Derniers recours : `deepseek-v4-pro-direct`, `omniroute-free-code`

| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Gemini | `high` | — |
| 2 | `gemini-3-8-flash` | Gemini | `medium` | — |
| 3 | `gemini-3-7-flash` | Gemini | — | — |
| 4 | `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| 5 | `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| 6 | `step-5-preview-nvidia` | NVIDIA | — | — |
| 7 | `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| 8 | `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| 9 | `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| 10 | `gemini-3-6-flash` | Gemini | défaut : medium | — |
| 11 | `muse-glimmer-nvidia` | NVIDIA | — | — |
| 12 | `gemini-2-5-flash` | Gemini | — | — |
| 13 | `laguna-xs-2-1-nvidia` | NVIDIA | — | — |
| 14 | `glm-4-7-flash-cloudflare` | Cloudflare | — | — |
| 15 | `glm-4-7-flash-zai` | Zai | — | — |
| 16 | `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| 17 | `qwen3-5-397b-ovh` | OVHcloud | — | — |
| 18 | `gpt-oss-120b-ovh` | OVHcloud | — | — |
| 19 | `qwen3-8-27b-ovh` | OVHcloud | — | — |
| 20 | `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| 21 | `qwen3-6-35b-ovh` | OVHcloud | — | — |
| 22 | `laguna-xs-2-1-ovh` | OVHcloud | — | — |
| 23 | `codestral` | Mistral | — | — |
| 24 | `codestral-2508` | Mistral | — | — |
| 25 | `deepseek-v4-pro-direct` | DeepSeek | défaut : high | dernier recours |
| 26 | `omniroute-free-code` | OmniRoute | — | dernier recours |

### `Auto-Claude-Code`

- Dérive de : `Auto-Code`, ordonné de la même façon, sans les membres qui ne répondent pas aux exigences ci-dessous
- Exige des membres : les appels d'outils

| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Gemini | `high` | — |
| 2 | `gemini-3-8-flash` | Gemini | `medium` | — |
| 3 | `gemini-3-7-flash` | Gemini | — | — |
| 4 | `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| 5 | `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| 6 | `step-5-preview-nvidia` | NVIDIA | — | — |
| 7 | `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| 8 | `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| 9 | `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| 10 | `gemini-3-6-flash` | Gemini | défaut : medium | — |
| 11 | `muse-glimmer-nvidia` | NVIDIA | — | — |
| 12 | `gemini-2-5-flash` | Gemini | — | — |
| 13 | `laguna-xs-2-1-nvidia` | NVIDIA | — | — |
| 14 | `glm-4-7-flash-cloudflare` | Cloudflare | — | — |
| 15 | `glm-4-7-flash-zai` | Zai | — | — |
| 16 | `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| 17 | `codestral` | Mistral | — | — |
| 18 | `codestral-2508` | Mistral | — | — |
| 19 | `deepseek-v4-pro-direct` | DeepSeek | défaut : high | — |

### `Auto-STT`


| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `whisper-large-v3-groq` | Groq | — | — |
| 2 | `whisper-large-v3-turbo-groq` | Groq | — | — |
| 3 | `gemini-3-5-transcribe` | Gemini | — | — |
| 4 | `voxtral-mini-mistral` | Mistral | — | — |

### `Auto-TTS`


| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `gemini-3-8-flash-tts` | Gemini | — | — |
| 2 | `gemini-3-8-flash-lite-tts` | Gemini | — | — |

### `Auto-Decision`


| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `clef-cloudflare` | Cloudflare | — | — |
| 2 | `clef-omni-cloudflare` | Cloudflare | — | — |
| 3 | `clef-flash-cloudflare` | Cloudflare | — | — |

### `Auto-Extraction`


| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `clairic-cloudflare` | Cloudflare | — | — |
| 2 | `clairic-flash-cloudflare` | Cloudflare | — | — |

### `Auto-Fiction`

- Classement : indice d'intelligence

| Rang | Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- | --- |
| 1 | `aion-3-5-aion-labs` | Aion Labs | — | — |
| 2 | `aion-3-5-mini-aion-labs` | Aion Labs | — | — |
| 3 | `aion-3-0-aion-labs` | Aion Labs | — | — |
| 4 | `aion-3-0-mini-aion-labs` | Aion Labs | — | — |
| 5 | `aion-2-0-aion-labs` | Aion Labs | — | — |
| 6 | `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | — | — |

### Les entrées qui ont un repli

Une entrée appelée par son nom, qui n'est la tête d'aucun routeur, et ce que LiteLLM essaie quand elle échoue.

| Entrée | Replis |
| --- | --- |
| `gemini-4-hydrogen-xhigh` | `gemini-4-hydrogen` |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les fournisseurs

Un fournisseur est celui que lit l'entrée : la clé dont la variable est donnée, ou une passerelle qui n'en demande aucune. Un fournisseur dont la clé n'est pas donnée n'a aucune entrée dans la configuration rendue.

| Fournisseur | Variable de la clé | Entrées | Routeurs où il figure |
| --- | --- | --- | --- |
| Gemini | `Artificial_Intelligence_LiteLLM_Gemini_API_key` | 18 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-STT`, `Auto-TTS` |
| Mistral | `Artificial_Intelligence_LiteLLM_Mistral_API_key` | 9 | `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-STT` |
| Groq | `Artificial_Intelligence_LiteLLM_Groq_API_key` | 5 | `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-STT` |
| OpenRouter | `Artificial_Intelligence_LiteLLM_OpenRouter_API_key` | 14 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` |
| DeepSeek | `Artificial_Intelligence_LiteLLM_DeepSeek_API_key` | 2 | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` |
| Cloudflare | `Artificial_Intelligence_LiteLLM_Cloudflare_API_key` | 18 | `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`, `Auto-Decision`, `Auto-Extraction` |
| Zai | `Artificial_Intelligence_LiteLLM_Zai_API_key` | 1 | `Auto-Code`, `Auto-Claude-Code` |
| Requesty | `Artificial_Intelligence_LiteLLM_Requesty_API_key` | 4 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` |
| NVIDIA | `Artificial_Intelligence_LiteLLM_NVIDIA_API_key` | 15 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code` |
| Cent AI | `Artificial_Intelligence_LiteLLM_Cent_AI_API_key` | 1 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` |
| Aion Labs | `Artificial_Intelligence_LiteLLM_Aion_Labs_API_key` | 6 | `Auto-Fiction` |
| Kilo | sans clé | 11 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` |
| OVHcloud | sans clé | 13 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code` |
| OmniRoute | sans clé | 4 | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code` |

### Les quotas que déclarent les contrats

Ce que dit `.github/LiteLLM_router_contracts.yaml`, tel quel, des limites de chaque fournisseur : ce sont des déclarations datées, qu'aucun contrôle ne vérifie.

- **Gemini** : Free tier, counted per Google project and per model, not per API key, and the daily quotas reset at midnight Pacific time, per ai.google.dev/gemini-api/docs/rate-limits (read 2026-11-22). The page of the rate limits of Google AI Studio for the gateway's project, free tier, read 2026-11-22, gives requests per minute / tokens per minute / requests per day per model: Gemini 4 Hydrogen, Gemini 3.8 Flash, Gemini 3.6 Flash, Gemini 3 Flash and Gemini 2.5 Flash 5 / 250K / 20; Gemini 3.5 Flash-Lite and Gemini 3.1 Flash-Lite 15 / 250K / 500; Gemini 2.5 Flash-Lite 10 / 250K / 20; Gemma 4 31B and Gemma 4 26B 30 / 16K / 14,400; Gemini Embedding 1 and 2 100 / 30K / 1,000; the text-to-speech models 3 / 10K / 10; Gemini 3.5 Transcribe 3 / 10K / 25; Gemini 3.1 Pro, Gemini 2.5 Pro and Gemini 4 Argon, Neon and Carbon 0, not served on the free tier; Gemini 3.7 Flash is not on that page. Every entry of one model draws on that model's quota: gemini-4-hydrogen, gemini-4-hydrogen-medium, gemini-4-hydrogen-low and gemini-4-hydrogen-xhigh share one 20 requests a day, and so do gemini-3-8-flash and gemini-3-8-flash-low
- **Mistral** : Paid, a prepaid balance: Free mode no longer includes the API, per docs.mistral.ai/admin/billing-usage/usage-limits (read 2026-11-21); per-model limits only in the account's admin panel
- **Groq** : Free plan, 30 requests and 8K tokens per minute for these models, per console.groq.com/docs/rate-limits as the template quotes it (checked 2026-09-27)
- **OpenRouter** : 20 requests per minute and 50 per day, 1000 once 10 credits are bought, counted across every :free model of the account together, per openrouter.ai/docs/api_reference/limits as the template quotes it (checked 2026-09-27)
- **DeepSeek** : No free quota: a prepaid balance, per api-docs.deepseek.com/faq as the template quotes it (checked 2026-09-27)
- **Cloudflare** : 10,000 neurons a day for the whole account, shared by all its models, and 300 requests per minute for text generation, per developers.cloudflare.com/workers-ai/platform/pricing/ and .../platform/limits/ (read 2026-11-22); the models routed are deduced free from the pricing page's list of paid ones, and confirmed on no account
- **Zai** : unknown: Z AI publishes no limit outside the account's console (docs.z.ai, read 2026-11-22), and the one-request-at-a-time limit a third party cites is not verified
- **Requesty** : 200 requests a day and 20 a minute for a new organization (1,000 and 60 for one that pays), counted across every free model of the organization together, per the Free models page of the Requesty docs (read 2026-11-22), which also says the models are free for now and that a change will be announced in the changelog ahead of time
- **NVIDIA** : 40 requests per minute, shown on the account page (read 2026-11-22); no credit count, daily cap or end date is shown there or on any other page read, the API trial terms of service included
- **Cent AI** : no limit stated: the home page says "Free until Nov 30 · no daily limit" (read 2026-11-22) and nothing of what follows the 30th, when the model may be billed; a spending limit set on the key keeps a billed call from costing anything, since the call then fails and the cascade moves on
- **Aion Labs** : 15 requests a minute, 20,000 tokens a minute and 20,000 tokens a day for the whole account, all models together, on the free tier of the Rate Limits page of its documentation (read 2026-11-23); its terms of 2026-10-17 call free use "a courtesy that we may change or withdraw at any time"
- **Kilo** : Anonymous, no key and no account: 200 requests per hour per IP address, for the free models only, per the Authentication and Models and providers pages of the Kilo gateway documentation (read 2026-11-22); the free models' availability changes, and each flags that prompts may be trained on
- **OVHcloud** : Anonymous, no key and no account: 2 requests per minute per IP address and per model, observed from the maintainer's network on 2026-11-22 (a second call within the minute answered 429) and written on no page read, so one pool per entry, shared by the whole house; with a key, 400 a minute, but a payment method on a Public Cloud project is required and no spend cap exists (OVHcloud AI Endpoints page, read 2026-11-22)
- **OmniRoute** : No quota: local and keyless

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les modèles

Une ligne par entrée de la liste des modèles, dans l'ordre du modèle. La fenêtre de contexte et la réponse la plus longue sont celles que le fournisseur sert, `model_info.max_input_tokens` et `model_info.max_output_tokens`. Le niveau est le `reasoning_effort` que le modèle fixe, sinon celui auquel les contrats disent que le fournisseur appelle l'entrée par défaut. Un tiret veut dire qu'aucune source ne donne la valeur. L'indice d'intelligence et le temps jusqu'au premier jeton n'ont pas de colonne : ils viennent d'Artificial Analysis, que la vérification hebdomadaire des modèles lit en ligne, et aucun fichier du dépôt ne les garde.

| Entrée | Fournisseur | Type | Groupes | Routeurs (rang) | Niveau | Contexte | Sortie max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | chat | `LLM`, `Private-Data` | Auto-Pro n°1, Auto-Flash n°1, Auto-Code n°1, Auto-Claude-Code n°1 | `high` | 1 048 576 | 65 536 |
| `gemini-4-hydrogen-low` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°32 | `low` | 1 048 576 | 65 536 |
| `gemini-4-hydrogen-xhigh` | Gemini | chat | `LLM`, `Private-Data` | — | `xhigh` | 1 048 576 | 65 536 |
| `gemini-3-8-flash` | Gemini | chat | `LLM`, `Private-Data` | Auto-Pro n°3, Auto-Code n°2, Auto-Claude-Code n°2 | `medium` | 1 048 576 | 65 536 |
| `gemini-3-8-flash-low` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash n°3, Auto-Flash-Lite n°30 | `low` | 1 048 576 | 65 536 |
| `gemini-3-7-flash` | Gemini | chat | `LLM`, `Private-Data` | Auto-Pro n°4, Auto-Flash n°4, Auto-Flash-Lite n°31, Auto-Code n°3, Auto-Claude-Code n°3 | — | 1 048 576 | 65 536 |
| `gemini-3-6-flash` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash n°9, Auto-Code n°10, Auto-Claude-Code n°10 | défaut : medium | 1 048 576 | 65 536 |
| `gemini-3-5-flash-lite` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°1 | défaut : minimal | 1 048 576 | 65 536 |
| `gemini-3-1-flash-lite` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°2 | défaut : minimal | 1 048 576 | 65 536 |
| `gemini-3-flash-preview` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash n°10 | défaut : reasoning | 1 048 576 | 65 536 |
| `gemini-2-5-flash` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash n°13, Auto-Code n°12, Auto-Claude-Code n°12 | — | 1 048 576 | 65 536 |
| `gemini-2-5-flash-lite` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°9 | défaut : non-reasoning | 1 048 576 | 65 536 |
| `gemma-4-31b-gemini` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash n°15 | — | 262 144 | — |
| `gemma-4-26b-gemini` | Gemini | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°16 | — | 262 144 | — |
| `gemini-embedding-2` | Gemini | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — |
| `gemini-3-8-flash-tts` | Gemini | `audio_speech` | `TTS`, `Private-Data` | Auto-TTS n°1 | — | — | — |
| `gemini-3-8-flash-lite-tts` | Gemini | `audio_speech` | `TTS`, `Private-Data` | Auto-TTS n°2 | — | — | — |
| `gemini-3-5-transcribe` | Gemini | `audio_transcription` | `STT`, `Private-Data` | Auto-STT n°3 | — | — | — |
| `codestral` | Mistral | chat | `LLM`, `Private-Data` | Auto-Code n°23, Auto-Claude-Code n°17 | — | 128 000 | — |
| `codestral-2508` | Mistral | chat | `LLM`, `Private-Data` | Auto-Code n°24, Auto-Claude-Code n°18 | — | 128 000 | — |
| `mistral-medium` | Mistral | chat | `LLM`, `Private-Data` | Auto-Flash n°42 | — | 262 144 | — |
| `mistral-small` | Mistral | chat | `LLM`, `Private-Data` | Auto-Flash n°43 | — | 262 144 | — |
| `ministral-14b` | Mistral | chat | `LLM`, `Private-Data` | Auto-Flash n°44 | — | 262 144 | — |
| `ministral-8b` | Mistral | chat | `LLM`, `Private-Data` | Auto-Flash n°45 | — | 262 144 | — |
| `ministral-3b` | Mistral | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°35 | — | 262 144 | — |
| `mistral-embed` | Mistral | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — |
| `voxtral-mini-mistral` | Mistral | `audio_transcription` | `STT`, `Private-Data` | Auto-STT n°4 | — | — | — |
| `gpt-oss-120b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°11 | défaut : medium | 131 072 | 65 536 |
| `gpt-oss-20b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°14 | défaut : medium | 131 072 | 65 536 |
| `qwen3-8-27b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°14, Auto-Flash-Lite n°33, Auto-Code n°9, Auto-Claude-Code n°9 | défaut : non-reasoning | 131 072 | 16 384 |
| `whisper-large-v3-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | Auto-STT n°1 | — | — | — |
| `whisper-large-v3-turbo-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | Auto-STT n°2 | — | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°25, Auto-Code n°25, Auto-Claude-Code n°19 | défaut : high | 1 000 000 | 393 216 |
| `deepseek-flash-direct` | DeepSeek | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°46 | défaut : high | 1 000 000 | 393 216 |
| `nemotron-ultra-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°10 | — | 1 000 000 | 65 536 |
| `nemotron-reasoning-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°14 | — | 256 000 | 65 536 |
| `nemotron-lightning-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°5 | — | 1 000 000 | 65 536 |
| `nemotron-super-vl-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°18, Auto-Flash n°24 | — | 1 000 000 | 131 072 |
| `gemma-4-31b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°16 | — | 262 144 | 32 768 |
| `gemma-4-26b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°17 | — | 262 144 | 32 768 |
| `openrouter-auto-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°32 | — | — | — |
| `particle-1-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°19 | — | 1 048 576 | 131 072 |
| `ernie-5-5-flash-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°21 | — | 1 024 000 | 921 600 |
| `lfm-3-1-7b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°3 | — | 262 144 | 8 192 |
| `dots-3-note-preview-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°30 | — | 512 000 | 460 800 |
| `nemotron-3-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — |
| `nemotron-3-5-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — |
| `nemotron-3-5-embed-8b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — |
| `gpt-oss-120b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash n°12 | défaut : medium | 128 000 | — |
| `gpt-oss-20b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°15 | défaut : medium | 128 000 | — |
| `gemma-4-26b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°18 | — | 256 000 | — |
| `llama-3-3-70b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°12 | — | 24 000 | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Code n°14, Auto-Claude-Code n°14 | — | 131 072 | — |
| `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°20 | — | 128 000 | — |
| `clef-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | Auto-Decision n°1 | — | — | — |
| `clef-omni-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | Auto-Decision n°2 | — | — | — |
| `clef-flash-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | Auto-Decision n°3 | — | — | — |
| `clairic-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | Auto-Extraction n°1 | — | — | — |
| `clairic-flash-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | Auto-Extraction n°2 | — | — | — |
| `granite-4-0-h-micro-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°23 | — | 131 000 | — |
| `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°22 | — | 128 000 | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°10 | — | 131 000 | — |
| `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°21 | — | 128 000 | — |
| `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°19 | — | 32 768 | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | Auto-Flash n°38, Auto-Code n°20, Auto-Claude-Code n°16 | défaut : xhigh | 262 144 | — |
| `bge-m3-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — |
| `glm-4-7-flash-zai` | Zai | chat | `LLM`, `Public-Data-Only` | Auto-Code n°15, Auto-Claude-Code n°15 | — | 200 000 | 128 000 |
| `nemotron-ultra-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°13 | — | 1 000 000 | 65 536 |
| `nemotron-reasoning-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°17 | — | 256 000 | 65 536 |
| `nemotron-lightning-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°8 | — | 1 000 000 | 65 536 |
| `nemotron-super-vl-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°20, Auto-Flash n°27 | — | 1 000 000 | 131 072 |
| `particle-1-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°20 | — | 1 048 576 | 131 072 |
| `ernie-5-5-flash-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°22 | — | 1 024 000 | 921 600 |
| `lfm-3-1-7b-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°4 | — | 262 144 | 8 192 |
| `beam-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°9, Auto-Flash n°23 | — | 1 048 576 | 131 072 |
| `flint-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°28 | — | 262 144 | 235 929 |
| `glyph-cluster-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°29 | — | 256 000 | 256 000 |
| `dots-3-note-preview-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°31 | — | 512 000 | 460 800 |
| `deepseek-v4-1-flash-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Pro n°22, Auto-Flash n°34, Auto-Code n°16 | — | 1 048 576 | 262 144 |
| `qwen3-5-397b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Pro n°23, Auto-Flash n°35, Auto-Code n°17 | — | 262 144 | 262 144 |
| `gpt-oss-120b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Pro n°24, Auto-Flash n°36, Auto-Code n°18 | — | 131 072 | 131 072 |
| `qwen3-8-27b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash n°37, Auto-Code n°19 | — | 262 144 | 262 144 |
| `qwen3-6-35b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash n°39, Auto-Code n°21 | — | 262 144 | 65 536 |
| `nemotron3-omni-30b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash n°40 | — | 131 072 | 65 536 |
| `mistral-small-3-2-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash n°41 | — | 131 072 | 131 072 |
| `gpt-oss-20b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°25 | — | 131 072 | 65 536 |
| `gemma-4-26b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°26 | — | 262 144 | 65 536 |
| `nemotron3-nano-30b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°27 | — | 262 144 | 65 536 |
| `qwen3-5-9b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°28 | — | 262 144 | 65 536 |
| `olala-mini-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Flash-Lite n°29 | — | 32 768 | 16 384 |
| `laguna-xs-2-1-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | Auto-Code n°22 | — | 131 072 | 65 536 |
| `nemotron-ultra-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°11 | — | 1 048 576 | 65 536 |
| `nemotron-reasoning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°15 | — | 131 072 | 20 480 |
| `nemotron-lightning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°6 | — | 1 048 576 | 65 536 |
| `gemma-4-31b-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°17 | — | 262 144 | 8 192 |
| `kimi-k3-1-pro-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°2, Auto-Flash n°2, Auto-Code n°5, Auto-Claude-Code n°5 | — | 1 048 576 | — |
| `mistral-large-4-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°7, Auto-Flash n°7, Auto-Code n°8, Auto-Claude-Code n°8 | défaut : high | 1 048 576 | — |
| `nemotron-ultra-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°12 | — | 1 048 576 | — |
| `nemotron-reasoning-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°16 | — | 262 144 | — |
| `nemotron-lightning-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°7 | — | 1 048 576 | — |
| `nemotron-super-vl-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°19, Auto-Flash n°25 | — | 1 048 576 | — |
| `nemotron-bolt-e4b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°24 | — | 65 536 | — |
| `glm-5-3-flash-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°8, Auto-Flash n°8, Auto-Code n°4, Auto-Claude-Code n°4 | défaut : max | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°6, Auto-Flash n°6, Auto-Code n°7, Auto-Claude-Code n°7 | — | 1 000 000 | — |
| `step-5-preview-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°5, Auto-Flash n°5, Auto-Code n°6, Auto-Claude-Code n°6 | — | 1 000 000 | 1 000 000 |
| `laguna-xs-2-1-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Code n°13, Auto-Claude-Code n°13 | — | 262 144 | — |
| `muse-glimmer-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°26, Auto-Code n°11, Auto-Claude-Code n°11 | — | 131 072 | — |
| `gemma-4-31b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°18 | — | 262 144 | — |
| `gemma-3-12b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°13 | — | — | — |
| `gemma-3-4b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°11 | — | — | — |
| `hy4-flash-cent-ai` | Cent AI | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°21, Auto-Flash n°33, Auto-Flash-Lite n°34 | — | 1 048 576 | — |
| `aion-3-5-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | Auto-Fiction n°1 | — | 262 144 | 32 768 |
| `aion-3-5-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | Auto-Fiction n°2 | — | 262 144 | 32 768 |
| `aion-3-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | Auto-Fiction n°3 | — | 131 072 | 32 768 |
| `aion-3-0-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | Auto-Fiction n°4 | — | 131 072 | 32 768 |
| `aion-2-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | Auto-Fiction n°5 | — | 131 072 | 32 768 |
| `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | Auto-Fiction n°6 | — | 32 768 | 32 768 |
| `omniroute-free-auto` | OmniRoute | chat | `LLM`, `Public-Data-Only` | Auto-Flash n°47 | — | — | — |
| `omniroute-free-code` | OmniRoute | chat | `LLM`, `Public-Data-Only` | Auto-Code n°26 | — | — | — |
| `omniroute-free-reasoning` | OmniRoute | chat | `LLM`, `Public-Data-Only` | Auto-Pro n°26 | — | — | — |
| `omniroute-free-fast` | OmniRoute | chat | `LLM`, `Public-Data-Only` | Auto-Flash-Lite n°36 | — | — | — |
| `Auto` | LiteLLM | chat | `LLM`, `Public-Data-Only` | — | — | — | — |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)
