<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# AI-Docker-stack

Déploiement Ansible de l'**AIS** -- *Artificial Intelligence Stack* : la stack Docker qui regroupe toutes
les briques liées à l'IA du homelab. Passerelle LLM, base vectorielle, reranker, conteneur Claude Code,
agents et connecteurs y vivront dans un seul stack.

## Ce que contient ce dépôt

Un rôle, et le playbook d'exemple qui montre comment l'appeler.

```
playbook.AIS.example.yaml            l'appel du rôle, commenté
roles/deploy_AIS_Docker_stack/       le rôle : le docker-compose du stack et ses variables
```

C'est tout, et c'est délibéré : **le dépôt fournit le stack, pas la mécanique qui le déploie.** Cette
mécanique appartient à l'appelant, et elle existe déjà -- `Docker/deploy_Docker_swarm_stack` et
`Docker/deploy_Docker_compose_stack` du dépôt `Homelab_Ansible_deployment` la portent, chacun pour son
orchestrateur, avec tout ce que leurs commentaires documentent de pannes déjà payées.

## Un rôle paramétrable, pas un rôle spécifique

Le rôle ne présuppose **ni machine, ni domaine, ni compte, ni orchestrateur**. Tout ce qui identifie un
déploiement est une variable fournie par l'appelant : son inventaire, ses FQDN, les labels de son reverse
proxy, son réseau publié, et jusqu'au nom du rôle chargé de déployer le stack.

C'est ce qui permet à deux personnes de déployer le même stack sur deux estates qui n'ont rien en commun,
sans forker. Il n'y a donc dans ce dépôt aucune adresse IP, aucun nom d'hôte et aucun domaine.

## Comment l'appeler

```yaml
- role: deploy_AIS_Docker_stack
  vars:
    AIS_Docker_stack_deployment_role_name: "Docker/deploy_Docker_swarm_stack"
```

Le seul paramètre obligatoire est celui-là : le rôle qui déploie réellement le stack. Le contrat qu'il doit
remplir, la liste complète des variables et les raisons derrière les choix du template sont dans
[`roles/deploy_AIS_Docker_stack/README.md`](roles/deploy_AIS_Docker_stack/README.md).

## Où en est le stack

`services:` est **vide**. Le squelette décrit ce dans quoi on ajoute ; chaque issue de service y ajoutera
son bloc et ses variables. Le fichier se rend et se parse, mais un stack sans service ne démarre rien --
`docker compose config` le refuse, et c'est normal jusqu'à la première issue de service.

Le modèle commenté en tête du template porte les conventions qu'un bloc de service doit tenir : image
épinglée par version, limite mémoire déclarée, `deploy.restart_policy.condition: any`, aucun port publié
pour un service interne, aucun secret en clair. Elles sont écrites là plutôt que dans un document séparé
parce que c'est là qu'on les oublie.

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

Aujourd'hui `services:` est vide, donc les contrôles de convention ne portent sur rien. C'est voulu : ils
sont câblés maintenant pour mordre au premier bloc de service, plutôt qu'écrits après coup, une fois la
convention déjà cassée.

## Licence

Double licence, et les deux arms ne sont pas symétriques :

- **AGPL-3.0-only** pour tout le monde, sans frais et sans formalité. Le texte est dans [`LICENSE`](LICENSE) ;
- ou une **licence commerciale négociée séparément**, pour qui ne peut pas tenir les obligations de l'AGPL.

Le choix est celui du destinataire. Prendre ce travail sous l'AGPL ne demande ni permission, ni
enregistrement, ni notification à quiconque.

> La page décrivant l'arm commercial (`LICENSE-COMMERCIAL.md`), le `NOTICE` et le `CONTRIBUTING.md` qui
> permet à des contributions extérieures d'être offertes sous les deux arms restent à écrire ici. Ils
> existent déjà, sous une forme directement transposable, dans `Dell_iDRAC_fan_controller_Docker` et
> `Homelab_Ansible_deployment`.

Chaque fichier source de ce dépôt porte un en-tête SPDX. Les templates n'en portent pas : ils sont rendus
sur les nœuds gérés, et l'en-tête finirait recopié dans le `docker-compose` déployé.
