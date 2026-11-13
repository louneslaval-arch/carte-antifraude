"""Lecture des types TypeScript de Kamal (web_types.ts, engine-core_types.ts) en structure Python.

Prend en charge ce que ces fichiers emploient : `import type {…} from '…'`, `export type X = …` (une union de chaînes
devient une énumération ; tout autre alias garde son texte), `export interface X extends Y { … }` avec champs
facultatifs `?`, objets imbriqués, commentaires `/** … */` (gardés comme documentation) et `//`. Une déclaration non
fermée est refusée.
"""
import re
from dataclasses import dataclass, field


class ErreurTypes(ValueError):
    pass


@dataclass
class Champ:
    nom: str
    type: str
    facultatif: bool = False
    doc: str = ''
    sous_champs: list = field(default_factory=list)

    @property
    def nullable(self):
        return 'null' in _membres_union(self.type)

    @property
    def valeurs(self):
        """Valeurs d'une union de chaînes en ligne (`'A' | 'B' | null`), sinon []."""
        membres = [m for m in _membres_union(self.type) if m not in ('null', 'undefined')]
        return [m[1:-1] for m in membres] if membres and all(_est_chaine(m) for m in membres) else []

    @property
    def references(self):
        """Noms de types déclarés ailleurs employés par ce champ (majuscule initiale, hors Record, Array…)."""
        noms = re.findall(r"\b([A-Z]\w*)\b", re.sub(r"'[^']*'", '', self.type))
        return [n for n in dict.fromkeys(noms) if n not in GENERIQUES]


@dataclass
class Interface:
    nom: str
    parents: list
    champs: list
    doc: str = ''

    def champ(self, nom):
        for c in self.champs:
            if c.nom == nom:
                return c
        raise KeyError(nom)


@dataclass
class Types:
    importations: dict
    enumerations: dict
    alias: dict
    interfaces: dict

    def champs_complets(self, nom):
        """Champs d'une interface, ceux de ses parents d'abord (parents déclarés dans le même fichier)."""
        i = self.interfaces[nom]
        resultat = []
        for p in i.parents:
            if p in self.interfaces:
                resultat.extend(self.champs_complets(p))
        return resultat + i.champs


GENERIQUES = {'Record', 'Array', 'Partial', 'Exclude', 'Omit', 'Pick', 'Readonly', 'Promise', 'Date'}


def _est_chaine(t):
    return len(t) >= 2 and t[0] == t[-1] == "'"


def _decouper(texte, separateurs):
    """Découpe au niveau zéro des accolades, crochets, parenthèses et chevrons, hors chaînes."""
    morceaux, courant, profondeur, chaine = [], [], 0, False
    for c in texte:
        if c == "'":
            chaine = not chaine
        elif not chaine:
            if c in '{[(<':
                profondeur += 1
            elif c in '}])>':
                profondeur -= 1
            elif c in separateurs and profondeur == 0:
                morceaux.append(''.join(courant))
                courant = []
                continue
        courant.append(c)
    morceaux.append(''.join(courant))
    return [m.strip() for m in morceaux if m.strip()]


def _membres_union(t):
    return _decouper(t, '|')


def _sans_commentaires_ligne(texte):
    """Retire les commentaires `//` (hors chaîne) ; garde les blocs `/** */` pour la documentation."""
    sortie = []
    for ligne in texte.splitlines():
        chaine = False
        for i, c in enumerate(ligne):
            if c == "'":
                chaine = not chaine
            elif not chaine and ligne[i:i + 2] == '//':
                ligne = ligne[:i]
                break
        sortie.append(ligne)
    return '\n'.join(sortie)


DOC = re.compile(r'/\*\*?(.*?)\*/', re.S)


def _texte_doc(bloc):
    return ' '.join(l.strip().lstrip('*').strip() for l in bloc.splitlines()).strip()


def _fin_bloc(texte, debut):
    """Indice de l'accolade fermante qui répond à celle de `debut`."""
    profondeur, chaine = 0, False
    for i in range(debut, len(texte)):
        c = texte[i]
        if c == "'":
            chaine = not chaine
        elif not chaine and c == '{':
            profondeur += 1
        elif not chaine and c == '}':
            profondeur -= 1
            if profondeur == 0:
                return i
    raise ErreurTypes('accolade non fermée')


