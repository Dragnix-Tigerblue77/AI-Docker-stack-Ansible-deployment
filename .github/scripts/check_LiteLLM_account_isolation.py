#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Refuse toute configuration LiteLLM ou le quota d'une personne peut payer l'appel d'une autre.

POURQUOI CE CONTROLE EXISTE
---------------------------
La passerelle LiteLLM n'a de raison d'etre que si les quotas des deux comptes restent etanches.
Or l'etancheite se perd de trois facons, et une seule se voit a la relecture (#2, specification 4) :

  1. un "fallbacks" qui cite explicitement un modele de l'autre personne -- visible ;
  2. deux entrees de meme "model_name" portant des "api_key" differentes : le Router les traite
     comme deux deploiements d'un meme groupe et repartit la charge entre elles -- invisible, aucune
     ligne "fallbacks" n'a ete ecrite ;
  3. le cooldown automatique : a l'interieur d'un groupe, un deploiement qui prend un 429 est mis
     de cote et le trafic part vers les autres deploiements DU MEME GROUPE. Si le groupe contient
     les deux comptes, les deux personnes se relaient des que l'une est epuisee. C'est le
     comportement par defaut, il ne demande aucune configuration pour se produire, et c'est
     exactement ce qu'un fournisseur appelle un contournement de quota.

Le point 3 est le motif reel de ce fichier. Rien d'autre dans cette CI ne peut le voir : la
configuration fautive est un YAML parfaitement valide, que yamllint et ansible-lint acceptent tous
les deux sans une remarque. Le jour ou les 429 deviendront penibles, quelqu'un ajoutera un repli de
bonne foi, et l'isolation disparaitra sans qu'aucun test n'echoue.

CE QUI FAIT FOI POUR L'IDENTITE D'UN COMPTE
-------------------------------------------
Le nom de la variable d'environnement de la cle, et lui seul : "api_key: os.environ/GROQ_API_KEY_DRAGNIX"
appartient au compte "DRAGNIX". C'est la cle qui depense le quota ; le suffixe du "model_name" et
"model_info.access_groups" ne sont que des etiquettes, et une etiquette peut mentir.

Ce script ne connait aucune liste de personnes : le compte est le segment qui suit "_API_KEY_" dans
le nom de la variable, quel qu'il soit. Un troisieme compte, ou le projet facture "SCI" de #2,
fonctionnent sans qu'une ligne d'ici ne change. Une entree dont la cle ne permet PAS de conclure
(valeur litterale, variable Jinja, nom de variable hors convention) n'est pas ignoree en silence :
elle est signalee, parce qu'une entree que le controle ne sait pas rattacher est exactement une
entree sur laquelle il ne protege rien.

POURQUOI ON ANALYSE LE YAML, ET PLUS LIGNE A LIGNE
---------------------------------------------------
La premiere version de ce fichier lisait des lignes avec des expressions regulieres, pour n'avoir
aucune dependance. Elle a ete remplacee apres mesure : le meme repli inter-comptes ecrit en style
BLOC plutot qu'en style FLOT n'etait pas vu.

    router_settings:                     router_settings:
      fallbacks:                           fallbacks:
        - a: ["b"]          <- vu            - a:             <- PAS vu
                                                 - b

Les deux formes produisent le meme objet, "yamllint" les accepte toutes les deux, et la seconde est
celle que produit tout serialiseur YAML -- donc le filtre "to_nice_yaml" d'Ansible, donc le style
majoritaire du depot. Un garde-fou qui depend du style d'ecriture de ce qu'il surveille n'en est pas
un. Le prix paye est une dependance a PyYAML et une etape "pip install" dans le job ; c'est le bon
cote du compromis, et il est assume ici plutot que decouvert le jour d'un incident de quota.

Le fichier vise est un TEMPLATE Jinja rendu par un role Ansible, que "yaml.safe_load" refuserait :
"{{ ... }}" ouvre une accolade que YAML lit comme un debut de dictionnaire. Le Jinja est donc
neutralise avant l'analyse (voir "neutralise_jinja"). Si malgre cela un fichier reste illisible, il
est SIGNALE et non saute : un fichier qu'on n'a pas su lire n'est pas un fichier conforme.

