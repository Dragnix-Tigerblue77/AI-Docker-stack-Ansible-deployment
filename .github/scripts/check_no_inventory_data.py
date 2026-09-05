#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Tigerblue77
# SPDX-License-Identifier: AGPL-3.0-only

"""Refuse une adresse IP ou un nom de domaine ecrit en dur dans le depot.

POURQUOI CE CONTROLE EXISTE
---------------------------
Le role de ce depot est parametrable : c'est l'appelant qui fournit l'inventaire, les FQDN, les
etiquettes Traefik et le reseau (#22, #31, #33). Une adresse ou un nom d'hote ecrit ici n'est donc
pas seulement une fuite d'information sur le homelab -- c'est une regression fonctionnelle, puisque
le role cesse d'etre reutilisable par quelqu'un d'autre. Rien d'autre dans cette CI ne peut le
voir : un FQDN en dur est du YAML valide, et yamllint comme ansible-lint le laissent passer.

POURQUOI UNE LISTE BLANCHE, ET NON UNE LISTE NOIRE
--------------------------------------------------
C'est la seule forme possible. Une liste noire devrait enumerer les domaines interdits -- donc
ECRIRE le domaine du homelab dans un fichier versionne, ce qui est exactement ce que la regle
interdit. Le controle est donc a l'envers : tout ce qui ressemble a un hote est refuse, sauf les
quelques hotes amont que le depot doit citer pour fonctionner, chacun avec sa raison ci-dessous.

Le corollaire est assume : la liste blanche grandira. C'est voulu. Ajouter un hote amont est un
geste d'une ligne, qui laisse une trace dans un diff et demande sa justification ; c'est
precisement le controle qu'on cherche a avoir sur cette categorie de valeur.

CE QU'IL NE FAIT PAS
--------------------
* Il ne voit pas un nom d'hote SANS point ("chsonvdsw01"), que #22 nomme pourtant en premier.
  Aucune regle mecanique ne distingue un tel nom d'un mot ordinaire ; c'est une relecture humaine.
* Il ne lit pas les issues. gitleaks non plus, et le secret scanning de GitHub demanderait un plan
  que l'organisation n'a pas. Le contenu des issues reste une vigilance humaine.

COMMENT UN NOM EST RECONNU
--------------------------
Un jeton "label.label[.label]" dont le DERNIER label figure dans TOP_LEVEL_DOMAINS. Cette liste est
volontairement courte et ne cherche pas a etre exhaustive : elle evite les extensions de fichier
qui sont aussi des domaines de premier niveau et qui feraient hurler le controle sur tout le depot
-- ".sh" (Sainte-Helene), ".py" (Paraguay), ".md" (Moldavie), ".io" pour un fichier, ".pl", ".so".
Un domaine en ".sh" passerait donc au travers ; c'est le prix a payer pour que le controle ne crie
pas sur "functions.sh", et c'est le bon cote du compromis pour un depot qui n'en aura pas.
"""

import os
import re
import sys

# Les hotes amont que ce depot a le droit de nommer. Chaque entree porte sa raison : sans elle,
# la liste devient un fourre-tout et le controle ne veut plus rien dire.
ALLOWED_HOSTS = {
    "github.com": "telechargement des releases et des actions",
    "raw.githubusercontent.com": "contenu brut d'un depot public",
    "api.github.com": "API GitHub",
    "objects.githubusercontent.com": "redirection de telechargement des releases",
    "docs.github.com": "documentation citee en commentaire",
    "pypi.org": "installation des outils de requirements.txt",
    "files.pythonhosted.org": "artefacts servis par PyPI",
    "galaxy.ansible.com": "collections Ansible",
    "ghcr.io": "registre d'images",
    "docker.io": "registre d'images",
    "hub.docker.com": "registre d'images",
    "quay.io": "registre d'images",
    "docs.litellm.ai": "documentation de la passerelle, citee en commentaire",
    "ai.google.dev": "conditions d'utilisation Gemini, citees dans #2",
    "fsf.org": "texte de la licence",
    "www.gnu.org": "texte de la licence",
    "spdx.org": "identifiants de licence",
    "reuse.software": "specification des en-tetes de licence",
}

