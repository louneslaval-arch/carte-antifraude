"""Lecture de schema.prisma (structure de la v2 de Kamal) en structure Python.

Couvre ce que le schéma de Kamal emploie : modèles, énumérations, champs (scalaires, énumérations, relations,
facultatifs `?`, listes `[]`), attributs de champ (@id, @unique, @default, @map, @updatedAt, @relation, @db.<type natif>) et de modèle
(@@id, @@unique, @@index, @@map), commentaires de documentation `///`. Tout attribut ou type inconnu est refusé :
mieux vaut casser que lire de travers la base qu'on doit reproduire à l'identique.
"""
import re
from dataclasses import dataclass, field

SCALAIRES = {'String', 'Boolean', 'Int', 'BigInt', 'Float', 'Decimal', 'DateTime', 'Json', 'Bytes'}
ATTRIBUTS_CHAMP = {'id', 'unique', 'default', 'map', 'updatedAt', 'relation', 'db'}
ATTRIBUTS_MODELE = {'id', 'unique', 'index', 'map'}
BLOCS_IGNORES = {'generator', 'datasource'}


class ErreurPrisma(ValueError):
    pass


@dataclass
class ValeurEnum:
    nom: str
    nom_base: str


@dataclass
class Enum:
    nom: str
    valeurs: list
    nom_base: str
    doc: str = ''


@dataclass
class Champ:
    nom: str
    type: str
    facultatif: bool = False
    liste: bool = False
    colonne: str = ''
    cle_primaire: bool = False
    unique: bool = False
    defaut: str | None = None
    mis_a_jour_auto: bool = False
    type_natif: str | None = None  # @db.Date → 'Date'
    enum: bool = False
    relation: bool = False
    relation_champs: list = field(default_factory=list)
    relation_references: list = field(default_factory=list)
    relation_suppression: str | None = None
    doc: str = ''


@dataclass
class Modele:
    nom: str
    table: str
    champs: list
    cle_primaire: list
    uniques: list
    index: list
    doc: str = ''

    def champ(self, nom):
        for c in self.champs:
            if c.nom == nom:
                return c
        raise KeyError(nom)

    def colonnes(self):
        """Champs qui sont des colonnes de la table (les champs de relation n'en sont pas)."""
        return [c for c in self.champs if not c.relation]


@dataclass
class Schema:
    modeles: dict
    enums: dict


ENTETE = re.compile(r'^(model|enum|generator|datasource|type|view)\s+(\w+)\s*\{\s*$')
CHAMP = re.compile(r'^(\w+)\s+(\w+)(\[\])?(\?)?\s*(.*)$')
ATTRIBUT = re.compile(r'@(db\.\w+|\w+)')


def _sans_commentaire(ligne):
    """Retire un commentaire `//` hors chaîne (les `///` de documentation sont traités avant)."""
    dans_chaine = False
    for i, c in enumerate(ligne):
        if c == '"':
            dans_chaine = not dans_chaine
        elif c == '/' and not dans_chaine and ligne[i:i + 2] == '//':
            return ligne[:i]
    return ligne


def _attributs(texte, permis, ou):
    """Découpe `@nom(args) @autre` en [(nom, args ou None)], parenthèses imbriquées comprises."""
    resultat = []
    i = 0
    while i < len(texte):
        if texte[i].isspace():
            i += 1
            continue
        m = ATTRIBUT.match(texte, i)
        if not m:
            raise ErreurPrisma(f'{ou} : attribut illisible')
        nom = m.group(1)
        if nom.startswith('db.') and 'db' in permis:
            pass
        elif nom not in permis:
            raise ErreurPrisma(f'{ou} : attribut @{nom} inconnu')
        i = m.end()
        args = None
        if i < len(texte) and texte[i] == '(':
            profondeur, debut = 0, i
            while i < len(texte):
                if texte[i] == '(':
                    profondeur += 1
                elif texte[i] == ')':
                    profondeur -= 1
                    if profondeur == 0:
                        break
                i += 1
            if profondeur:
                raise ErreurPrisma(f'{ou} : parenthèse non fermée')
            args = texte[debut + 1:i].strip()
            i += 1
        resultat.append((nom, args))
    return resultat


def _liste(args):
    """`[a, b]` ou `fields: [a, b]` → ['a', 'b']."""
    m = re.search(r'\[([^\]]*)\]', args or '')
    return [x.strip() for x in m.group(1).split(',') if x.strip()] if m else []


def _chaine(args):
    m = re.fullmatch(r'\s*"([^"]*)"\s*', args or '')
    if not m:
        raise ErreurPrisma('nom entre guillemets attendu')
    return m.group(1)


