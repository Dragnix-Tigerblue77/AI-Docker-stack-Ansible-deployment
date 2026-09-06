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
| `AIS_environment_file_name` · `..._destination_path` | `.env` | Le fichier d'environnement, rendu `0600` depuis le vault. |
| `AIS_LiteLLM_config_file_name` · `..._destination_path` | `LiteLLM_config.yaml` | La configuration de routage, montée en lecture seule. #2 en remplit le `model_list`. |

`false` et non `''` pour les deux derniers : ansible-core 2.19 refuse un test de vérité sur autre chose
qu'un booléen, donc « renseigné » s'écrit `is string`. C'est l'idiome des rôles Docker et DNS du dépôt
`Homelab_Ansible_deployment`, repris tel quel plutôt que réinventé.

Les deux se renseignent **ensemble ou pas du tout**, et le rôle le refuse autrement : n'en donner qu'un
produit soit un `docker-compose` qui référence un réseau non déclaré -- que l'orchestrateur ne signale
qu'au déploiement -- soit un réseau déclaré que personne n'utilise.

Aucun port hôte n'apparaît dans ce rôle, et c'est voulu : les services internes se joignent par le réseau
du stack, et les rares interfaces web passent par le reverse proxy de l'appelant. Le jour où un port devra
malgré tout être publié, il faudra qu'il esquive la liste `kRestrictedPorts` de Chromium -- un port
restreint est refusé *dans* le navigateur, avant que la connexion ne le quitte, donc le service reste sain
et ses journaux restent vides.

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

Deux services, et trois fichiers rendus sur le nœud : le `docker-compose`, un `.env` en `0600`, et la
configuration de routage de LiteLLM montée en lecture seule.

**Aucun port publié, et c'est le point central.** Le conteneur LiteLLM détient les clés Gemini / Groq /
Mistral des *deux* comptes plus la clé maîtresse. Publié tel quel — sans TLS, sans authentification en
frontal — il répond à tout ce qui se branche sur le LAN. Le port `4000` reste donc un port du réseau du
stack. La conséquence est assumée : `/ui` n'est plus joignable depuis un navigateur du LAN, et son
exposition éventuelle est une décision distincte, qui passerait par le reverse proxy de l'appelant.

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

### Deux points qui attendent la bascule Swarm

Ils sont écrits ici pour ne pas être découverts à ce moment-là :

1. **Le `.env` n'est lu que par Compose.** Compose le trouve parce qu'il est dans le *répertoire de
   projet*, celui du fichier de compose — c'est pourquoi les deux chemins dérivent du même répertoire.
   `docker stack deploy` interpole depuis l'environnement du *shell* : la bascule demandera soit un
   `set -a; . ./.env`, soit des secrets natifs.
2. **LiteLLM lit `os.environ/…`.** Les secrets Swarm se montent en fichiers, donc le passage demandera
   soit un point d'entrée qui exporte le contenu du fichier, soit les variantes `*_FILE` là où elles
   existent.

`depends_on` relève du même registre : c'est une facilité de Compose, **Swarm l'ignore**. LiteLLM doit
donc tolérer une base pas encore prête, et c'est la politique de redémarrage qui rattrape le cas — pas
l'ordre de démarrage. Le bloc est conservé parce qu'il épargne un premier démarrage en échec au banc
d'essai.

Ce que ce squelette ne fait pas
-------------------------------

- **Il ne déploie plus rien de vide, mais il n'a pas été déployé.** Depuis #1, `services:` porte
  `postgres` et `litellm`, le fichier rendu passe `docker compose config`, et aucun port n'apparaît dans
  la configuration résolue. Ce qui reste à faire sur une vraie machine : la mesure sous charge des deux
  limites mémoire, le test négatif d'exposition depuis une autre machine, la persistance après un
  `down` / `up`, et l'idempotence sur un second passage.
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