# Les adresses qui ne designent aucune machine et qu'un fichier de configuration doit pouvoir
# ecrire : elles ne disent rien du homelab.
ALLOWED_ADDRESSES = {
    "0.0.0.0": "ecouter sur toutes les interfaces",
    "127.0.0.1": "boucle locale",
    "255.255.255.255": "diffusion",
    "::1": "boucle locale IPv6",
}

# Volontairement courte : voir la docstring. Toute extension de fichier utilisee dans ce depot en
# est tenue a l'ecart, meme quand elle est un vrai domaine de premier niveau.
TOP_LEVEL_DOMAINS = {
    # Generiques
    "com", "net", "org", "io", "dev", "ai", "cloud", "info", "tech", "xyz", "tv", "cc",
    # Pays et regions plausibles pour ce foyer et ses fournisseurs
    "fr", "eu", "be", "ch", "de", "uk", "nl", "es", "it", "nf", "re", "pm", "yt", "ovh",
    "co", "me",
    # Pseudo-domaines de reseau local : ce sont EUX qu'un homelab ecrit par accident
    "lan", "local", "home", "internal", "intranet", "box", "arpa",
}

# Les domaines de premier niveau qui sont aussi des MOTS ordinaires -- "email", "services",
# "tools", "network", "systems", "digital", "zone", "host", "site", "space", "link", "live",
# "app", "online", "website" -- sont deliberement absents. Mesure : les inclure fait refuser
# "git config user.email" dans un workflow de ce depot, et la meme collision se produirait sur
# n'importe quel identifiant pointe. Ce sont aussi les TLD les moins plausibles pour le domaine
# d'un foyer : on perd donc peu de couverture et on gagne beaucoup de precision.

# Les chemins que le controle ne lit pas, avec leur raison.
SKIPPED_PATHS = {
    "LICENSE": "texte amont de l'AGPL, ni ecrit ni modifiable ici",
    ".git": "donnees internes de git",
    # Rien de tout cela n'est versionne, et tout cela existe sur la machine d'un contributeur.
    # Sans ces lignes, la commande que CONTRIBUTING.md demande de lancer part en rouge sur des
    # milliers de fichiers des le premier "python3 -m venv .venv" (mesure : 1457 manquements).
    ".venv": "environnement virtuel local, non versionne",
    "venv": "environnement virtuel local, non versionne",
    "node_modules": "dependances locales, non versionnees",
    "__pycache__": "cache Python",
    ".ansible": "cache d'ansible-lint",
    ".mypy_cache": "cache local",
    ".pytest_cache": "cache local",
}

# Une region que le controle saute, delimitee dans le fichier lui-meme. Elle existe pour UN cas :
# un bloc dont le contenu EST un contre-exemple, comme les cas de verification plus bas -- ce
# fichier se lit lui-meme, et sans cela il refuserait ses propres cas de test.
#
# ! C'est une exemption bornee, pas un fichier exclu. La difference est le fond du sujet : sauter le
#   fichier entier ferait de lui le seul endroit du depot ou une vraie adresse passerait inapercue,
#   et ce serait le fichier du controle. Une region delimitee, elle, se voit dans un diff, et le
#   compte des regions traversees est imprime a chaque execution pour qu'elles ne se multiplient
#   pas en silence.
#
# Les deux marqueurs sont assembles en deux morceaux, et ce n'est pas une coquetterie : ecrits d'une
# piece, ils ouvriraient une region sur leur propre ligne de definition -- le controle sauterait
# alors les deux lignes qui le configurent, sans que rien ne le dise. Mesure.
IGNORE_START = "CONTROLE-" + "IgnoreStart"
IGNORE_END = "CONTROLE-" + "IgnoreEnd"

# Un jeton qui ressemble a un nom d'hote. Le dernier label est filtre ensuite contre
# TOP_LEVEL_DOMAINS ; la regex seule ne distingue pas un nom de fichier d'un nom d'hote.
#
# ! Ne pas ecrire de domaine d'exemple dans ce fichier, meme en commentaire : le controle se
#   lit lui-meme et le refuserait, ce qui est le comportement voulu (mesure).
HOSTNAME = re.compile(r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}\b")

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# IPv6 : uniquement les formes qui ne peuvent pas etre autre chose. Exiger un "::" ou huit groupes
# ecarte "20:25:30", qui est une heure, et "12:34:56:78", qui est une adresse MAC tronquee.
IPV6 = re.compile(
    r"(?<![0-9A-Za-z:])(?:"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?"
    r"|::(?:[0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{1,4}"
    r")(?![0-9A-Za-z:])"
)


