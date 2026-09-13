<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# AI-Docker-stack

Déploiement Ansible de l'**AIS** -- *Artificial Intelligence Stack* : la stack Docker qui regroupe toutes
les briques liées à l'IA du homelab. Passerelle LLM, base vectorielle, reranker, conteneur Claude Code,
agents et connecteurs y vivront dans un seul stack.

**Ce dépôt est le rôle Ansible `deploy_AIS_Docker_stack`, et rien d'autre autour de lui : il rend le
`docker-compose` du stack et délègue son déploiement au rôle que l'appelant désigne.** `tasks/`,
`defaults/`, `templates/` et le reste vivent à sa racine plutôt que sous un `roles/<nom>/` à lui : c'est
ce qui permet à un appelant de l'installer directement, par Galaxy ou par un submodule, et d'avoir le
checkout résolu comme le rôle lui-même -- sans une couche de dossier en plus qui n'existe que pour ce
dépôt et que personne d'autre n'a de raison de reproduire.

## Ce que contient ce dépôt

Un rôle, le playbook d'exemple qui montre comment l'appeler, et de quoi vérifier les deux.

```
playbook.AIS.example.yaml                     l'appel du rôle, commenté
defaults/, tasks/, templates/, files/,        le rôle lui-même : le docker-compose du stack,
handlers/, vars/, meta/                       ses variables, sa configuration LiteLLM/LibreChat
.ansible-lint                                 ce que « conforme » veut dire ici
.github/scripts/check_compose_template.py     rend le template et le tient à ses conventions
```

Un rôle et rien d'autre, et c'est délibéré : **le dépôt fournit le stack, pas la mécanique qui le déploie.** Cette
mécanique appartient à l'appelant, et elle existe déjà -- `Docker/deploy_Docker_swarm_stack` et
`Docker/deploy_Docker_compose_stack` du dépôt `Homelab_Ansible_deployment` la portent, chacun pour son
orchestrateur, avec tout ce que leurs commentaires documentent de pannes déjà payées.

Le modèle commenté en tête du template (`templates/AIS.docker-compose.yml.j2`) porte les conventions
qu'un bloc de service doit tenir : image épinglée par version, limite mémoire déclarée,
`deploy.restart_policy.condition: any`, aucun port publié pour un service interne, aucun secret en
clair. Elles sont écrites là plutôt que dans un document séparé parce que c'est là qu'on les oublie.

## Un rôle paramétrable, pas un rôle spécifique

Le rôle ne présuppose **ni machine, ni domaine, ni compte, ni orchestrateur**. Tout ce qui identifie un
déploiement est une variable fournie par l'appelant : son inventaire, ses FQDN, les labels de son reverse
proxy, son réseau publié, et jusqu'au nom du rôle chargé de déployer le stack.

C'est ce qui permet à deux personnes de déployer le même stack sur deux estates qui n'ont rien en commun,
sans forker. Il n'y a donc dans ce dépôt aucune adresse IP, aucun nom d'hôte et aucun domaine.

## Prérequis

- Un rôle capable de déployer le stack, nommé par `AIS_Docker_stack_deployment_role_name`, et résoluble
  depuis le `roles_path` de l'appelant. Ce dépôt n'en fournit aucun : voir « Le contrat du rôle de
  déploiement » plus bas.
- La collection `community.docker` (`requirements.yml`, à la racine du dépôt), depuis #76 : le compte
  admin de LibreChat s'y crée par `docker_host_info` et `docker_container_exec`, pas par
  `ansible.builtin.assert`/`include_role` comme le reste du rôle.
