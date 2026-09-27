<!--
SPDX-FileCopyrightText: 2026 Dragnix-23
SPDX-License-Identifier: AGPL-3.0-only
-->

# N8N workflows — AIS

Issue #20, Niveau 1 uniquement (API officielles — statistiques Twitch/YouTube/TikTok/X/Facebook/Instagram
de Dragnix-23). Le Niveau 2 (alertes mail immobilier, tigerblue77) reste hors périmètre de ce dossier.

Ces fichiers sont des exports N8N nettoyés : aucun identifiant, token ou secret n'y figure. Tous les
credentials sont créés et stockés exclusivement dans le gestionnaire de credentials de l'instance N8N,
jamais dans ce dépôt.

## Arborescence

- `streaming_social_stats_collector.json` — workflow orchestrateur. Déclencheur Cron quotidien (06:00),
  appelle chaque sous-workflow de `collectors/`, fusionne leurs sorties, valide le schéma commun et
  écrit en double destination (Postgres + Notion).
- `collectors/<plateforme>_stats_collector.json` — un sous-workflow indépendant par plateforme. Ajouter
  une nouvelle plateforme = ajouter un fichier ici + un noeud `Execute Workflow` dans l'orchestrateur,
  sans modifier les sous-workflows existants.

## Import dans N8N

1. Importer les 6 workflows de `collectors/` en premier, configurer leurs credentials respectifs.
2. Importer `streaming_social_stats_collector.json`.
3. Dans chaque noeud `Execute Workflow` de l'orchestrateur, remplacer le `workflowId` placeholder
   (`REPLACE_AFTER_IMPORT_<plateforme>_stats_collector`) par l'ID réel attribué par l'instance à
   l'import du sous-workflow correspondant.
4. Configurer les credentials Postgres (`AIS Postgres`) et Notion (`AIS Notion`) de l'orchestrateur.
5. Dans les sous-workflows Facebook et Instagram, remplacer `PLACEHOLDER_FACEBOOK_PAGE_ID` et
   `PLACEHOLDER_INSTAGRAM_USER_ID` par les identifiants réels.
6. Dans les sous-workflows Twitch et TikTok, renseigner l'en-tête `Client-Id` (Twitch) — ces valeurs ne
   sont pas portées par le credential OAuth2 générique.

## Schéma commun

Chaque sous-workflow retourne exactement :

```json
{
  "platform": "string",
  "account_id": "string",
  "account_name": "string",
  "followers_count": "integer | null",
  "views_recent_30d": "integer | null",
  "views_average": "integer | null",
  "account_status": "string | null",
  "collected_at": "ISO 8601"
}
```

Pas de métrique de live temps réel (hors périmètre validé pour ce lot).

## Limitations connues par plateforme

| Plateforme | `views_recent_30d` / `views_average` | Raison |
| --- | --- | --- |
| Twitch | Approximé via les VOD (`type=archive`) des 30 derniers jours, une page (100 max) | `view_count` retiré de `GET /helix/users` en 2023, pas de compteur de vues total au niveau du compte |
| YouTube | Calculé sur les vidéos de la playlist `uploads` publiées dans les 30 derniers jours | Pas de fenêtre 30 jours native dans l'API publique |
| TikTok | `null` si le scope `video.list` n'est pas accordé | Display API gratuite limitée, pas de compteur de vues agrégé natif |
| X (Twitter) | Toujours `null` | Impressions au niveau compte indisponibles sur le tier gratuit |
| Facebook | `null` tant que l'app review Meta (`pages_read_engagement`) n'est pas active | Permission Insights soumise à revue |
| Instagram | `null` tant que l'app review Meta (`instagram_manage_insights`) n'est pas active | Permission Insights soumise à revue |

`account_status` n'est renseigné que pour Twitch (`broadcaster_type`) et YouTube (`privacyStatus`) — les
autres plateformes n'exposent pas d'équivalent direct dans leur API publique.

## Table Postgres attendue

Le noeud Postgres de l'orchestrateur écrit dans `social_stats`. Cette table n'est pas créée par ce
dépôt (aucune migration Ansible pour ce niveau, conformément à l'arbitrage validé) — DDL de référence
à exécuter manuellement sur l'instance Postgres de l'AIS :

```sql
CREATE TABLE IF NOT EXISTS social_stats (
    id               BIGSERIAL PRIMARY KEY,
    platform         TEXT NOT NULL,
    account_id       TEXT NOT NULL,
    account_name     TEXT NOT NULL,
    followers_count  INTEGER,
    views_recent_30d INTEGER,
    views_average    INTEGER,
    account_status   TEXT,
    collected_at     TIMESTAMPTZ NOT NULL
);
```

## Base Notion attendue

Le noeud Notion de l'orchestrateur crée une page par plateforme et par exécution dans une base Notion
dont le `databaseId` doit être renseigné après import, avec les propriétés : `Platform` (texte),
`Account` (texte), `Followers` (nombre), `Views (30d)` (nombre), `Avg views` (nombre), `Status` (texte),
`Collected at` (date).