def is_ipv4(candidate):
    parts = candidate.split(".")
    return len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def is_skipped(relative_path):
    parts = relative_path.split(os.sep)
    return any(part in SKIPPED_PATHS for part in parts)


def is_binary(path):
    try:
        with open(path, "rb") as handle:
            return b"\0" in handle.read(4096)
    except OSError:
        return True


def findings_in_line(line, file_names=frozenset()):
    """Les manquements d'une ligne : (categorie, valeur)."""
    found = []

    for match in IPV4.finditer(line):
        value = match.group(0)
        if is_ipv4(value) and value not in ALLOWED_ADDRESSES:
            found.append(("adresse IPv4", value))

    for match in IPV6.finditer(line):
        value = match.group(0)
        if value not in ALLOWED_ADDRESSES:
            found.append(("adresse IPv6", value))

    for match in HOSTNAME.finditer(line):
        value = match.group(0)
        if is_ipv4(value):
            continue  # deja traite au-dessus, et une IP n'est pas un nom
        if value.rsplit(".", 1)[-1].lower() not in TOP_LEVEL_DOMAINS:
            continue
        if value.lower() in ALLOWED_HOSTS:
            continue
        if value in file_names:
            continue
        found.append(("nom de domaine", value))

    return found


def repository_file_names(root):
    """Les noms de fichiers presents dans l'arbre.

    Ils servent a ne pas confondre un fichier avec un hote : un README en «.org», un logo en
    «.ai», un Dockerfile en «.dev» portent tous un suffixe qui est un vrai domaine de premier
    niveau, et aucun n'est une adresse.

    Le compromis assume est symetrique : un fichier que quelqu'un nommerait comme un domaine
    echapperait au controle. C'est un cas qu'on n'a jamais vu, contre des faux positifs qu'on
    aurait a chaque ajout de fichier.

    ! Les exemples ci-dessus sont ecrits en toutes lettres plutot qu'en "nom.suffixe" parce que ce
      fichier se lit lui-meme : les ecrire normalement les ferait refuser. Encadrer le paragraphe
      d'une region ignoree aurait marche aussi, et aurait ete pire -- une exemption de plus, pour
      un commentaire.
    """
    names = set()
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_PATHS]
        names.update(files)
        names.update(subdirectories)
    return names


def walk(root):
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name not in SKIPPED_PATHS]
        for name in sorted(files):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, root)
            if is_skipped(relative) or is_binary(path):
                continue
            yield path, relative


# Les cas de verification, construits EN MEMOIRE et non dans des fichiers de fixtures.
# La raison est directe : une fixture contenant une adresse devrait etre exclue du parcours pour
# que le controle reste vert, et ce repertoire exclu deviendrait le seul endroit du depot ou une
# vraie fuite passerait inapercue. Un cas en memoire ne cree pas cet angle mort.
# CONTROLE-IgnoreStart
SELFTEST_CASES = (
    # (ligne, nombre de manquements attendus, ce que le cas prouve)
    ("  serveur: 192.168.1.42", 1, "une adresse privee est refusee"),
    ("  bind: 0.0.0.0", 0, "ecouter sur toutes les interfaces reste permis"),
    ("  boucle: 127.0.0.1", 0, "la boucle locale reste permise"),
    ("  hote: 2001:0db8:85a3:0000:0000:8a2e:0370:7334", 1, "une IPv6 complete est refusee"),
    ("  abrege: fe80::1ff:fe23:4567", 1, "une IPv6 abregee est refusee"),
    ("  heure: 20:25:30", 0, "une heure n'est pas une IPv6"),
    ("  version: 8.30.1", 0, "un numero de version n'est pas une adresse"),
    ("  fichier: requirements.txt", 0, "un nom de fichier n'est pas un domaine"),
    ("  script: functions.sh", 0, "une extension qui est aussi un TLD ne compte pas"),
    ("  module: ansible.builtin.assert", 0, "un nom de module n'est pas un domaine"),
    ("  cle: os.environ/GEMINI_API_KEY_DRAGNIX", 0, "une variable n'est pas un domaine"),
    ("  playbook: playbook.AIS.example.yaml", 0, "un nom de playbook n'est pas un domaine"),
    ("  regle: traefik.http.routers.ais.rule", 0, "une etiquette Traefik n'est pas un domaine"),
    ("  url: https://github.com/gitleaks/gitleaks", 0, "un hote amont de la liste blanche passe"),
    ("  fqdn: ais.un-domaine-quelconque.fr", 1, "un FQDN hors liste blanche est refuse"),
    ("  # commente: ais.un-domaine-quelconque.fr", 1, "un commentaire est lu comme le reste"),
)
# CONTROLE-IgnoreEnd