def _champs(corps):
    champs, doc_attente = [], ''
    for membre in _decouper(corps, ';\n'):
        doc = doc_attente
        m_doc = DOC.search(membre)
        if m_doc:
            doc = _texte_doc(m_doc.group(1))
            membre = DOC.sub('', membre).strip()
        if not membre:  # commentaire seul sur sa ligne : il documente le membre suivant
            doc_attente = doc
            continue
        if membre.startswith('/*') or membre.startswith('*'):  # morceau d'un bloc sur plusieurs lignes
            doc_attente = (doc_attente + ' ' + membre.strip('/* ')).strip()
            continue
        doc_attente = ''
        m = re.match(r'^(\w+)(\?)?\s*:\s*(.+)$', membre, re.S)
        if not m:
            m_index = re.match(r'^\[[^\]]+\]\s*:\s*(.+)$', membre, re.S)
            if m_index:
                champs.append(Champ('[index]', ' '.join(m_index.group(1).split()), doc=doc))
                continue
            raise ErreurTypes('membre illisible')
        type_ = ' '.join(m.group(3).split()).rstrip(',')
        c = Champ(m.group(1), type_, facultatif=bool(m.group(2)), doc=doc)
        if type_.startswith('{') and type_.endswith('}'):
            c.sous_champs = _champs(type_[1:-1])
        champs.append(c)
    return champs


def _neutraliser_blocs(texte):
    """Dans les blocs `/* */`, les apostrophes et `//` ne sont ni des chaînes ni des commentaires de ligne."""
    return re.sub(r'/\*.*?\*/', lambda m: m.group(0).replace("'", '\u2019').replace('//', '/ /'), texte,
                  flags=re.S)


def lire(texte):
    texte = _sans_commentaires_ligne(_neutraliser_blocs(texte))
    importations, enumerations, alias, interfaces = {}, {}, {}, {}
    i, doc_attente = 0, ''
    while i < len(texte):
        reste = texte[i:]
        m_doc = re.match(r'\s*/\*\*?(.*?)\*/', reste, re.S)
        if m_doc:
            doc_attente = _texte_doc(m_doc.group(1))
            i += m_doc.end()
            continue
        m_imp = re.match(r"\s*import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*'([^']+)';?", reste, re.S)
        if m_imp:
            for nom in _decouper(m_imp.group(1), ','):
                importations[nom.split(' as ')[-1].strip()] = m_imp.group(2)
            i += m_imp.end()
            continue
        m_int = re.match(r'\s*export\s+interface\s+(\w+)(?:\s+extends\s+([\w\s,]+?))?\s*\{', reste)
        if m_int:
            debut = i + m_int.end() - 1
            fin = _fin_bloc(texte, debut)
            parents = [p.strip() for p in (m_int.group(2) or '').split(',') if p.strip()]
            interfaces[m_int.group(1)] = Interface(m_int.group(1), parents, _champs(texte[debut + 1:fin]),
                                                   doc_attente)
            doc_attente, i = '', fin + 1
            continue
        m_type = re.match(r'\s*export\s+type\s+(\w+)\s*=', reste)
        if m_type:
            debut = i + m_type.end()
            membres = _decouper(texte[debut:], ';')
            if not membres:
                raise ErreurTypes(f'type {m_type.group(1)} vide')
            corps = membres[0]
            fin = texte.index(corps, debut) + len(corps)
            union = [m for m in _membres_union(corps)]
            if union and all(_est_chaine(m) for m in union):
                enumerations[m_type.group(1)] = [m[1:-1] for m in union]
            else:
                alias[m_type.group(1)] = ' '.join(corps.split())
            doc_attente = ''
            i = fin + 1
            continue
        if reste.strip() == '':
            break
        if re.match(r'\s*;', reste):
            i += re.match(r'\s*;', reste).end()
            continue
        raise ErreurTypes(f'déclaration illisible près de : {reste.strip()[:40]!r}')
    return Types(importations, enumerations, alias, interfaces)
