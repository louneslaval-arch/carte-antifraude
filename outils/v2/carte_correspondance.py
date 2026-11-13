#!/usr/bin/env python3
"""Carte de correspondance entre la structure de la v2 de Kamal et notre base (`docs/correspondance_v2.md`).

La partie générée, entre les repères DEBUT et FIN, vient des fichiers de Kamal lus par programme : modèles et
colonnes → miroir c0 (repris à l'identique), énumérations (avec les écarts entre schema.prisma et les types),
types d'échange, vocabulaire amont → moteur (README § 4) et tables enfants proposées (README § 7). Le reste du
document est écrit à la main (nos ajouts, chacun justifié) et conservé d'une génération à l'autre.

Usage :
    carte_correspondance.py --ecrire   [--structure DOSSIER] [--doc FICHIER]
    carte_correspondance.py --verifier [--structure DOSSIER] [--doc FICHIER]   (code 1 si la carte est périmée)
"""
import argparse
import hashlib
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import lire_prisma  # noqa: E402
import lire_types_ts  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(ICI))
STRUCTURE_DEFAUT = os.path.join(RACINE, 'import', 'kamal_structure')
DOC_DEFAUT = os.path.join(RACINE, 'docs', 'correspondance_v2.md')
DEBUT = '<!-- DEBUT PARTIE GENEREE : outils/v2/carte_correspondance.py --ecrire ; ne pas modifier à la main -->'
FIN = '<!-- FIN PARTIE GENEREE -->'
SOURCES = ('schema/schema.prisma', 'types/web_types.ts', 'types/engine-core_types.ts', 'README.md')

ENTETE_MAIN = """# Correspondance entre la v2 de Kamal et la base de la carte

Source de vérité : les fichiers de Kamal (`reference/v2/`, sinon `import/kamal_structure/`). La partie générée
ci-dessous se refait par `outils/v2/carte_correspondance.py --ecrire` ; un test échoue tant qu'elle ne correspond
pas aux fichiers de Kamal (dérive).

## Nos ajouts (écrits à la main, chacun justifié)

| Nom | Où | Pourquoi la v2 ne l'a pas |
| --- | --- | --- |
| `schema_version` | toutes couches | numéro des migrations appliquées (`schema/000_schema_version.sql`) ; propre à notre base |

"""


def _lire(structure, chemin):
    with open(os.path.join(structure, chemin), encoding='utf-8') as f:
        return f.read()


def _section(readme, numero):
    m = re.search(rf'^## {numero}\..*?$(.*?)(?=^## |\Z)', readme, re.M | re.S)
    return m.group(1) if m else ''


def vocabulaire_amont_moteur(readme):
    """Paires (clés amont, clé moteur, précision) de la table de correspondance du README § 4."""
    ligne = next((l for l in _section(readme, 4).splitlines() if 'correspondance amont' in l), '')
    ligne = re.split(r'correspondance amont\s*→\s*moteur\s*:', ligne, maxsplit=1)[-1]
    paires = []
    for m in re.finditer(r'`([^`]+?)→([^`]+?)`(?:\s*\(([^)]*)\))?', ligne):
        amont = [x.strip() for x in re.split(r'[|]', m.group(1)) if x.strip()]
        paires.append((amont, m.group(2).strip(), (m.group(3) or '').strip()))
    return paires


def tables_enfants(readme):
    """Noms de tables enfants proposés au README § 7 (entre accents graves, en minuscules à tirets bas)."""
    return list(dict.fromkeys(re.findall(r'`([a-z]+_[a-z_]+)`', _section(readme, 7))))


def _type_colonne(c):
    t = c.type + ('[]' if c.liste else '')
    return t + (f' (@db.{c.type_natif})' if c.type_natif else '')


