<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

deploy_AIS_Docker_stack
=======================

Rend le `docker-compose` du stack AIS -- *Artificial Intelligence Stack* -- et délègue son déploiement au
rôle que l'appelant désigne.

C'est le contenant, pas le contenu : le stack ne comporte encore aucun service, et chaque issue de service
viendra y ajouter son bloc et ses variables. Ce que ce rôle apporte aujourd'hui est la forme -- un rôle qui
ne présuppose ni machine, ni domaine, ni compte, ni orchestrateur, et un template dont les conventions sont
écrites à l'endroit où on les oublie.

Prérequis
---------

- Un rôle capable de déployer le stack, nommé par `AIS_Docker_stack_deployment_role_name`, et résoluble
  depuis le `roles_path` de l'appelant. Ce dépôt n'en fournit aucun : voir le contrat plus bas.
- Rien d'autre. Le rôle n'utilise que `assert` et `include_role`, donc aucune collection, aucun paquet
  et aucun fait rassemblé.

Variables du rôle
-----------------

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

`false` et non `''` pour les deux derniers : ansible-core 2.19 refuse un test de vérité sur autre chose
qu'un booléen, donc « renseigné » s'écrit `is string`. C'est l'idiome des rôles Docker et DNS du dépôt
`Homelab_Ansible_deployment`, repris tel quel plutôt que réinventé.

Les deux se renseignent **ensemble ou pas du tout**, et le rôle le refuse autrement : n'en donner qu'un
produit soit un `docker-compose` qui référence un réseau non déclaré -- que l'orchestrateur ne signale
qu'au déploiement -- soit un réseau déclaré que personne n'utilise.

