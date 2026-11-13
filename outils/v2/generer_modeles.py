#!/usr/bin/env python3
"""Génère les modèles d'échange pydantic de la v2 (`pipeline/modeles_v2.py`) depuis les types de Kamal.

Source : `web_types.ts` (interfaces échangées entre le back et le front de la v2) et `engine-core_types.ts`
(énumérations importées). Règles de traduction :
- `string` → str ; `number` → int | float (un entier reste un entier) ; `boolean` → bool ; `unknown` → Any ;
- `T | null` → Optional[T], le champ reste obligatoire ; `x?: T` → facultatif ;
- union de chaînes → Literal[...] ; union de chaînes ouverte par `| string` → str ;
- `T[]` → list[T] ; `Record<string, V>` → dict[str, V] ; objet en ligne → modèle imbriqué `Parent_champ` ;
- `extends` → héritage ; signature d'index `[k: string]: V` → clés supplémentaires admises dans ce modèle seul ; nom de champ réservé par Python ou pydantic → nom suffixé de `_`, nom JSON gardé en alias.
Tout autre type est refusé. Les modèles sont stricts (un nombre en texte n'est pas un nombre) et refusent un champ inconnu (`extra='forbid'`) : ils décrivent exactement les
types de Kamal ; le collecteur (étape D) décidera s'il tolère des champs nouveaux.

Usage : generer_modeles.py --ecrire | --verifier  [--types DOSSIER]
"""
import argparse
import hashlib
import keyword
import os
import re
import sys

from pydantic import BaseModel

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
import lire_types_ts  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(ICI))
TYPES_DEFAUT = os.path.join(RACINE, 'import', 'kamal_structure', 'types')
SORTIE = os.path.join(RACINE, 'pipeline', 'modeles_v2.py')


class ErreurModeles(ValueError):
    pass


def _nom_python(nom):
    if keyword.iskeyword(nom) or hasattr(BaseModel, nom):
        return nom + '_'
    return nom


class _Traducteur:
    def __init__(self, web, moteur):
        self.enums = {**moteur.enumerations, **web.enumerations}
        self.interfaces = web.interfaces
        self.imbriques = []  # (nom de classe, champs) à émettre avant leur parent

    def type(self, expr, contexte):
        membres = lire_types_ts._membres_union(expr)
        if len(membres) > 1:
            nullable = 'null' in membres
            autres = [m for m in membres if m not in ('null', 'undefined')]
            chaines = [m for m in autres if lire_types_ts._est_chaine(m)]
            if autres and len(chaines) == len(autres):
                t = 'Literal[' + ', '.join(chaines) + ']'
            elif 'string' in autres and all(m == 'string' or lire_types_ts._est_chaine(m) for m in autres):
                t = 'str'
            else:
                t = ' | '.join(self.type(m, contexte) for m in autres)
            return f'Optional[{t}]' if nullable else t
        m = expr.strip()
        simples = {'string': 'str', 'number': 'int | float', 'boolean': 'bool', 'unknown': 'Any', 'any': 'Any'}
        if m in simples:
            return simples[m]
        if m.endswith('[]'):
            return f'list[{self.type(m[:-2], contexte)}]'
        r = re.fullmatch(r'Record<\s*string\s*,\s*(.+)>', m)
        if r:
            return f'dict[str, {self.type(r.group(1), contexte)}]'
        if m.startswith('{') and m.endswith('}'):
            nom = contexte
            self.imbriques.append((nom, lire_types_ts._champs(m[1:-1])))
            return nom
        if lire_types_ts._est_chaine(m):
            return f'Literal[{m}]'
        if m in self.enums or m in self.interfaces:
            return m
        if re.fullmatch(r'\w+', m):
            raise ErreurModeles(f'type {m} introuvable dans les types de Kamal')
        raise ErreurModeles(f'type non pris en charge : {m}')

    def classe(self, nom, parents, champs):
        lignes = []
        index = [c for c in champs if c.nom == '[index]']
        if index:  # signature d'index `[k: string]: V` : clés libres admises en plus des champs nommés
            lignes.append("    model_config = ConfigDict(extra='allow', populate_by_name=True, strict=True)")
        for c in champs:
            if c.nom == '[index]':
                continue
            t = self.type(c.type, f'{nom}_{c.nom}')
            py = _nom_python(c.nom)
            alias = f"Field(alias='{c.nom}')" if py != c.nom else None
            if c.facultatif:
                t = t if t.startswith('Optional[') else f'Optional[{t}]'
                defaut = f"Field(default=None, alias='{c.nom}')" if alias else 'None'
                lignes.append(f'    {py}: {t} = {defaut}')
            else:
                lignes.append(f'    {py}: {t}' + (f' = {alias}' if alias else ''))
        base = ', '.join(parents) or '_Modele'
        return [f'class {nom}({base}):'] + (lignes or ['    pass']) + ['', '']


