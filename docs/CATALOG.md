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
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `beam-kilo` | Kilo | — | — |
| `nemotron-ultra-free` | OpenRouter | `high` | — |
| `nemotron-ultra-requesty` | Requesty | `max` | — |
| `nemotron-ultra-nvidia` | NVIDIA | — | — |
| `nemotron-ultra-kilo` | Kilo | `high` | — |
| `nemotron-reasoning-free` | OpenRouter | — | — |
| `nemotron-reasoning-requesty` | Requesty | `max` | — |
| `nemotron-reasoning-nvidia` | NVIDIA | — | — |
| `nemotron-reasoning-kilo` | Kilo | — | — |
| `nemotron-super-vl-free` | OpenRouter | — | — |
| `nemotron-super-vl-nvidia` | NVIDIA | — | — |
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
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `gemini-3-6-flash` | Gemini | `high` | — |
| `gemini-3-flash-preview` | Gemini | `high` | — |
| `gpt-oss-120b-groq` | Groq | défaut : medium | — |
| `gpt-oss-120b-cloudflare` | Cloudflare | défaut : medium | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `gemma-4-31b-gemini` | Gemini | — | — |
| `gemma-4-31b-free` | OpenRouter | — | — |
| `gemma-4-31b-requesty` | Requesty | `high` | — |
| `gemma-4-31b-nvidia` | NVIDIA | — | — |
| `particle-1-free` | OpenRouter | `xhigh` | — |
| `particle-1-kilo` | Kilo | `max` | — |
| `ernie-5-5-flash-free` | OpenRouter | `high` | — |
| `ernie-5-5-flash-kilo` | Kilo | `high` | — |
| `beam-kilo` | Kilo | — | — |
| `nemotron-super-vl-free` | OpenRouter | — | — |
| `nemotron-super-vl-nvidia` | NVIDIA | — | — |
| `muse-glimmer-nvidia` | NVIDIA | — | — |
| `nemotron-super-vl-kilo` | Kilo | — | — |
| `flint-kilo` | Kilo | — | — |
| `glyph-cluster-kilo` | Kilo | — | — |
| `dots-3-note-preview-free` | OpenRouter | — | — |
| `dots-3-note-preview-kilo` | Kilo | — | — |
| `openrouter-auto-free` | OpenRouter | — | dernier recours |
| `hy4-flash-cent-ai` | Cent AI | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-ovh` | OVHcloud | — | — |
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
| `nemotron-lightning-kilo` | Kilo | — | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | — | — |
| `gemma-3-4b-nvidia` | NVIDIA | — | — |
| `llama-3-3-70b-cloudflare` | Cloudflare | — | — |
| `gemma-3-12b-nvidia` | NVIDIA | — | — |
| `gpt-oss-20b-groq` | Groq | défaut : medium | — |
| `gpt-oss-20b-cloudflare` | Cloudflare | défaut : medium | — |
| `gemma-4-26b-gemini` | Gemini | — | — |
| `gemma-4-26b-free` | OpenRouter | — | — |
| `gemma-4-26b-cloudflare` | Cloudflare | — | — |
| `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | — | — |
| `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | — | — |
| `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | — | — |
| `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | — | — |
| `granite-4-0-h-micro-cloudflare` | Cloudflare | — | — |
| `nemotron-bolt-e4b-nvidia` | NVIDIA | — | — |
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
| `voxtral-mini-mistral` | Mistral | `audio_transcription` | `STT`, `Private-Data` | `Auto-STT` | — | — | — | — | — | — |
| `gpt-oss-120b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | défaut : medium | 131 072 | 65 536 | 30 | 8 000 | 1 000 |
| `gpt-oss-20b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | défaut : medium | 131 072 | 65 536 | 30 | 8 000 | 1 000 |
| `qwen3-8-27b-groq` | Groq | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code` | défaut : non-reasoning | 131 072 | 16 384 | 30 | 8 000 | 1 000 |
| `whisper-large-v3-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | `Auto-STT` | — | — | — | 20 | — | 2 000 |
| `whisper-large-v3-turbo-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | `Auto-STT` | — | — | — | 20 | — | 2 000 |
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
| `nemotron-3-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-3-5-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `nemotron-3-5-embed-8b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `gpt-oss-120b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash` | défaut : medium | 128 000 | — | — | — | — |
| `gpt-oss-20b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | défaut : medium | 128 000 | — | — | — | — |
| `gemma-4-26b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 256 000 | — | — | — | — |
| `llama-3-3-70b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 24 000 | — | — | — | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 131 072 | — | — | — | — |
| `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — | — | — | — |
| `clef-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — | — | — | — |
| `clef-omni-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — | — | — | — |
| `clef-flash-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — | — | — | — |
| `clairic-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | `Auto-Extraction` | — | — | — | — | — | — |
| `clairic-flash-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | `Auto-Extraction` | — | — | — | — | — | — |
| `granite-4-0-h-micro-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 000 | — | — | — | — |
| `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — | — | — | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 000 | — | — | — | — |
| `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — | — | — | — |
| `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 32 768 | — | — | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | défaut : xhigh | 262 144 | — | — | — | — |
| `bge-m3-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — | — | — | — |
| `glm-4-7-flash-zai` | Zai | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 200 000 | 128 000 | — | — | — |
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
| `nemotron-ultra-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `max` | 1 048 576 | 65 536 | — | — | — |
| `nemotron-reasoning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `max` | 131 072 | 20 480 | — | — | — |
| `nemotron-lightning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 048 576 | 65 536 | — | — | — |
| `gemma-4-31b-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `high` | 262 144 | 8 192 | — | — | — |
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
| `hy4-flash-cent-ai` | Cent AI | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` | — | 1 048 576 | — | — | — | — |
| `aion-3-5-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 262 144 | 32 768 | — | — | — |
| `aion-3-5-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 262 144 | 32 768 | — | — | — |
| `aion-3-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 | — | — | — |
| `aion-3-0-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 | — | — | — |
| `aion-2-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 | — | — | — |
| `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 32 768 | 32 768 | — | — | — |
| `omniroute-free-auto` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | — | — | — | — | — |
| `omniroute-free-code` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Code` | — | — | — | — | — | — |
| `omniroute-free-reasoning` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | — | — | — | — | — |
| `omniroute-free-fast` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | — | — | — | — | — |
| `omniroute-free-vision` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `omniroute-vision` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `omniroute-multimodal` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |
| `Auto` | LiteLLM | chat | `LLM`, `Public-Data-Only` | — | — | — | — | — | — | — |