CE QU'IL NE FAIT PAS, DELIBEREMENT
----------------------------------
* Il ne lit pas l'etat reel de la passerelle. Une cle virtuelle creee a la main dans "/ui" lui est
  invisible : c'est le test negatif executable de #2 qui couvre cela, pas un controle de fichier.
* Il ne voit pas un repli passe dans le CORPS d'une requete ("extra_body={'fallbacks': [...]}").
  Aucun controle de fichier ne le peut. La parade est "disable_fallbacks" sur les cles virtuelles.
* Il ne voit plus ce qui est en COMMENTAIRE, puisqu'un analyseur YAML les jette. C'est un changement
  par rapport a la version ligne a ligne, et c'est le bon sens : un repli commente n'est pas actif,
  et l'ancienne version accusait une entree correcte a cause d'une cle revoquee gardee en trace.
* Il ne rend pas un verdict sur un fichier qu'il n'a pas trouve. Tant que #2 n'a pas atterri, il
  n'y a rien a lire, et il le dit plutot que de rendre un vert qui ne veut rien dire.
"""

import argparse
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "PyYAML est requis par ce controle (voir requirements.txt) : pip install -r requirements.txt\n"
    )
    raise SystemExit(2)

# Les quatre cles de repli de LiteLLM. "fallbacks" seul ne suffit pas : les trois autres produisent
# le meme effet par un autre chemin, et se declarent aussi bien sous "router_settings" que sous
# "litellm_settings".
FALLBACK_KEYS = (
    "fallbacks",
    "default_fallbacks",
    "context_window_fallbacks",
    "content_policy_fallbacks",
)
SETTINGS_SECTIONS = ("router_settings", "litellm_settings")

# "os.environ/GROQ_API_KEY_DRAGNIX" -> compte "DRAGNIX".
ENVIRONMENT_REFERENCE = re.compile(r"^os\.environ/(?P<variable>[A-Za-z0-9_]+)$")
ACCOUNT_FROM_VARIABLE = re.compile(r"_API_KEY_(?P<account>[A-Za-z0-9_]+)$")

JINJA_EXPRESSION = re.compile(r"\{\{.*?\}\}", re.DOTALL)
JINJA_STATEMENT = re.compile(r"\{%.*?%\}", re.DOTALL)
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)

# Un fichier candidat est un YAML, rendu ou non par Jinja. Le NOM ne sert pas a le reconnaitre :
# LiteLLM appelle sa configuration "config.yaml", et un controle qui exige "litellm" dans le nom
# annoncerait tranquillement « aucune configuration trouvee » sur un depot qui en a une.
CANDIDATE_SUFFIXES = (".yml", ".yaml", ".yml.j2", ".yaml.j2")
SKIPPED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "__pycache__", ".ansible"}

SELFTEST_DIRECTORY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tests", "LiteLLM_account_isolation"
)


def neutralise_jinja(text):
    """Rend un template Jinja analysable par un lecteur YAML.

    Les expressions deviennent un scalaire ordinaire, les instructions et commentaires
    disparaissent. Ce n'est pas un rendu : une boucle "{% for %}" ne produit pas ses elements, donc
    ce qui est analyse est le SQUELETTE statique du fichier. C'est suffisant ici -- une entree de
    "model_list" engendree par une boucle serait de toute facon indecidable a la lecture -- et c'est
    dit plutot que suppose.
    """
    text = JINJA_COMMENT.sub("", text)
    text = JINJA_STATEMENT.sub("", text)
    text = JINJA_EXPRESSION.sub("JINJA", text)
    lines = [line for line in text.splitlines() if line.strip() != ""]
    return "\n".join(lines)


def account_of_reference(value):
    """Le compte proprietaire d'une "api_key", et pourquoi quand on ne peut pas conclure."""
    if not isinstance(value, str):
        return None, "la valeur n'est pas une chaine"
    reference = ENVIRONMENT_REFERENCE.match(value.strip())
    if not reference:
        if "JINJA" in value:
            return None, "la cle vient d'une variable Jinja, illisible ici"
        return None, "la cle n'est pas lue par \"os.environ/...\""
    account = ACCOUNT_FROM_VARIABLE.search(reference.group("variable"))
    if not account:
        return None, (
            "le nom \"%s\" ne suit pas la convention \"<FOURNISSEUR>_API_KEY_<COMPTE>\" de #2"
            % reference.group("variable")
        )
    return account.group("account"), None