- **Sur le nœud géré** (pas sur celui qui lance Ansible, s'ils diffèrent) : le SDK Python `docker`
  (`pip install docker`). Les deux modules ci-dessus parlent à l'API du moteur Docker à travers lui,
  jamais à travers le CLI `docker` -- son absence échoue à l'intérieur du module, avec son propre
  message, plutôt que d'être vérifiée ici où il n'y a rien à vérifier avant que le module ne tourne.

## Comment l'appeler

```yaml
- role: deploy_AIS_Docker_stack
  vars:
    AIS_Docker_stack_deployment_role_name: "Docker/deploy_Docker_swarm_stack"
```

Le seul paramètre obligatoire est celui-là : le rôle qui déploie réellement le stack. Le contrat qu'il doit
remplir, la liste complète des variables et les raisons derrière les choix du template sont dans les
sections qui suivent.

## Variables du rôle

Le stack porte déjà plusieurs services -- la passerelle et sa base, Redis, OmniRoute, Qdrant, LibreChat
et sa base, l'agent Claude Code de tigerblue77 (désactivé par défaut) -- chacun arrivé par sa propre
issue de service, avec son bloc et ses variables. Ce que ce rôle apporte reste la forme plutôt que le
contenu : un rôle qui ne présuppose ni machine, ni domaine, ni compte, ni orchestrateur, et un template
dont les conventions sont écrites à l'endroit où on les oublie.

| Variable | Défaut | Description |
|---|---|---|
| `AIS_Docker_stack_deployment_role_name` | aucun | **Obligatoire.** Le rôle qui déploie réellement le stack. Sans défaut, délibérément : en avoir un présupposerait un orchestrateur. |
| `AIS_Docker_stack_name` | `AIS` | Le « namespace » du stack chez l'orchestrateur. Compose le normalise en minuscules pour son nom de projet. |
| `AIS_Docker_compose_file_name` | `AIS.docker-compose.yml` | Le template rendu, sans le suffixe `.j2`. |
| `AIS_Docker_compose_file_destination_directory` | `/tmp/` | Où le fichier rendu atterrit sur le nœud géré. |
| `AIS_Docker_compose_file_destination_path` | *dérivé des deux précédents* | Chemin complet. À ne surcharger que si l'on veut le découpler du répertoire. |
| `AIS_server_time_zone` | `Etc/UTC` | Le `TZ` injecté dans chaque conteneur. Un appelant qui a déjà le sien le passe ici. |
| `AIS_internal_Docker_network_name` | `AIS_internal` | Le réseau que les services du stack utilisent entre eux. Déclaré par le stack, donc créé et détruit avec lui. |
| `AIS_published_Docker_network_name` | `false` | Le réseau publié de l'appelant, celui où écoute son reverse proxy. |
| `AIS_published_Docker_network_definition` | `false` | La déclaration de ce même réseau, telle qu'elle doit apparaître dans le bloc `networks:`. |

Et celles que #1 apporte, pour la passerelle et sa base :

| Variable | Défaut | Description |
|---|---|---|
| `AIS_PostgreSQL_password` | aucun | **Obligatoire.** Rendu depuis le vault de l'appelant. Sans défaut : un mot de passe par défaut est un mot de passe, et livré dans un dépôt, un mot de passe publié. |
| `AIS_LiteLLM_master_key` | aucun | **Obligatoire.** Administration **uniquement** : chaque consommateur reçoit sa propre clé virtuelle (#2). |
| `AIS_LiteLLM_Docker_image_tag` | `v1.100.0` | SemVer explicite, jamais `main-latest`. **À re-vérifier le jour du déploiement.** |
| `AIS_LiteLLM_minimum_secure_version` | `1.84.0` | Le plancher de sécurité que `tasks/main.yml` refuse de franchir vers le bas. |
| `AIS_LiteLLM_number_of_workers` | `4` | Chaque worker réplique la configuration : ce nombre multiplie l'empreinte mémoire. |
| `AIS_LiteLLM_memory_limit` | `2g` | Valeur de départ, à recaler sous charge. |
| `AIS_PostgreSQL_Docker_image_tag` | `17-alpine` | Majeur explicite : une montée de majeur impose un `pg_dump` / restauration. |
| `AIS_PostgreSQL_database` · `AIS_PostgreSQL_user` | `litellm` | Base et rôle de la passerelle. |
| `AIS_PostgreSQL_data_Docker_volume_name` | `AIS_PostgreSQL_data` | Volume **nommé** : survivre à une recréation de conteneur est un critère d'acceptation. |
| `AIS_PostgreSQL_memory_limit` | `1g` | Valeur de départ, à recaler sous charge. |
| `AIS_LiteLLM_config_file_name` · `..._destination_path` | `LiteLLM_config.yaml` | La configuration de routage, montée en lecture seule. #2 en remplit le `model_list`. |
| `AIS_LiteLLM_UI_username` | `admin` | Le compte de connexion à `/ui`, dont le port est publié -- voir plus bas. |
| `AIS_LiteLLM_UI_password` | aucun | **Obligatoire.** Rendu depuis le vault de l'appelant, comme les deux secrets ci-dessus. |
| `AIS_LiteLLM_internal_users` | `[]` | Une **liste**, jamais une paire de variables nommées (#103) : chaque `{username, email}` devient un compte `internal_user` à lui, self-service, ajouté à `access_group:<username>`. Voir « Un compte par personne, pas une paire figée » plus bas. |

Et celles que #2 apporte, pour le `model_list` de tigerblue77 (voir plus bas pourquoi Dragnix n'a pas
les siennes ici) :

| Variable | Défaut | Description |
|---|---|---|
| `AIS_LiteLLM_Gemini_API_key_tigerblue77` | aucun | **Obligatoire.** |
| `AIS_LiteLLM_GitHub_API_key_tigerblue77` | aucun | **Obligatoire.** |
| `AIS_LiteLLM_Mistral_API_key_tigerblue77` | aucun | **Obligatoire.** |
| `AIS_LiteLLM_Cerebras_API_key_tigerblue77` | aucun | **Obligatoire.** |
| `AIS_LiteLLM_Groq_API_key_tigerblue77` | aucun | **Obligatoire.** |
| `AIS_LiteLLM_OpenRouter_API_key_tigerblue77` | aucun | **Obligatoire.** |
| `AIS_LiteLLM_DeepSeek_API_key_tigerblue77` | aucun | **Obligatoire.** Le seul fournisseur **payant** de ce fichier (#101) -- l'API directe de DeepSeek n'a pas de palier gratuit permanent, contrairement à tous les autres. |

Et celles que #71 apporte, pour Redis :

| Variable | Défaut | Description |
|---|---|---|
| `AIS_Redis_Docker_image_tag` | `7-alpine` | Majeur explicite, jamais `:latest`. |
| `AIS_Redis_data_Docker_volume_name` | `AIS_Redis_data` | Volume nommé : `--save 60 1` sans volume derrière ne sert à rien. |
| `AIS_Redis_memory_limit` | `256m` | Valeur de départ. |
| `AIS_Redis_password` | aucun | **Obligatoire.** `--requirepass` serait vide sinon. |

Et celles que #73 apporte, pour OmniRoute :

| Variable | Défaut | Description |
|---|---|---|
| `AIS_OmniRoute_Docker_image_tag` | `3.8.50` | SemVer explicite, jamais `:latest` ni la variante `-web`. |
| `AIS_OmniRoute_data_Docker_volume_name` | `AIS_OmniRoute_data` | Volume nommé pour son magasin SQLite. |
| `AIS_OmniRoute_memory_limit` | `2g` | Valeur de départ, à recaler si l'usage dépasse le simple dernier recours. |
| `AIS_OmniRoute_dashboard_password` | aucun | **Obligatoire.** Remplace le `CHANGEME` de l'image. |

Et celles que #3 apporte, pour Qdrant :

| Variable | Défaut | Description |
|---|---|---|
| `AIS_Qdrant_Docker_image_tag` | `v1.19.1` | SemVer explicite, jamais `:latest`. |
| `AIS_Qdrant_data_Docker_volume_name` | `AIS_Qdrant_data` | Volume nommé pour `/qdrant/storage`. |
| `AIS_Qdrant_memory_limit` | `1g` | Valeur de départ, généreuse pour la taille du corpus visée par #3. |
| `AIS_Qdrant_API_key` | aucun | **Obligatoire.** Défense en profondeur, même sans port publié. |

Et celles que #13 apporte, pour l'agent Claude Code de tigerblue77 -- **toutes sans effet tant que
`AIS_Claude_code_tigerblue77_enabled` reste à `false`**, sa valeur par défaut :

| Variable | Défaut | Description |
|---|---|---|
| `AIS_Claude_code_tigerblue77_enabled` | `false` | Active le service. #31 exige que chaque service se déclare ainsi. |
| `AIS_Claude_code_Docker_image_tag` · `..._digest` | `2.1.236` / le digest publié | L'image dont l'agent est construit, épinglée par tag **et** digest -- jamais l'un sans l'autre. |
| `AIS_Claude_code_tigerblue77_build_context_directory` | *dérivé* | Où le `Dockerfile` rendu atterrit sur le nœud géré, à côté du `docker-compose`. |
| `AIS_Claude_code_tigerblue77_virtual_key` | aucun | **Obligatoire si activé.** Clé virtuelle LiteLLM (#2), jamais la clé maîtresse. |
| `AIS_Claude_code_tigerblue77_GitHub_token` | aucun | **Obligatoire si activé.** Jeton personnel, en attendant le connecteur MCP GitHub (#23). |
| `AIS_Claude_code_tigerblue77_workspace_directory` | aucun | **Obligatoire si activé.** Un chemin hôte : ce rôle ne peut pas en inventer un. |
| `AIS_Claude_code_tigerblue77_model` | `claude-code` | L'alias que LiteLLM résout (#2) -- jamais un nom de modèle Anthropic littéral. |
| `AIS_Claude_code_tigerblue77_memory_limit` | `2g` | Valeur de départ, à recaler sous charge. |
| `AIS_Claude_code_tigerblue77_home_Docker_volume_name` | `AIS_Claude_code_tigerblue77_home` | Le volume nommé du répertoire personnel **entier** -- voir plus bas pourquoi. |

Et celles que #76 apporte, pour LibreChat et sa base :

| Variable | Défaut | Description |
|---|---|---|
| `AIS_LibreChat_Docker_image_tag` | `v0.8.7` | Version stable explicite, jamais `-dev` ni `:latest`. |
| `AIS_MongoDB_LibreChat_Docker_image_tag` | `8.0.20` | Majeur explicite. |
| `AIS_LibreChat_creds_key` · `..._creds_IV` · `..._JWT_secret` · `..._JWT_refresh_secret` | aucun | **Obligatoires**, les quatre. Sans eux, LibreChat en génère des temporaires au premier démarrage. |
| `AIS_LibreChat_allow_registration` | `false` | Fermé : le port est publié sur le LAN. Comptes créés via `create-user`. |
| `AIS_LibreChat_uploads_Docker_volume_name` · `AIS_MongoDB_LibreChat_data_Docker_volume_name` | dérivés | Volumes nommés pour les pièces jointes et la base. |
| `AIS_LibreChat_memory_limit` · `AIS_MongoDB_LibreChat_memory_limit` | `1g` / `512m` | Valeurs de départ, à recaler sous charge. |
| `AIS_LibreChat_Dragnix_email` · `..._name` · `..._username` · `..._password` | aucun | **Obligatoires**, les quatre. Le compte de Dragnix, créé par le rôle et promu `ADMIN` -- voir plus bas. |

`false` et non `''` pour les deux réseaux publiés plus haut : ansible-core 2.19 refuse un test de vérité
sur autre chose qu'un booléen, donc « renseigné » s'écrit `is string`. C'est l'idiome des rôles Docker et
DNS du dépôt `Homelab_Ansible_deployment`, repris tel quel plutôt que réinventé.

Les deux se renseignent **ensemble ou pas du tout**, et le rôle le refuse autrement : n'en donner qu'un
produit soit un `docker-compose` qui référence un réseau non déclaré -- que l'orchestrateur ne signale
qu'au déploiement -- soit un réseau déclaré que personne n'utilise.

Trois ports hôte apparaissent dans ce rôle : le `4000` de LiteLLM (#1), le `20128` d'OmniRoute (#73) et
le `3080` de LibreChat (#76), chacun sous mot de passe ou compte nominatif -- voir plus bas pourquoi
chacun est une exception plutôt qu'une habitude. Les autres services internes se joignent par le réseau
du stack, et les rares interfaces web pensées pour passer par un reverse proxy le feront par celui de
l'appelant. Le jour où un autre port devra malgré tout être publié, il faudra qu'il esquive la liste
`kRestrictedPorts` de Chromium -- un port restreint est refusé *dans* le navigateur, avant que la
connexion ne le quitte, donc le service reste sain et ses journaux restent vides.

## OmniRoute -- le repli gratuit et sans clé (#73)

**Aucune clé de fournisseur n'est jamais connectée à ce service, et c'est le point central.** Il sert de
dernier recours à chaque cascade de repli de la passerelle (#2) : quand tous les fournisseurs à clé sont
épuisés, la requête atterrit ici plutôt que d'échouer. `check_LiteLLM_account_isolation.py` (#32)
reconnaît une entrée dont la clé est une chaîne littérale -- jamais `os.environ/...` -- comme
délibérément partagée entre tous les comptes, précisément parce qu'il n'y a aucun quota derrière elle à
protéger.

**Le mot de passe du tableau de bord est obligatoire, sans défaut.** L'image démarre avec `CHANGEME` si
rien n'est fourni -- documenté en amont comme volontairement faible pour forcer un changement. Traité
comme le mot de passe `/ui` de LiteLLM (#1) : vaulté, jamais laissé à son défaut.

## Qdrant -- déployé, pas encore rempli (#3)

**Périmètre volontairement partiel.** #3 déploie le serveur ; il ne crée aucune collection. Les créer
demande une dimension de vecteur, et cette dimension dépend du modèle d'embedding que #21 n'a pas
encore choisi -- en créer une maintenant serait deviner, exactement le genre de désalignement
silencieux que #3 met en garde contre. #21 crée les collections une fois le modèle choisi.

**Aucun `healthcheck:` ici, et c'est délibéré.** L'image officielle n'embarque ni sonde propre ni
outil pour en écrire une -- pas de `curl`, pas d'interpréteur, un durcissement amont volontaire, pas
un oubli. Un `CMD` qui nomme un binaire absent échouerait à chaque contrôle, rendant le service
*unhealthy* en permanence pour une raison étrangère à Qdrant lui-même -- exactement le piège que le
modèle commenté du template met en garde contre.

## LibreChat -- l'interface humaine de l'AIS (#76)

**`librechat.yaml` (`files/librechat/`) est copié, pas rendu.** Rien n'y a besoin de Jinja : la clé
d'API y est lue par LibreChat lui-même, avec sa propre syntaxe `${VAR}`, depuis l'environnement du
conteneur -- Ansible n'a rien à y interpoler. Repris du POC fonctionnel de tigerblue77, avec trois
corrections : deux identifiants de modèles absents du `model_list` réel de #2, et une `apiKey` qui
portait la clé maîtresse de la passerelle plutôt qu'une clé virtuelle dédiée.

**L'inscription est fermée.** Le port `3080` est publié sur le LAN, et une inscription ouverte y
donnerait à n'importe qui sur le réseau un accès aux quotas des deux comptes.

**Les quatre secrets de chiffrement sont obligatoires.** Sans eux, LibreChat en génère des temporaires
au premier démarrage et les écrit dans son propre volume -- ce que sa documentation déconseille
explicitement en production, précisément parce que rien ne les vaulte nulle part.

**Le compte de Dragnix se crée tout seul ; celui de tigerblue77 se crée à la main.** Une fois le stack
déployé, le rôle exécute lui-même `npm run create-user` dans le conteneur `librechat`, puis promeut ce
compte `ADMIN` par une écriture directe dans MongoDB (`mongosh ... updateOne`) plutôt que de compter
sur le comportement « le premier compte est admin » de LibreChat -- des retours d'expérience amont le
signalent silencieusement inopérant, ce qui en aurait fait une hypothèse plutôt qu'un fait. Dragnix,
une fois connecté avec ce compte admin, crée celui de tigerblue77 lui-même depuis le panneau
d'administration : rien à automatiser côté Ansible pour un compte que la personne qui le possède peut
créer en trente secondes une fois qu'elle a un accès admin.

Techniquement, deux choses ont été vérifiées en direct plutôt que supposées avant d'écrire ces tâches :

- **`create-user` se bloque si on lui répond par une entrée standard multi-lignes.** Le script ouvre
  une nouvelle interface `readline` par question et la ferme aussitôt après ; si toute la réponse
  arrive d'un coup (comme le fait un `docker exec -i` alimenté par un `printf | ...`), les lignes au-delà
  de la première se perdent entre deux interfaces, et le script attend indéfiniment une question à
  laquelle il a déjà, sans le savoir, reçu une réponse. La solution qui évite complètement le problème :
  passer le mot de passe en 4ᵉ argument positionnel et `--email-verified=true` en option, ce que le
  script lit avant de songer à demander l'un ou l'autre -- aucune invite ne se déclenche.
- **Le conteneur est trouvé par son étiquette Compose**, `com.docker.compose.service=librechat`, plutôt
  que par un nom deviné : le nommage de Compose (`<projet>-<service>-<n>`) n'est le contrat de rien ici,
  l'étiquette si. **Ceci ne fonctionne que sous Compose.** Sous Swarm, le nœud qui exécute cette tâche
  n'est pas forcément celui qui héberge le conteneur `librechat` -- Swarm peut le placer sur n'importe
  quel nœud du cluster -- et ce rôle ne cherche pas sur quel nœud il tourne réellement. La tâche ne
  trouve alors rien et se saute proprement plutôt que d'agir sur le démon Docker du mauvais nœud ;
  cela reste à faire le jour où la cible réelle est Swarm.

Les deux mécanismes ont été vérifiés contre un vrai `docker compose up` de ces deux services (création,
ré-exécution idempotente, cas « compte déjà existant », promotion `ADMIN` idempotente), pas seulement
lus dans la documentation amont.

## Le contrat du rôle de déploiement

Ce rôle rend le stack, il ne le déploie pas. `AIS_Docker_stack_deployment_role_name` nomme celui qui s'en
charge, et ce rôle-là doit :

1. **rendre `{{ Docker_compose_file_name }}.j2` depuis le `templates/` de son appelant**, c'est-à-dire
   depuis celui du rôle AIS. C'est le point qui fait tenir tout le reste : un dépôt peut fournir un stack
   sans fournir la mécanique qui le déploie ;
2. lire `Docker_stack_name`, `Docker_compose_file_destination_path` et
   `Docker_compose_file_destination_directory`, que `tasks/main.yml` lui passe en paramètres
   d'`include_role` ;
3. écrire le fichier rendu en **`0600` et avec `diff: false`**. Le stack n'interpole encore aucun secret,
   mais il en interpolera dès la première issue de service -- clés d'API de quatre fournisseurs, clé
   maîtresse de la passerelle, jetons. `/tmp` est le premier endroit où tout compte de la machine regarde,
   et `--diff` imprimerait le fichier *entier* dans la sortie du run, donc dans tout ce qui la capture.

Et une quatrième obligation, qui pèse sur l'**appelant** et non sur le rôle nommé : **ce que ce rôle-là
exige en plus, c'est à l'appelant de le fournir.** Ni ce rôle-ci ni ses `assert` ne peuvent le deviner —
le rôle de déploiement est désigné par une variable, donc son contenu est inconnu au moment où les
vérifications tournent.

Ce n'est pas théorique. `Docker/deploy_Docker_swarm_stack` et `Docker/deploy_Docker_compose_stack` du
dépôt `Homelab_Ansible_deployment` remplissent tous les deux les trois obligations ci-dessus **sans
modification** — mais tous les deux lisent aussi `APT_cache_lifetime`, qui n'a de défaut ni dans l'un ni
dans l'autre. Elle vit dans les `vars:` du `playbook.CHSONP.yaml` de ce dépôt, donc elle est en portée
quand c'est lui qui appelle, et **absente partout ailleurs**. Un appelant qui ne la déclare pas échoue au
déploiement, sur une variable non définie, à l'intérieur d'un rôle d'un autre dépôt, portant un nom qui
n'apparaît nulle part dans l'appel qu'il a écrit.

Les deux rôles rendent en plus deux faits que les issues de service voudront lire :
`Docker_stack_first_deployment`, qui dit si le stack est déployé pour la première fois sur cette machine,
et `Docker_stack_deployment_state`.

## La passerelle et sa base (#1)

Deux services, et deux fichiers rendus sur le nœud : le `docker-compose` -- qui porte les deux
secrets, interpolés directement par Ansible -- et la configuration de routage de LiteLLM, montée en
lecture seule et sans secret propre.

**Le port `4000` est publié, à rebours du choix initial de #1 -- décision de Dragnix, validée par
tigerblue77 le 07/09/2026 : le compromis (HTTP sans TLS, authentification basique seule, port ouvert
sur tout le LAN) est accepté tel quel, sur un LAN jugé de confiance.** Chaque compte ajoute ses propres
clés fournisseur depuis `/ui`, à la main, plutôt que de les faire
rendre depuis un vault : c'est le même modèle que les autres bases auto-hébergées de cette estate --
déployées vides, peuplées en direct, sauvegardées de temps en temps dans leur dépôt -- et `/ui` doit donc
être joignable depuis un simple navigateur du LAN, avant même qu'un reverse proxy existe pour le faire à
sa place. Le coût n'est pas nul : pas de TLS, et l'authentification `UI_USERNAME` / `UI_PASSWORD` (voir
`AIS_LiteLLM_UI_password` plus haut) comme seule chose entre le LAN et le conteneur qui porte la clé
maîtresse et les clés fournisseur des deux comptes. Un reverse proxy devant `/ui` reste la suite logique,
pas une clause de style.

**Les deux secrets vivent dans le fichier compose, pas dans un `.env` à part.** `AIS_PostgreSQL_password`
et `AIS_LiteLLM_master_key` sont interpolés par Ansible au rendu, comme le reste du template -- c'est ce
qui permet à la même forme de servir Compose et Swarm sans y toucher : Ansible rend ce fichier de la
même façon quel que soit celui qui le lira ensuite. C'est aussi pourquoi le fichier compose porte déjà
l'obligation `0600` / `diff: false` du contrat du rôle de déploiement : elle existe depuis #31,
précisément pour le jour où le template interpolerait un secret.

**La clé maîtresse ne sort pas du conteneur.** Elle sert à l'administration depuis Ansible, à rien
d'autre. Open WebUI, N8N, le conteneur Claude Code et le bot Discord reçoivent chacun une clé virtuelle
portant sa propre liste blanche de modèles — c'est #2 qui les crée. Un client qui détient la clé maîtresse
rend inutile tout le travail d'isolation de #2.

**Le plancher de version est vérifié par le rôle, pas par la relecture.** `tasks/main.yml` refuse un tag
inférieur à `AIS_LiteLLM_minimum_secure_version`, et refuse `main-latest`. La comparaison se fait avec le
test `version` d'Ansible et non en chaînes : `1.100.0` est bien supérieur à `1.84.0`, ce qu'une
comparaison de chaînes affirme à l'envers. Le plancher est à **re-vérifier le jour du déploiement** contre
les avis amont : quatre CVE critiques en quatre mois sur ce produit en 2026, dont une injection SQL
*pré-authentifiée* visant précisément la base déployée ici.

### Un point qui attend la bascule Swarm, et un qui ne l'attend plus

L'interpolation par Ansible plutôt que par un `.env` a réglé le premier problème d'elle-même : rendre
le fichier compose est le travail d'Ansible, pas de l'orchestrateur, donc la bascule Compose → Swarm ne
change rien à la façon dont les deux secrets y arrivent.

Ce qui reste à traiter à ce moment-là : **LiteLLM lit `os.environ/…`** pour sa clé maîtresse et son URL
de base, valeurs que le compose lui passe en clair via `environment:`. Swarm sait faire pareil, à
l'identique -- ce n'est donc pas un blocage -- mais le jour de la bascule est le bon moment pour se
demander si les secrets natifs de Swarm ne valent pas mieux que des variables en clair dans le fichier
rendu, question que Compose ne se pose de toute façon pas.

`depends_on` relève d'un registre voisin : c'est une facilité de Compose, **Swarm l'ignore**. LiteLLM doit
donc tolérer une base pas encore prête, et c'est la politique de redémarrage qui rattrape le cas — pas
l'ordre de démarrage. Le bloc est conservé parce qu'il épargne un premier démarrage en échec au banc
d'essai.

## Le `model_list` de tigerblue77 (#2, périmètre v1)

`LiteLLM_config.yaml.j2` porte désormais le `model_list` réel de tigerblue77 -- une soixantaine
d'entrées à travers Gemini, GitHub Models, Mistral, Cerebras, Groq, OpenRouter (`:free`) et OmniRoute
en dernier recours -- repris de son propre POC fonctionnel plutôt que ré-inventé. DeepSeek (#101) s'y
ajoute en accès direct, seul fournisseur payant du fichier : placé en dernier recours dans chaque
cascade où il apparaît, juste avant OmniRoute, qui reste le seul vraiment gratuit.

**Un seul compte dans ce `model_list`, et c'est un choix assumé, pas un oubli.** tigerblue77 ajoute les
siennes lui-même depuis `/ui` (voir `AIS_LiteLLM_UI_password` plus haut) : même modèle que ses autres
bases auto-hébergées, déployées vides puis peuplées en direct. Chaque entrée porte déjà
`model_info.access_groups: ["tigerblue77"]`, pour qu'une deuxième personne n'ait rien à reprendre ici --
voir « Un compte par personne, pas une paire figée » plus bas pour comment elle obtient le sien.
#2 demande encore davantage : `rpm_limit` / `tpm_limit` par clé, la segmentation `sci-*` / `gen-*`, le
test négatif inter-comptes exécutable -- resté ouvert sur #2, délibérément pas tenté ici.

**La clé d'API décide du compte, jamais le nom du modèle.** `check_LiteLLM_account_isolation.py` (#32)
attribue chaque entrée à un compte par le nom de sa variable d'environnement -- `os.environ/GEMINI_
API_KEY_TIGERBLUE77` appartient à `TIGERBLUE77` -- et non par le `model_name` ou par
`access_groups`, qui ne sont que des étiquettes. C'est pour cette convention que les six clés de
tigerblue77 sont exposées au conteneur sous ce nom précis plutôt que sous leur nom usuel (`GITHUB_
TOKEN` devient `GITHUB_API_KEY_TIGERBLUE77`, par exemple) : LiteLLM ne se soucie pas du nom de la
variable, seul ce contrôle en a besoin.

**OmniRoute n'appartient à personne, et c'est voulu.** Son `api_key` est une chaîne littérale, jamais
`os.environ/...` -- ce que la règle « aucun secret en clair, jamais » de ce dépôt rend sans ambiguïté :
une valeur littérale ne peut être qu'un marqueur pour un service qui n'a besoin d'aucune information
d'authentification, jamais un oubli. `check_LiteLLM_account_isolation.py` reconnaît maintenant cette
forme et l'exempte des règles 1 et 2 : il n'y a aucun quota à lui attribuer, donc aucun à protéger.

### Un compte par personne, pas une paire figée (#103)

`AIS_LiteLLM_internal_users` est une **liste**, vide par défaut, jamais deux variables nommées
(`_tigerblue77`, `_Dragnix`, ...) : figer sur deux noms fait de l'ajout d'une troisième personne une
modification de structure du rôle plutôt qu'une ligne ajoutée à une liste. `tasks/main.yml` boucle
dessus et, pour chaque `{username, email}`, crée un compte LiteLLM au rôle `internal_user` --
self-service (peut créer/voir/supprimer ses propres clés, voir sa propre consommation) et rien
d'autre : jamais les clés d'un autre compte, jamais la configuration de la passerelle. Le compte
`AIS_LiteLLM_UI_username`/`_password` (admin, plus haut) n'a pas sa place dans cette liste : il a déjà
un accès complet par le mécanisme natif de LiteLLM, une entrée ici ne lui apporterait rien.

La clé de chaque compte est scopée à `access_group:<username>` dès sa création -- le même mécanisme
d'`access_groups` que le `model_list` de tigerblue77 porte déjà (plus haut) -- et `POST /key/generate`
n'est appelé **qu'une fois par compte, pour toujours** : la tâche se déclenche seulement l'exécution où
`POST /user/new` vient tout juste de créer ce compte (409 ensuite, pour toujours), jamais sur la base
du comportement propre de `/key/generate` rejoué, qui reste à vérifier contre une instance réelle (voir
« Non vérifié » plus bas). Cette clé n'est montrée qu'**une seule fois**, dans la sortie de ce rôle, le
jour où elle est réellement créée : LiteLLM ne la restitue pas une seconde fois, au même titre qu'un
jeton GitHub ou un mot de passe de registre. C'est cette clé-là, et non un compte LiteLLM partagé, que
la personne colle ensuite dans son propre compte LibreChat -- voir juste en dessous.

**`librechat.yaml` route désormais chaque compte LibreChat vers sa propre identité côté passerelle.**
`apiKey: "user_provided"` (au lieu d'une clé unique lue dans l'environnement du conteneur) fait que
LibreChat demande sa propre clé à CHAQUE compte, la première fois qu'il utilise cet endpoint, et la
retient chiffrée pour lui seul. Avant #103, une seule clé virtuelle servait tout le conteneur : n'importe
quel compte LibreChat, humain ou non, parlait à la passerelle sous la même identité, ce qui défaisait
l'isolation par compte dès qu'un deuxième humain existait -- même avec son propre compte LiteLLM créé
par la liste ci-dessus, rien ne l'aurait fait passer par lui plutôt que par l'unique clé partagée.
`AIS_LibreChat_LiteLLM_virtual_key` et son `assert` obligatoire disparaissent avec ce changement :
plus personne n'a besoin de pré-fabriquer une clé virtuelle avant que LibreChat ne tourne, ce qui
règle au passage le problème d'ordre de démarrage que ce même `assert` posait (LiteLLM devait tourner
pour émettre une clé via son propre `/key/generate`, et rien ne se déployait tant que l'`assert`
n'était pas satisfait).

**Redis, déployé par #71.** Le cache de réponses (préserve les quotas TPM des paliers gratuits) et
l'état de cooldown partagé entre les workers de LiteLLM en avaient besoin ; ni #1 ni #2 n'en avait le
périmètre à l'origine. `--requirepass` est obligatoire, sans défaut, même raisonnement que la clé
d'API de Qdrant (#3) : défense en profondeur sur un service interne, sans port publié. **Le
cloisonnement du cache entre comptes n'est pas vérifié depuis cette session** -- documenté en amont
comme limité à la clé/l'équipe/l'organisation par défaut, mais à confirmer sur le banc d'essai avant
d'y faire confiance ; #79 est ouverte pour ça, voir aussi le commentaire dans
`LiteLLM_config.yaml.j2`.

**Un modèle repéré comme vieillissant, laissé en place.** `gemini-2-5-flash` est plusieurs générations
derrière la ligne `gemini-3.x` déjà prioritaire partout où il apparaît, et #2 le signale comme tel --
mais rien ne confirme qu'il soit réellement retiré, et il ne figure qu'en dernier recours dans les
cascades. Retiré ou confirmé au prochain audit de #2, pas ici.

## L'agent Claude Code -- tigerblue77 (#13)

Construit **sur** l'image publiée par `Claude-Code-Docker-container`, jamais reconstruit depuis une
base nue : cette image porte déjà le CLI épinglé, l'utilisateur non-root `node` et l'auto-updater
désactivé, et repartir d'une base Node nue referait tout cela une seconde fois, avec le risque de le
refaire différemment.

**`build:`, pas `image:` seul, parce que ce compte a besoin de plus que l'agent.** `gh`, `ansible-core`
et de l'outillage de compilation s'ajoutent par-dessus l'image publiée -- ce sont les outils du travail
d'infrastructure de tigerblue77, pas des besoins de Claude Code lui-même. Le `Dockerfile` est **rendu**
par ce rôle (`templates/claude_code_tigerblue77.Dockerfile.j2`) plutôt que copié tel quel : l'image dont
il part reste ainsi une seule valeur dans `defaults/main.yml`, épinglée par tag et digest, plutôt qu'une
seconde copie figée dans un fichier statique.

**Le répertoire personnel monté est `/home/node` en entier, jamais `~/.claude` seul.** C'est le piège
d'authentification que le dépôt amont documente sur lui-même : `~/.claude.json` vit À CÔTÉ de
`~/.claude`, pas dedans, et un volume sur `~/.claude` seul perd la moitié de la session à chaque
recréation du conteneur, sans qu'aucune erreur ne le signale. L'entrée du conteneur restaure ce fichier
depuis la plus récente de ses propres sauvegardes si le volume est neuf.

**Aucun montage de `docker.sock` dans cette issue.** #11 n'a pas encore conçu l'isolation qu'un agent
doit respecter avant de pouvoir atteindre le démon Docker de l'hôte, et ce conteneur attend cette
décision plutôt que de la devancer. `docker.io` est installé mais inerte : rien ne branche le socket
tant que #11 n'a pas tranché.

**Le jeton GitHub est un jeton personnel, pas encore le connecteur MCP.** #13 délègue l'accès aux
dépôts au connecteur MCP GitHub (#23) et l'accès aux outils à la passerelle MCP (#7) ; en attendant que
l'un ou l'autre existe, `AIS_Claude_code_tigerblue77_GitHub_token` est ce qui permet à `gh` et à git de
fonctionner à l'intérieur du conteneur.

**Le modèle est un alias, jamais un nom de modèle Anthropic littéral.** `ANTHROPIC_BASE_URL` pointe sur
la passerelle interne (`litellm:4000`, #1), jamais sur l'API Anthropic, et `ANTHROPIC_MODEL` porte
l'alias `claude-code` que #2 résout dans LiteLLM. C'est le point de conformité de #13 : quoi que cet
alias résolve, ce ne doit jamais être un modèle Anthropic adossé à un abonnement.

**Ce service ne dépend pas de #1 pour être mergé, seulement pour tourner.** Il se déploie et se rend
indépendamment ; c'est au démarrage du conteneur, une fois `litellm` réellement présent, que
`ANTHROPIC_BASE_URL` doit pouvoir le résoudre.

## Ce que ce squelette ne fait pas

- **Il ne déploie plus rien de vide, mais il n'a pas été déployé.** Depuis #1, `services:` porte
  `postgres` et `litellm` **inconditionnellement**, et depuis #73, #3 et #76 `omniroute`, `qdrant` et
  `librechat`/`librechat_mongodb` les rejoignent, inconditionnellement aussi. Depuis #13,
  `claude_code_tigerblue77` s'y ajoute en plus quand `AIS_Claude_code_tigerblue77_enabled` vaut
  `true` (`false` par défaut -- #31 exige que chaque service se déclare ainsi) ; dans tous les états,
  les seuls ports qui apparaissent dans la configuration résolue sont le `4000` de LiteLLM, le
  `20128` d'OmniRoute et le `3080` de LibreChat, publiés à dessein -- Qdrant n'en publie aucun. La
  case « le rôle se déploie sur la VM de test et les conteneurs démarrent » de #31 devient donc
  vérifiable sur le banc d'essai, pas avant. Le compte de Dragnix et sa promotion `ADMIN` sont
  vérifiés contre un vrai `docker compose up` (voir plus haut) ; ce qui reste à faire sur une vraie
  machine : la mesure sous charge des limites mémoire, la persistance après un `down` / `up`,
  l'idempotence sur un second passage, et, hors du périmètre de #3, la création des collections
  Qdrant une fois le modèle d'embedding choisi (#21).
- **Il ne fournit ni `.gitignore`, ni `.env.example`, ni intégration continue.** #31 et #32 revendiquaient
  tous deux le `.env.example` ; il revient à #32, avec les garde-fous dont il fait partie.
- **Il ne tranche pas la topologie réseau.** Un seul réseau interne, parce que #7 décidera la séparation
  collecteur / acteur et que c'est cette décision-là qui dira s'il en faut deux ou trois. Un squelette qui
  la préempterait ferait le contraire de son travail.

## Pourquoi tout vit sous `deploy:`

Le modèle commenté dans le template écrit les limites de ressources et la politique de redémarrage sous
`deploy:`, et jamais sous leurs équivalents de premier niveau. C'est la seule forme que **Compose et Swarm
honorent tous les deux**, et c'est ce qui permet au rôle de ne présupposer aucun orchestrateur : la cible
d'aujourd'hui est une VM en Compose, celle de demain est Swarm, et la bascule ne doit pas rouvrir ce
fichier.

Écrites autrement, les mêmes intentions se perdent en silence :

| Clé | Compose | Swarm |
|---|---|---|
| `restart: unless-stopped` | fonctionne | **ignoré** — il faut `deploy.restart_policy.condition: any` |
| `mem_limit` / `cpus` | fonctionnent | **ignorés** — remplacés par `deploy.resources.limits` |
| `depends_on` | ordonne le démarrage | accepté, **sans effet** |
| `shm_size` | fonctionne | **ignoré** |
| `container_name` | fonctionne | déprécié — ne jamais s'en servir comme nom d'hôte |
| Secrets | fichier ou variable | secrets natifs de l'orchestrateur |

Sur `restart_policy` : `condition: any`, jamais `on-failure`. Quand un conteneur devient malsain,
l'orchestrateur l'arrête **proprement** ; le processus sort avec le code 0 ; et `on-failure` ne remplace
jamais une tâche sortie proprement. Le service reste à 0 réplique, le reverse proxy ne construit plus de
route à partir des tâches en cours d'exécution, et l'URL répond un 404 nu sans que rien ne soit journalisé
nulle part. C'est une panne que le dépôt `Homelab_Ansible_deployment` a déjà payée une fois.

Que Compose v2 honore bien `deploy.resources.limits` et `deploy.restart_policy` est l'hypothèse sur
laquelle repose ce choix. Elle est documentée par Compose, et elle **reste à confirmer sur le banc
d'essai** avec la première issue de service : rien de ce qui est ici ne démarre de conteneur, donc rien
ici ne la prouve.

## Vérifier une modification du template

Lire le diff ne suffit pas, et « Auto-merging » non plus : les conflits qui font mal ici sont sémantiques,
pas textuels. Le template se **rend** et le résultat se **parse** :

```bash
yamllint .
ansible-lint
ansible-playbook --syntax-check playbook.AIS.example.yaml
python3 .github/scripts/check_compose_template.py
```

Le dernier est celui qui compte pour le template. Il le rend dans ses **deux** états -- réseau publié
renseigné et non renseigné -- parse les deux, compare les objets parsés plutôt que les fichiers, et tient
chaque bloc de service aux conventions que le modèle commenté du template documente : image épinglée,
limite mémoire, `restart_policy.condition: any`, pas de `container_name`, et tout réseau ou volume
référencé effectivement déclaré.

L'état « désactivé » est celui que personne ne regarde, et une condition Jinja qui ne marche que quand la
fonctionnalité est active est un défaut qui part en production. C'est pour cela que les deux états sont
rendus, et que le contrôle refuse qu'activer le réseau publié change autre chose que le bloc `networks:`.

## Exemple d'appel

```yaml
- role: deploy_AIS_Docker_stack
  vars:
    AIS_Docker_stack_deployment_role_name: "Docker/deploy_Docker_swarm_stack"
    AIS_server_time_zone: "{{ server_time_zone | default('Etc/UTC') }}"
```

`playbook.AIS.example.yaml`, à la racine du dépôt, en donne la version complète et commentée.

## Dépendances

Aucune déclarée dans `meta/`. Le rôle en inclut une à l'exécution -- celle que l'appelant nomme -- et c'est
précisément pour qu'elle ne soit pas déclarée ici qu'elle est un paramètre.

Une collection, en revanche, l'est dans `requirements.yml` à la racine du dépôt depuis #76 :
`community.docker`, pour les deux modules qui créent le compte de Dragnix. Voir « Prérequis » plus
haut.

## Licence

Double licence, et les deux arms ne sont pas symétriques :

- **AGPL-3.0-only** pour tout le monde, sans frais et sans formalité. Le texte est dans [`LICENSE`](LICENSE) ;
- ou une **licence commerciale négociée séparément**, pour qui ne peut pas tenir les obligations de l'AGPL.

Le choix est celui du destinataire. Prendre ce travail sous l'AGPL ne demande ni permission, ni
enregistrement, ni notification à quiconque.

Trois fichiers portent le reste, et ils se renvoient l'un à l'autre :

| Fichier | Ce qu'il dit |
|---|---|
| [`LICENSE-COMMERCIAL.md`](LICENSE-COMMERCIAL.md) | Ce que couvre l'arm commercial, dans quels cas il est nécessaire — presque jamais — et comment le demander. **Ce n'est pas une licence** : c'est la description d'une offre de négocier. |
| [`NOTICE`](NOTICE) | Le titulaire, l'absence d'historique de licence, et le matériel tiers — au premier chef les images que le stack nommera, qui gardent chacune leur licence et ne deviennent pas des œuvres dérivées de ce dépôt. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | La clause qui permet à une contribution d'être offerte sous les **deux** arms. Elle est arrivée avant la première contribution extérieure, ce qui est la seule façon qu'elle avait de les couvrir toutes. |

Chaque fichier source de ce dépôt porte un en-tête SPDX. Les templates n'en portent pas : ils sont rendus
sur les nœuds gérés, et l'en-tête finirait recopié dans le `docker-compose` déployé.

## Auteur

[tigerblue77](https://github.com/tigerblue77)