Deux ports hôte apparaissent dans ce rôle : le `4000` de LiteLLM (#1) et le `20128` d'OmniRoute (#73),
chacun sous mot de passe -- voir plus bas pourquoi chacun est une exception plutôt qu'une habitude. Les
autres services internes se joignent par le réseau du stack, et les rares interfaces web pensées pour
passer par un reverse proxy le feront par celui de l'appelant. Le jour où un autre port devra malgré tout
être publié, il faudra qu'il esquive la liste `kRestrictedPorts` de Chromium -- un port restreint est
refusé *dans* le navigateur, avant que la connexion ne le quitte, donc le service reste sain et ses
journaux restent vides.

OmniRoute -- le repli gratuit et sans clé (#73)
------------------------------------------------

**Aucune clé de fournisseur n'est jamais connectée à ce service, et c'est le point central.** Il sert de
dernier recours à chaque cascade de repli de la passerelle (#2) : quand tous les fournisseurs à clé sont
épuisés, la requête atterrit ici plutôt que d'échouer. `check_LiteLLM_account_isolation.py` (#2)
reconnaît une entrée dont la clé est une chaîne littérale -- jamais `os.environ/...` -- comme
délibérément partagée entre tous les comptes, précisément parce qu'il n'y a aucun quota derrière elle à
protéger.

**Le mot de passe du tableau de bord est obligatoire, sans défaut.** L'image démarre avec `CHANGEME` si
rien n'est fourni -- documenté en amont comme volontairement faible pour forcer un changement. Traité
comme le mot de passe `/ui` de LiteLLM (#1) : vaulté, jamais laissé à son défaut.

Qdrant -- déployé, pas encore rempli (#3)
--------------------------------------------

**Périmètre volontairement partiel.** #3 déploie le serveur ; il ne crée aucune collection. Les créer
demande une dimension de vecteur, et cette dimension dépend du modèle d'embedding que #21 n'a pas
encore choisi -- en créer une maintenant serait deviner, exactement le genre de désalignement
silencieux que #3 met en garde contre. #21 crée les collections une fois le modèle choisi.

**Aucun `healthcheck:` ici, et c'est délibéré.** L'image officielle n'embarque ni sonde propre ni
outil pour en écrire une -- pas de `curl`, pas d'interpréteur, un durcissement amont volontaire, pas
un oubli. Un `CMD` qui nomme un binaire absent échouerait à chaque contrôle, rendant le service
*unhealthy* en permanence pour une raison étrangère à Qdrant lui-même -- exactement le piège que le
modèle commenté du template met en garde contre.

Le contrat du rôle de déploiement
---------------------------------

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

La passerelle et sa base (#1)
-----------------------------

Deux services, et deux fichiers rendus sur le nœud : le `docker-compose` -- qui porte les deux
secrets, interpolés directement par Ansible -- et la configuration de routage de LiteLLM, montée en
lecture seule et sans secret propre.

**Le port `4000` est publié, à rebours du choix initial de #1 -- décision de Dragnix, actée dans la
session qui a écrit cette phrase, à faire valider par tigerblue77 à la reprise de leur discussion.**
Chaque compte ajoute ses propres clés fournisseur depuis `/ui`, à la main, plutôt que de les faire
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

Le `model_list` de tigerblue77 (#2, périmètre v1)
--------------------------------------------------

`LiteLLM_config.yaml.j2` porte désormais le `model_list` réel de tigerblue77 -- une soixantaine
d'entrées à travers Gemini, GitHub Models, Mistral, Cerebras, Groq, OpenRouter (`:free`) et OmniRoute
en dernier recours -- repris de son propre POC fonctionnel plutôt que ré-inventé.

**Un seul compte pour l'instant, et c'est un choix assumé, pas un oubli.** Dragnix ajoute les siennes
lui-même depuis `/ui` (voir `AIS_LiteLLM_UI_password` plus haut) : même modèle que ses autres bases
auto-hébergées, déployées vides puis peuplées en direct. #2 demande davantage -- équipes et clés
virtuelles créées par tâches Ansible idempotentes via l'API de LiteLLM, `rpm_limit` / `tpm_limit` par
clé, la segmentation `sci-*` / `gen-*`, le test négatif inter-comptes exécutable -- et c'est un travail
réel qui reste ouvert sur #2 ; il n'est délibérément pas tenté ici. Chaque entrée porte déjà
`model_info.access_groups: ["tigerblue77"]`, pour que ce travail ait une chose de moins à reprendre.

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

L'agent Claude Code -- tigerblue77 (#13)
-----------------------------------------

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

Ce que ce squelette ne fait pas
-------------------------------

- **Il ne déploie plus rien de vide, mais il n'a pas été déployé.** Depuis #1, `services:` porte
  `postgres` et `litellm` **inconditionnellement**, et depuis #73 et #3 `omniroute` et `qdrant` les
  rejoignent, inconditionnellement aussi. Depuis #13, `claude_code_tigerblue77` s'y ajoute en plus
  quand `AIS_Claude_code_tigerblue77_enabled` vaut `true` (`false` par défaut -- #31 exige que chaque
  service se déclare ainsi) ; dans les deux états, les seuls ports qui apparaissent dans la
  configuration résolue sont le `4000` de LiteLLM et le `20128` d'OmniRoute, publiés à dessein --
  Qdrant n'en publie aucun. La case « le rôle se déploie sur la VM de test et les conteneurs
  démarrent » de #31 devient donc vérifiable sur le banc d'essai, pas avant. Ce qui reste à faire sur
  une vraie machine : la mesure sous charge des limites mémoire, la persistance après un `down` /
  `up`, l'idempotence sur un second passage -- et, hors du périmètre de #3, la création des
  collections Qdrant une fois le modèle d'embedding choisi (#21).
- **Il ne fournit ni `.gitignore`, ni `.env.example`, ni intégration continue.** #31 et #32 revendiquaient
  tous deux le `.env.example` ; il revient à #32, avec les garde-fous dont il fait partie.
- **Il ne tranche pas la topologie réseau.** Un seul réseau interne, parce que #7 décidera la séparation
  collecteur / acteur et que c'est cette décision-là qui dira s'il en faut deux ou trois. Un squelette qui
  la préempterait ferait le contraire de son travail.

Pourquoi tout vit sous `deploy:`
--------------------------------

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

Exemple d'appel
---------------

```yaml
- role: deploy_AIS_Docker_stack
  vars:
    AIS_Docker_stack_deployment_role_name: "Docker/deploy_Docker_swarm_stack"
    AIS_server_time_zone: "{{ server_time_zone | default('Etc/UTC') }}"
```

`playbook.AIS.example.yaml`, à la racine du dépôt, en donne la version complète et commentée.

Dépendances
-----------

Aucune déclarée dans `meta/`. Le rôle en inclut une à l'exécution -- celle que l'appelant nomme -- et c'est
précisément pour qu'elle ne soit pas déclarée ici qu'elle est un paramètre.

Licence
-------

AGPL-3.0-only, ou une licence commerciale distincte. Voir `LICENSE` à la racine du dépôt.

Auteur
------

[tigerblue77](https://github.com/tigerblue77)