def normalise_fallbacks(section):
    """Toutes les correspondances de repli d'une section, quelle que soit leur ecriture.

    Renvoie des (cle, source, [cibles]). La source vaut None pour "default_fallbacks", qui n'en a
    pas : sa liste s'applique a TOUS les groupes a la fois.

    C'est ici que se paie l'analyse YAML : le style bloc, le style flot et le style flot eclate sur
    plusieurs lignes arrivent tous les trois sous la meme forme, et il n'y a plus qu'un cas a
    traiter au lieu de trois a rater.
    """
    found = []
    if not isinstance(section, dict):
        return found
    for key in FALLBACK_KEYS:
        if key not in section:
            continue
        value = section[key]
        if key == "default_fallbacks":
            targets = value if isinstance(value, list) else [value]
            found.append((key, None, [t for t in targets if isinstance(t, str)]))
            continue
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for source, targets in entry.items():
                if not isinstance(targets, list):
                    targets = [targets]
                found.append((key, source, [t for t in targets if isinstance(t, str)]))
    return found


def read_entries(document):
    """Les entrees de "model_list", sous une forme utilisable."""
    entries = []
    model_list = document.get("model_list") if isinstance(document, dict) else None
    if not isinstance(model_list, list):
        return entries
    for entry in model_list:
        if not isinstance(entry, dict):
            continue
        parameters = entry.get("litellm_params") or {}
        information = entry.get("model_info") or {}
        groups = information.get("access_groups") if isinstance(information, dict) else None
        entries.append({
            "model_name": entry.get("model_name"),
            "api_key": parameters.get("api_key") if isinstance(parameters, dict) else None,
            "access_groups": [g for g in (groups or []) if isinstance(g, str)],
        })
    return entries