def run_selftest():
    """Prouve que le controle refuse ce qu'il pretend refuser, et accepte le reste.

    Un controle dont personne n'a jamais vu l'echec est un controle que personne ne croit -- et
    celui-ci porte une liste blanche, donc son risque propre est de tout laisser passer en silence.
    """
    failures = 0
    for line, expected, purpose in SELFTEST_CASES:
        found = findings_in_line(line)
        if len(found) != expected:
            failures += 1
            print("selftest: ECHEC (%s) -- %d manquement(s), %d attendu(s) : %s"
                  % (purpose, len(found), expected, line.strip()))
        else:
            print("selftest: ok -- %s" % purpose)
    return 1 if failures else 0


def main():
    arguments = [argument for argument in sys.argv[1:] if argument != "--selftest"]
    if "--selftest" in sys.argv[1:]:
        return run_selftest()
    root = arguments[0] if arguments else "."
    problems = []
    ignored_regions = []
    file_names = repository_file_names(root)

    for path, relative in walk(root):
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
        except OSError as error:
            problems.append((relative, 0, "fichier illisible", error.__class__.__name__))
            continue
        except UnicodeDecodeError:
            # ! Signale, et non saute en silence. Un fichier que ce controle ne sait pas decoder
            #   est un fichier ou une adresse peut se cacher sans que personne ne la voie : c'est
            #   le seul angle mort qu'il ne doit pas s'accorder a lui-meme. Mesure : un fichier
            #   latin-1 contenant une adresse privee passait « aucun manquement », exit 0.
            problems.append((
                relative, 0, "fichier non-UTF-8",
                "non decodable, donc non verifie ; le convertir en UTF-8",
            ))
            continue

        ignoring = False
        opened_at = None
        for number, line in enumerate(lines, start=1):
            if IGNORE_START in line:
                ignoring = True
                opened_at = number
                ignored_regions.append((relative, number))
                continue
            if IGNORE_END in line:
                ignoring = False
                opened_at = None
                continue
            if ignoring:
                continue
            for category, value in findings_in_line(line, file_names):
                problems.append((relative, number, category, value))

        if ignoring:
            # Une region jamais refermee avale tout le reste du fichier. Sans ce controle-ci, la
            # suppression accidentelle d'un marqueur de fin desactive silencieusement la moitie
            # d'un fichier -- et le compte des regions, lui, n'aurait pas bouge.
            problems.append((
                relative, opened_at, "region ignoree jamais refermee",
                "tout le reste du fichier a ete saute ; ajouter le marqueur de fin",
            ))

    if ignored_regions:
        # Imprime sur les DEUX chemins, vert comme rouge : une region ignoree est une exemption, et
        # une exemption qui ne se voit qu'a moitie du temps finit par en couvrir d'autres.
        print("%d region(s) explicitement ignoree(s) :" % len(ignored_regions))
        for relative, number in ignored_regions:
            print("  %s:%d" % (relative, number))
        print("")

    if problems:
        print("Donnees d'inventaire ecrites en dur : %d manquement(s).\n" % len(problems))
        for relative, number, category, value in problems:
            print("%s:%d: %s \"%s\"" % (relative, number, category, value))
        print(
            "\nCes valeurs appartiennent a l'inventaire de l'appelant, pas a ce depot : un role qui\n"
            "les porte cesse d'etre reutilisable, et publie le homelab au passage. Les passer en\n"
            "variable.\n"
            "\n"
            "S'il s'agit d'un hote AMONT que le depot doit legitimement citer, l'ajouter a\n"
            "ALLOWED_HOSTS dans %s AVEC SA RAISON, dans le meme commit."
            % os.path.relpath(os.path.abspath(__file__), os.path.abspath(root))
        )
        return 1

    print("Aucune adresse IP ni nom de domaine en dur.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