def generer(structure):
    schema = lire_prisma.lire(_lire(structure, SOURCES[0]))
    web = lire_types_ts.lire(_lire(structure, SOURCES[1]))
    moteur = lire_types_ts.lire(_lire(structure, SOURCES[2]))
    readme = _lire(structure, SOURCES[3])

    l = [DEBUT, '', '## Sources lues', '', '| Fichier | sha256 |', '| --- | --- |']
    for s in SOURCES:
        with open(os.path.join(structure, s), 'rb') as f:
            l.append(f'| `{s}` | `{hashlib.sha256(f.read()).hexdigest()}` |')

    n_champs = sum(len(m.champs) for m in schema.modeles.values())
    l += ['', '## Modèles de schema.prisma → miroir c0 (repris à l\'identique)', '',
          f'Couverture : {len(schema.modeles)} modèles, {n_champs} champs, {len(schema.enums)} énumérations de '
          'schema.prisma ; 100 % repris dans le miroir c0 (étape D), noms de tables et de colonnes tels que '
          'PostgreSQL les voit.', '',
          '| Table | Champ | Colonne | Type | Facultatif | Clé, unicité | Destination |',
          '| --- | --- | --- | --- | --- | --- | --- |']
    for m in schema.modeles.values():
        for c in m.champs:
            if c.relation:
                cle, dest, colonne, type_ = '', 'relation, pas de colonne (jointure par la clé étrangère)', '—', c.type
            else:
                drapeaux = [x for x, ok in (('clé', c.nom in m.cle_primaire), ('unique', c.unique)) if ok]
                cle = ', '.join(drapeaux)
                dest = 'miroir c0, repris'
                colonne, type_ = f'`{c.colonne}`', _type_colonne(c)
            l.append(f'| `{m.table}` | `{c.nom}` | {colonne} | {type_} | {"oui" if c.facultatif else "non"} | '
                     f'{cle} | {dest} |')
        for u in m.uniques:
            l.append(f'| `{m.table}` | unicité ({", ".join(u)}) | | | | unique | miroir c0, repris |')

    l += ['', '## Énumérations', '', 'Valeurs reprises telles quelles, sans traduction ni changement de casse '
          '(texte contrôlé dans le miroir).', '', '| Énumération | Source | Valeurs | Remarque |',
          '| --- | --- | --- | --- |']
    types_enums = {}
    for origine, t in (('web_types.ts', web), ('engine-core_types.ts', moteur)):
        for nom, valeurs in t.enumerations.items():
            types_enums.setdefault(nom, []).append((origine, valeurs))
    for nom, e in schema.enums.items():
        valeurs = [v.nom for v in e.valeurs]
        remarque = []
        for origine, autres in types_enums.get(nom, []):
            if autres != valeurs:
                remarque.append(f'écart avec {origine} : {", ".join(autres)}')
        l.append(f'| `{nom}` | schema.prisma | {", ".join(valeurs)} | {"; ".join(remarque)} |')
    for nom, liste in types_enums.items():
        if nom in schema.enums:
            continue
        for origine, valeurs in liste:
            l.append(f'| `{nom}` | {origine} | {", ".join(valeurs)} | absente de schema.prisma (texte libre en base) |')

    l += ['', '## Types d\'échange → modèles d\'échange, générateur et collecteur', '',
          '| Interface | Source | Champs | Destination |', '| --- | --- | --- | --- |']
    for origine, t in (('web_types.ts', web), ('engine-core_types.ts', moteur)):
        for nom in t.interfaces:
            champs = [c.nom for c in t.champs_complets(nom)]
            l.append(f'| `{nom}` | {origine} | {len(champs)} | modèle d\'échange (pydantic), générateur et serveur '
                     'v2 fictifs (étape C), collecteur (étape D) |')
        for nom in t.alias:
            l.append(f'| `{nom}` | {origine} | — | alias repris tel quel dans les modèles d\'échange |')

    l += ['', '## Vocabulaire amont → moteur (README § 4) → `ref_cle_canonique`', '',
          'La clé canonique d\'un fait est la clé moteur (colonne de droite).', '',
          '| Clés amont | Clé moteur | Précision |', '| --- | --- | --- |']
    for amont, cle, precision in vocabulaire_amont_moteur(readme):
        l.append(f'| {", ".join(f"`{a}`" for a in amont)} | `{cle}` | {precision} |')

    l += ['', '## Tables enfants proposées (README § 7) → c1 (étape E)', '', '| Table | Destination |',
          '| --- | --- |']
    for t in tables_enfants(readme):
        l.append(f'| `{t}` | c1, nom et clés repris |')
    l += ['', FIN]
    return '\n'.join(l) + '\n'


def _composer(existant, genere):
    if existant and DEBUT in existant and FIN in existant:
        avant = existant[:existant.index(DEBUT)]
        apres = existant[existant.index(FIN) + len(FIN):].lstrip('\n')
        return avant + genere + ('\n' + apres if apres else '')
    return (existant or ENTETE_MAIN) + genere


def ecrire(structure, doc):
    existant = open(doc, encoding='utf-8').read() if os.path.exists(doc) else ''
    with open(doc, 'w', encoding='utf-8') as f:
        f.write(_composer(existant, generer(structure)))


def a_jour(structure, doc):
    if not os.path.exists(doc):
        return False
    existant = open(doc, encoding='utf-8').read()
    return _composer(existant, generer(structure)) == existant


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--ecrire', action='store_true')
    mode.add_argument('--verifier', action='store_true')
    p.add_argument('--structure', default=STRUCTURE_DEFAUT)
    p.add_argument('--doc', default=DOC_DEFAUT)
    a = p.parse_args(argv)
    if a.ecrire:
        ecrire(a.structure, a.doc)
        print('carte de correspondance écrite')
        return 0
    ok = a_jour(a.structure, a.doc)
    print('carte de correspondance à jour' if ok else 'carte de correspondance périmée', file=sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