def check_document(path, document):
    """Les manquements d'une configuration deja analysee."""
    problems = []
    entries = read_entries(document)
    if not entries:
        return problems

    accounts_seen = set()
    for entry in entries:
        account, _ = account_of_reference(entry["api_key"])
        if account:
            accounts_seen.add(account)

    # Regle 1 -- un "model_name" ne regroupe jamais deux comptes.
    # C'est celle qui ferme le cooldown automatique, donc la plus importante des quatre.
    by_name = {}
    for entry in entries:
        if isinstance(entry["model_name"], str):
            by_name.setdefault(entry["model_name"], []).append(entry)

    account_of_model = {}
    for name, group in sorted(by_name.items()):
        accounts = sorted({
            account for account, _ in
            (account_of_reference(entry["api_key"]) for entry in group) if account
        })
        if len(accounts) == 1:
            account_of_model[name] = accounts[0]
        elif len(accounts) > 1:
            problems.append(
                "%s: le model_name \"%s\" regroupe des deploiements de plusieurs comptes (%s).\n"
                "    Le Router les traite comme un seul groupe : il repartit la charge entre eux, et\n"
                "    met automatiquement en cooldown celui qui prend un 429 pour router vers l'autre.\n"
                "    Les deux personnes se relaient donc des que l'une est epuisee, sans qu'aucune\n"
                "    ligne \"fallbacks\" n'ait ete ecrite. Donner un model_name distinct a chaque compte."
                % (path, name, ", ".join(accounts))
            )

    # Regle 2 -- une entree que le controle ne sait pas rattacher est signalee, pas ignoree.
    for entry in entries:
        account, reason = account_of_reference(entry["api_key"])
        if account:
            continue
        problems.append(
            "%s: l'entree \"%s\" n'a pas de compte identifiable : %s.\n"
            "    Aucune des regles d'isolation ne peut s'appliquer a elle. Ecrire la cle sous la forme\n"
            "    \"api_key: os.environ/<FOURNISSEUR>_API_KEY_<COMPTE>\", comme le prescrit #2."
            % (path, entry["model_name"], reason)
        )

    # Regle 3 -- l'etiquette doit dire la meme chose que la cle.
    # Une entree mal etiquetee n'est pas une faute de frappe : c'est ce qui rend la regle 4
    # illisible, puisqu'un relecteur juge un repli sur le nom qu'il voit.
    for entry in entries:
        account, _ = account_of_reference(entry["api_key"])
        if not account or not isinstance(entry["model_name"], str):
            continue
        suffix = entry["model_name"].rsplit("-", 1)[-1].upper()
        if suffix != account and suffix in accounts_seen:
            problems.append(
                "%s: le model_name \"%s\" annonce le compte \"%s\" mais sa cle appartient a \"%s\".\n"
                "    L'etiquette ment : un relecteur qui juge un repli sur le nom qu'il lit se trompera."
                % (path, entry["model_name"], suffix, account)
            )
        for group in entry["access_groups"]:
            if group.upper() != account and group.upper() in accounts_seen:
                problems.append(
                    "%s: \"%s\" est dans l'access_group \"%s\" mais sa cle appartient a \"%s\".\n"
                    "    La liste blanche d'une equipe donnerait acces a la cle de l'autre."
                    % (path, entry["model_name"], group, account)
                )

    # Regle 4 -- les replis.
    for section_name in SETTINGS_SECTIONS:
        section = document.get(section_name) if isinstance(document, dict) else None
        for key, source, targets in normalise_fallbacks(section):
            if source is None:
                problems.append(
                    "%s: \"%s.%s\" s'applique a TOUS les groupes de modeles a la fois, donc aussi a\n"
                    "    ceux de l'autre compte : il traverse toutes les frontieres d'un coup. Ecrire les\n"
                    "    replis un par un sous \"fallbacks\", ou ne pas en mettre."
                    % (path, section_name, key)
                )
                continue
            source_account = account_of_model.get(source)
            if source_account is None:
                continue
            for target in targets:
                target_account = account_of_model.get(target)
                if target_account is not None and target_account != source_account:
                    problems.append(
                        "%s: \"%s.%s\" fait replier \"%s\" (compte %s) sur \"%s\" (compte %s).\n"
                        "    Un appel legitime de l'un consommerait le quota de l'autre. Un repli reste a\n"
                        "    l'interieur des cles d'UNE SEULE personne."
                        % (path, section_name, key, source, source_account, target, target_account)
                    )
    return problems


def load(path):
    """(document, erreur). L'un des deux est None."""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        return None, "illisible (%s)" % error.__class__.__name__
    try:
        return yaml.safe_load(neutralise_jinja(raw)), None
    except yaml.YAMLError as error:
        return None, "YAML invalide meme apres neutralisation du Jinja (%s)" % (
            str(error).splitlines()[0] if str(error) else error.__class__.__name__
        )


def check_file(path):
    """Les manquements d'un fichier. Un fichier illisible EST un manquement."""
    document, error = load(path)
    if error:
        if not is_litellm_configuration_by_text(path):
            return []
        return [
            "%s: %s.\n"
            "    Un fichier que le controle ne sait pas lire n'est pas un fichier conforme : tant qu'il\n"
            "    n'est pas analysable, l'isolation des comptes n'y est verifiee par personne."
            % (path, error)
        ]
    return check_document(path, document)


def is_litellm_configuration_by_text(path):
    """Dernier recours quand l'analyse echoue : le fichier PARLE-t-il de model_list ?"""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return "model_list" in handle.read()
    except OSError:
        return False