def _ordre_par_heritage(interfaces):
    vus, ordre = set(), []

    def visiter(nom):
        if nom in vus or nom not in interfaces:
            return
        vus.add(nom)
        for p in interfaces[nom].parents:
            visiter(p)
        ordre.append(nom)
    for nom in interfaces:
        visiter(nom)
    return ordre


def generer(texte_web, texte_moteur):
    web = lire_types_ts.lire(texte_web)
    moteur = lire_types_ts.lire(texte_moteur)
    tr = _Traducteur(web, moteur)
    empreinte = hashlib.sha256((texte_web + '\0' + texte_moteur).encode('utf-8')).hexdigest()
    sortie = [
        '"""Modèles d\'échange de la v2 de Kamal.',
        '',
        'FICHIER GÉNÉRÉ par outils/v2/generer_modeles.py depuis web_types.ts et engine-core_types.ts :',
        'ne pas le modifier à la main ; le régénérer (`--ecrire`) quand les types de Kamal changent.',
        f'Empreinte des types sources : {empreinte}',
        '"""',
        'from __future__ import annotations',
        '',
        'from typing import Any, Literal, Optional',
        '',
        'from pydantic import BaseModel, ConfigDict, Field',
        '',
        '',
        'class _Modele(BaseModel):',
        "    model_config = ConfigDict(extra='forbid', populate_by_name=True, strict=True)",
        '',
        '',
    ]
    for nom, valeurs in tr.enums.items():
        sortie.append(f'{nom} = Literal[' + ', '.join(f"'{v}'" for v in valeurs) + ']')
    sortie += ['', '']
    noms = []
    for nom in _ordre_par_heritage(web.interfaces):
        i = web.interfaces[nom]
        corps = tr.classe(nom, [p for p in i.parents if p in web.interfaces], i.champs)
        while tr.imbriques:  # modèles imbriqués d'abord (ils peuvent en contenir d'autres)
            nom_imb, champs = tr.imbriques.pop(0)
            sortie += tr.classe(nom_imb, [], champs)
            noms.append(nom_imb)
        sortie += corps
        noms.append(nom)
    sortie += [f'{n}.model_rebuild()' for n in noms]
    code = '\n'.join(sortie) + '\n'
    if 'Field(' not in code.split('class _Modele', 1)[1]:
        code = code.replace('from pydantic import BaseModel, ConfigDict, Field', 'from pydantic import BaseModel, ConfigDict')
    return code


def _sources(dossier):
    with open(os.path.join(dossier, 'web_types.ts'), encoding='utf-8') as f:
        web = f.read()
    with open(os.path.join(dossier, 'engine-core_types.ts'), encoding='utf-8') as f:
        moteur = f.read()
    return web, moteur


def a_jour(dossier, sortie=SORTIE):
    if not os.path.exists(sortie):
        return False
    with open(sortie, encoding='utf-8') as f:
        return f.read() == generer(*_sources(dossier))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--ecrire', action='store_true')
    mode.add_argument('--verifier', action='store_true')
    p.add_argument('--types', default=TYPES_DEFAUT)
    a = p.parse_args(argv)
    if a.ecrire:
        with open(SORTIE, 'w', encoding='utf-8') as f:
            f.write(generer(*_sources(a.types)))
        print('modèles d\'échange écrits')
        return 0
    ok = a_jour(a.types)
    print('modèles à jour' if ok else 'modèles périmés', file=sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