def _argument_nomme(args, nom):
    m = re.search(rf'\b{nom}\s*:\s*(\[[^\]]*\]|\w+)', args or '')
    return m.group(1) if m else None


def lire(texte):
    blocs = []  # (genre, nom, doc, [(ligne, doc)])
    doc = []
    courant = None
    for numero, brute in enumerate(texte.splitlines(), start=1):
        ligne = brute.strip()
        if ligne.startswith('///'):
            doc.append(ligne[3:].strip())
            continue
        ligne = _sans_commentaire(ligne).strip()
        if not ligne:
            continue
        if courant is None:
            m = ENTETE.match(ligne)
            if not m:
                raise ErreurPrisma(f'ligne {numero} : début de bloc attendu')
            courant = (m.group(1), m.group(2), ' '.join(doc), [])
            doc = []
        elif ligne == '}':
            blocs.append(courant)
            courant = None
        else:
            courant[3].append((numero, ligne, ' '.join(doc)))
            doc = []
    if courant is not None:
        raise ErreurPrisma(f'bloc {courant[1]} non fermé')

    noms_enums = {b[1] for b in blocs if b[0] == 'enum'}
    noms_modeles = {b[1] for b in blocs if b[0] == 'model'}
    enums, modeles = {}, {}
    for genre, nom, doc_bloc, lignes in blocs:
        if genre in BLOCS_IGNORES:
            continue
        if genre == 'enum':
            enums[nom] = _lire_enum(nom, doc_bloc, lignes)
        elif genre == 'model':
            modeles[nom] = _lire_modele(nom, doc_bloc, lignes, noms_enums, noms_modeles)
        else:
            raise ErreurPrisma(f'bloc {genre} {nom} non pris en charge')
    return Schema(modeles=modeles, enums=enums)


def _lire_enum(nom, doc, lignes):
    valeurs, nom_base = [], nom
    for numero, ligne, _ in lignes:
        if ligne.startswith('@@'):
            for attr, args in _attributs(ligne[1:], {'map'}, f'enum {nom}, ligne {numero}'):
                nom_base = _chaine(args)
            continue
        m = re.fullmatch(r'(\w+)\s*(.*)', ligne)
        if not m:
            raise ErreurPrisma(f'enum {nom}, ligne {numero} : valeur illisible')
        valeur = ValeurEnum(m.group(1), m.group(1))
        for attr, args in _attributs(m.group(2), {'map'}, f'enum {nom}, ligne {numero}'):
            valeur.nom_base = _chaine(args)
        valeurs.append(valeur)
    return Enum(nom=nom, valeurs=valeurs, nom_base=nom_base, doc=doc)


def _lire_modele(nom, doc, lignes, noms_enums, noms_modeles):
    champs, uniques, index, cle, table = [], [], [], [], nom
    for numero, ligne, doc_champ in lignes:
        ou = f'modèle {nom}, ligne {numero}'
        if ligne.startswith('@@'):
            for attr, args in _attributs(ligne[1:], ATTRIBUTS_MODELE, ou):
                if attr == 'map':
                    table = _chaine(args)
                elif attr == 'id':
                    cle = _liste(args)
                elif attr == 'unique':
                    uniques.append(_liste(args))
                else:
                    index.append(_liste(args))
            continue
        m = CHAMP.match(ligne)
        if not m:
            raise ErreurPrisma(f'{ou} : champ illisible')
        nom_champ, type_, liste, facultatif, reste = m.groups()
        if type_ not in SCALAIRES and type_ not in noms_enums and type_ not in noms_modeles:
            raise ErreurPrisma(f'{ou} : type {type_} inconnu')
        c = Champ(nom=nom_champ, type=type_, facultatif=bool(facultatif), liste=bool(liste), colonne=nom_champ,
                  enum=type_ in noms_enums, relation=type_ in noms_modeles, doc=doc_champ)
        for attr, args in _attributs(reste, ATTRIBUTS_CHAMP, ou):
            if attr == 'id':
                c.cle_primaire = True
            elif attr == 'unique':
                c.unique = True
            elif attr == 'default':
                c.defaut = args
            elif attr == 'map':
                c.colonne = _chaine(args)
            elif attr == 'updatedAt':
                c.mis_a_jour_auto = True
            elif attr.startswith('db.'):
                c.type_natif = attr[3:]
            else:
                c.relation_champs = _liste(_argument_nomme(args, 'fields'))
                c.relation_references = _liste(_argument_nomme(args, 'references'))
                c.relation_suppression = _argument_nomme(args, 'onDelete')
        champs.append(c)
    if not cle:
        cle = [c.nom for c in champs if c.cle_primaire]
    return Modele(nom=nom, table=table, champs=champs, cle_primaire=cle, uniques=uniques, index=index, doc=doc)