### Les scores d'Artificial Analysis et d'Epoch AI

Les chiffres sont ceux d'Artificial Analysis et d'Epoch AI : l'enregistrement et le niveau d'Artificial Analysis, et le modèle d'Epoch AI, sont ceux que dit `.github/LiteLLM_router_contracts.yaml` de l'entrée. La CI ne peut lire aucun de ces deux sites : la vérification hebdomadaire des modèles les lit et réécrit [`docs/catalog_scores.json`](catalog_scores.json) dans chaque pull request qu'elle ouvre. La CI tient ce fichier à sa forme (des nombres, et des entrées du modèle de configuration) et ce catalogue à ce fichier. Jours de lecture : Artificial Analysis le jamais, Epoch AI le 2026-11-24. Un tiret veut dire qu'aucune source ne donne le chiffre : l'enregistrement est introuvable ou n'est pas celui du niveau où l'entrée est appelée, le modèle n'est pas à l'indice d'Epoch AI, ou moins de deux de ses benchmarks de code ont un score pour lui.

- **Indice AA** : l'indice d'intelligence de l'enregistrement, plus haut est meilleur.
- **Premier mot AA** : le temps moyen jusqu'au premier jeton de la réponse, en secondes, que le temps de réflexion compte.
- **ECI Epoch** : l'indice de capacités du modèle, plus haut est meilleur.
- **Position de code Epoch** : la médiane, en pour cent, de la position du modèle dans les benchmarks de code où il a un score, deux au moins, où 100 est le dernier : plus petit est meilleur.

Sources : Artificial Analysis (artificialanalysis.ai) et Epoch AI, benchmark data, CC BY 4.0.