def configuration_files(root):
    """Les fichiers qui declarent une "model_list", reconnus par leur CONTENU."""
    paths = []
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in SKIPPED_DIRECTORIES]
        if os.path.abspath(directory).startswith(SELFTEST_DIRECTORY):
            continue
        for name in sorted(files):
            if not name.endswith(CANDIDATE_SUFFIXES):
                continue
            path = os.path.join(directory, name)
            document, error = load(path)
            if error:
                if is_litellm_configuration_by_text(path):
                    paths.append(path)
                continue
            if isinstance(document, dict) and "model_list" in document:
                paths.append(path)
    return sorted(paths)


def run_selftest():
    """Prouve que le controle attrape ce qu'il pretend attraper.

    La Definition of Done de #32 demande que le controle « echoue sur une configuration
    deliberement fautive -- teste, pas suppose ». C'est ce que fait cette fonction, et c'est
    aussi ce qui donne au fichier une valeur AUJOURD'HUI, avant que #2 n'ait produit la moindre
    configuration reelle a lire.

    Chaque fixture annonce en premiere ligne le nombre de manquements attendus ET un fragment que
    le premier d'entre eux doit contenir. Comparer un NOMBRE seul ne suffisait pas : la moitie de
    la surface surveillee pouvait disparaitre sans que le compte ne bouge.
    """
    if not os.path.isdir(SELFTEST_DIRECTORY):
        print("selftest: repertoire de fixtures introuvable : %s" % SELFTEST_DIRECTORY)
        return 1

    failures = 0
    names = sorted(name for name in os.listdir(SELFTEST_DIRECTORY)
                   if os.path.isfile(os.path.join(SELFTEST_DIRECTORY, name)))
    if not names:
        print("selftest: aucune fixture")
        return 1

    for name in names:
        path = os.path.join(SELFTEST_DIRECTORY, name)
        with open(path, encoding="utf-8") as handle:
            first_line = handle.readline()
        expected = re.search(r"ATTENDU\s*:\s*(\d+)", first_line)
        fragment = re.search(r"CONTIENT\s*:\s*(.+?)\s*(?:--|$)", first_line)
        if not expected:
            print("selftest: %s n'annonce pas son nombre de manquements attendus" % name)
            failures += 1
            continue
        problems = check_file(path)
        count = int(expected.group(1))
        if len(problems) != count:
            failures += 1
            print("selftest: %s -> %d manquement(s), %d attendu(s)" % (name, len(problems), count))
            for problem in problems:
                print("    " + problem.splitlines()[0])
            continue
        if count and fragment:
            wanted = fragment.group(1)
            if not any(wanted in problem for problem in problems):
                failures += 1
                print("selftest: %s -> le bon NOMBRE de manquements, mais aucun ne contient \"%s\""
                      % (name, wanted))
                for problem in problems:
                    print("    " + problem.splitlines()[0])
                continue
        print("selftest: %s -> %d manquement(s), conforme" % (name, len(problems)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="verifie le controle contre ses fixtures au lieu de lire le depot",
    )
    parser.add_argument("--root", default=".", help="racine du depot a parcourir")
    arguments = parser.parse_args()

    if arguments.selftest:
        return run_selftest()

    paths = configuration_files(arguments.root)
    if not paths:
        # Vert, mais bavard : personne ne doit croire que ce controle a valide quoi que ce soit.
        print(
            "Aucune configuration LiteLLM trouvee : #2 ne l'a pas encore produite, il n'y a rien a\n"
            "lire. Ce controle deviendra effectif sans qu'on y touche le jour ou le fichier existera,\n"
            "quel que soit son nom -- il est reconnu a sa \"model_list\", pas a son nom de fichier.\n"
            "Sa capacite a detecter une faute est verifiee des maintenant par \"--selftest\"."
        )
        return 0

    problems = []
    for path in paths:
        problems.extend(check_file(path))

    if problems:
        print("Isolation des comptes LiteLLM : %d manquement(s).\n" % len(problems))
        for problem in problems:
            print(problem + "\n")
        return 1

    print("Isolation des comptes LiteLLM : %d fichier(s) lu(s), aucun manquement." % len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