| Entrée | Enregistrement AA | Indice AA | Premier mot AA (s) | Modèle Epoch | ECI Epoch | Position de code Epoch (%) |
| --- | --- | --- | --- | --- | --- | --- |
| `gemini-4-hydrogen` | `gemini-4-hydrogen` (`xhigh`) | — | — | `Gemini 4 Hydrogen` | 166,81 | 9,37 |
| `gemini-4-hydrogen-low` | `gemini-4-hydrogen-low` (`low`) | — | — | `Gemini 4 Hydrogen` | 166,81 | — |
| `gemini-3-8-flash` | `gemini-3-8-flash-medium` (`high`) | — | — | `Gemini 3.8 Flash` | 158,81 | 17,18 |
| `gemini-3-8-flash-low` | `gemini-3-8-flash-low` (`low`) | — | — | `Gemini 3.8 Flash` | 158,81 | — |
| `gemini-3-7-flash` | `gemini-3-7-flash` | — | — | `Gemini 3.7 Flash` | 158,4 | 45,74 |
| `gemini-3-6-flash` | `gemini-3-6-flash` (`high`) | — | — | `Gemini 3.6 Flash` | 155,24 | 71,57 |
| `gemini-3-5-flash-lite` | `gemini-3-5-flash-lite` (`minimal`) | — | — | `Gemini 3.5 Flash-Lite` | 145,63 | — |
| `gemini-3-1-flash-lite` | `gemini-3-1-flash-lite-preview` (`minimal`) | — | — | `Gemini 3.1 Flash-Lite` | 144,97 | — |
| `gemini-3-flash-preview` | `gemini-3-flash-reasoning` (`reasoning`) | — | — | `Gemini 3 Flash` | 152,35 | 25,87 |
| `gemma-4-31b-gemini` | `gemma-4-31b` | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `gemma-4-26b-gemini` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `mistral-medium` | `mistral-medium-3-5` | — | — | `Mistral Medium 3.5` | 141,58 | — |
| `mistral-small` | `mistral-small-4` | — | — | — | — | — |
| `ministral-14b` | `ministral-3-14b` | — | — | — | — | — |
| `ministral-8b` | `ministral-3-8b` | — | — | — | — | — |
| `ministral-3b` | `ministral-3-3b` | — | — | — | — | — |
| `gpt-oss-120b-groq` | `gpt-oss-120b` (`medium`) | — | — | `gpt-oss-120b` | 140,21 | 84,28 |
| `gpt-oss-20b-groq` | `gpt-oss-20b` (`medium`) | — | — | `gpt-oss-20b` | 134,89 | 89,71 |
| `qwen3-8-27b-groq` | `qwen3-8-27b-non-reasoning` (`non-reasoning`) | — | — | `Qwen 3.8 27B` | 152,63 | — |
| `deepseek-v4-pro-direct` | `deepseek-v4-pro-high` (`high`) | — | — | `DeepSeek V4 Pro 0813` | 155,96 | 21,68 |
| `deepseek-flash-direct` | `deepseek-v4-1-flash-1017-high` (`high`) | — | — | `DeepSeek V4.1 Flash 1017` | 159,41 | — |
| `nemotron-ultra-free` | `nvidia-nemotron-3-ultra-550b-a55b` (`reasoning`) | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-reasoning-free` | `nemotron-3-nano-omni-30b-a3b` | — | — | — | — | — |
| `nemotron-lightning-free` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `nemotron-super-vl-free` | `nemotron-3-5-super-vl` | — | — | — | — | — |
| `gemma-4-31b-free` | `gemma-4-31b` | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `gemma-4-26b-free` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `lfm-3-1-7b-free` | `lfm3-1-7b` | — | — | — | — | — |
| `gpt-oss-120b-cloudflare` | `gpt-oss-120b` (`medium`) | — | — | `gpt-oss-120b` | 140,21 | 84,28 |
| `gpt-oss-20b-cloudflare` | `gpt-oss-20b` (`medium`) | — | — | `gpt-oss-20b` | 134,89 | 89,71 |
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
| `gpt-oss-120b-ovh` | `gpt-oss-120b` | — | — | `gpt-oss-120b` | 140,21 | 84,28 |
| `qwen3-8-27b-ovh` | — | — | — | `Qwen 3.8 27B` | 152,63 | — |
| `nemotron3-omni-30b-ovh` | `nemotron-3-nano-omni-30b-a3b` | — | — | — | — | — |
| `gpt-oss-20b-ovh` | `gpt-oss-20b` | — | — | `gpt-oss-20b` | 134,89 | 89,71 |
| `gemma-4-26b-ovh` | `gemma-4-26b-a4b` | — | — | `Gemma 4 26B A4B` | 141,56 | — |
| `nemotron-ultra-requesty` | `nvidia-nemotron-3-ultra-550b-a55b` (`reasoning`) | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-reasoning-requesty` | `nemotron-3-nano-omni-30b-a3b` (`max`) | — | — | — | — | — |
| `nemotron-lightning-requesty` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `gemma-4-31b-requesty` | `gemma-4-31b` (`reasoning`) | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `kimi-k3-1-pro-nvidia` | `kimi-k3-1-pro` | — | — | `Kimi K3.1 Pro` | 161,2 | — |
| `mistral-large-4-nvidia` | `mistral-large-4` (`high`) | — | — | `Mistral Large 4` | 154,57 | — |
| `nemotron-ultra-nvidia` | `nvidia-nemotron-3-ultra-550b-a55b` | — | — | `Nemotron 3 Ultra` | 147,02 | — |
| `nemotron-reasoning-nvidia` | `nemotron-3-nano-omni-30b-a3b` | — | — | — | — | — |
| `nemotron-lightning-nvidia` | `nemotron-3-5-lightning` | — | — | — | — | — |
| `nemotron-super-vl-nvidia` | `nemotron-3-5-super-vl` | — | — | — | — | — |
| `glm-5-3-flash-nvidia` | `glm-5-3-flash` (`max`) | — | — | `GLM-5.3-Flash` | 153,77 | 68,24 |
| `minimax-m3-1-flash-nvidia` | `minimax-m3-1-flash` | — | — | — | — | — |
| `step-5-preview-nvidia` | `step-5` | — | — | — | — | — |
| `muse-glimmer-nvidia` | `muse-glimmer` | — | — | — | — | — |
| `gemma-4-31b-nvidia` | `gemma-4-31b` | — | — | `Gemma 4 31B IT` | 144,12 | — |
| `gemma-3-12b-nvidia` | `gemma-3-12b` | — | — | — | — | — |
| `gemma-3-4b-nvidia` | `gemma-3-4b` | — | — | — | — | — |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)
