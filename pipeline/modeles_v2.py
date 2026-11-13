"""Modèles d'échange de la v2 de Kamal.

FICHIER GÉNÉRÉ par outils/v2/generer_modeles.py depuis web_types.ts et engine-core_types.ts :
ne pas le modifier à la main ; le régénérer (`--ecrire`) quand les types de Kamal changent.
Empreinte des types sources : 9bd5929b0a1a00c6e332bfdb6e2a2c9166304bed74b739ea9818bdee158fa3de
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class _Modele(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)


PersonType = Literal['PP', 'PM']
RiskCategory = Literal['A', 'B', 'C', 'D', 'E', 'NON_CLASSIFIABLE']
Criticality = Literal['MINEURE', 'MAJEURE', 'CRITIQUE', 'INFORMATION']
Escalade = Literal['CONSEILLER_CLIENTELE', 'DIRECTEUR_AGENCE', 'CELLULE_FRAUDES']
ControlOutcome = Literal['CONFORME', 'ANOMALIE', 'NON_EXECUTABLE', 'ERREUR_TECHNIQUE', 'NON_APPLICABLE']
Verdict = Literal['CONFORME', 'OK_ALERTES_MINEURES', 'SUSPECT', 'TRES_SUSPECT']
AnalysisStatus = Literal['COMPLETE', 'INCOMPLETE', 'EN_ERREUR']
ControlFamily = Literal['IDENTITE', 'EMPLOI_REVENUS', 'BANCAIRE', 'AUTOMOBILE', 'PM_PRO', 'BLACKLIST_GEO']
PieceType = Literal['CIN', 'ATTESTATION_TRAVAIL_SALAIRE', 'BULLETIN_DE_PAIE', 'ATTESTATION_PENSION', 'ATTESTATION_CNSS', 'RELEVE_BANCAIRE', 'ATTESTATION_RIB', 'REGISTRE_COMMERCE', 'STATUTS', 'PV_ASSEMBLEE_GENERALE', 'FACTURE_PROFORMA_VEHICULE', 'CARTE_GRISE', 'CARTE_PROFESSIONNELLE', 'DOMICILIATION']
Applicability = Literal['OUI', 'NON', 'SELON_PROFIL', 'SELON_PIECES', 'SI_AUTO', 'SI_REQUIS', 'SI_RETRAITE', 'SI_STATUTS']
ProductFamily = Literal['AUTO', 'NON_AUTO']
PaymentMode = Literal['PRELEVEMENT_SOURCE', 'PRELEVEMENT_BANCAIRE']
Csp = Literal['FONCTIONNAIRE', 'EMPLOYE_COMMUNE', 'MILITAIRE', 'SALARIE_PRIVE', 'RETRAITE_PUBLIC', 'RETRAITE_CIMR', 'RETRAITE_INDETERMINE', 'PROFESSION_LIBERALE', 'LOUEUR', 'SOCIETE', 'AUTRE']
DossierStatus = Literal['EN_ATTENTE_DONNEES', 'EN_COURS', 'COMPLETE', 'INCOMPLETE', 'EN_ERREUR']
BlacklistKind = Literal['CLIENT', 'EMPLOYEUR', 'GERANT', 'BENEFICIAIRE', 'TIERS_BANCAIRE', 'ZONE']


class Dossier(_Modele):
    id: str
    ref: str
    personType: Optional[PersonType]
    csp: Optional[str]
    productType: Optional[str]
    paymentMode: Optional[str]
    clientName: Optional[str]
    agence: Optional[str]
    canal: Optional[Literal['PHYSIQUE', 'DIGITAL']]
    category: Optional[RiskCategory]
    categoryRule: Optional[int | float]
    categoryReason: Optional[str]
    analysisStatus: DossierStatus
    verdict: Optional[Verdict]
    verdictProvisional: bool
    alertsMinor: int | float
    alertsMajor: int | float
    alertsCritical: int | float
    commentaireScore: Optional[int | float]
    commentaireAlerte: bool
    matrixVersion: Optional[str]
    businessReceivedAt: Optional[str]
    resultsReceivedAt: Optional[str]
    createdAt: str
    updatedAt: str


class DossiersResponse_counts(_Modele):
    verdict: dict[str, int | float]
    status: dict[str, int | float]
    category: dict[str, int | float]


class DossiersResponse(_Modele):
    items: list[Dossier]
    total: int | float
    counts: DossiersResponse_counts


class Piece(_Modele):
    upstreamPieceId: str
    type: str
    extractionStatus: str
    pdfPath: Optional[str]
    fields: dict[str, Any]
    source: str


class AnalysisControl(_Modele):
    id: str
    controlId: str
    applicable: bool
    applicabilityReason: Optional[str]
    outcome: ControlOutcome
    criticality: Optional[Criticality]
    escalade: Optional[Escalade]
    explanation: Optional[str]
    details: Optional[dict[str, Any]]
    missing: list[str]
    source: str
    computedAt: str
    label: str
    family: Optional[ControlFamily]
    numeroMetier: Optional[str]
    previousOutcome: Optional[ControlOutcome]


class AnalysisSummary(_Modele):
    id: str
    trigger: str
    status: DossierStatus
    verdict: Optional[Verdict]
    provisional: bool
    startedAt: str
    endedAt: Optional[str]
    matrixVersion: str
    engineVersion: str
    error: Optional[str]


class ReanalysisInfo_result(_Modele):
    avant: Optional[dict[str, Any]] = None
    apres: Optional[dict[str, Any]] = None


class ReanalysisInfo(_Modele):
    controlId: str
    pieceId: Optional[str]
    requestedFields: list[str]
    result: Optional[ReanalysisInfo_result]
    status: Literal['PENDING', 'RUNNING', 'DONE', 'FAILED']
    createdAt: str
    completedAt: Optional[str]


class LatestAnalysis(_Modele):
    id: str
    matrixVersion: str
    engineVersion: str
    trigger: str
    status: DossierStatus
    verdict: Optional[Verdict]
    provisional: bool
    startedAt: str
    endedAt: Optional[str]
    error: Optional[str]
    controls: list[AnalysisControl]


class BusinessData(_Modele):
    model_config = ConfigDict(extra='allow', populate_by_name=True)
    known_client: Optional[bool] = None
    in_production: Optional[bool] = None


class ConstatLibre(_Modele):
    ordre: int | float
    texte: str
    indicateur: Optional[str]
    valeurCitee: Optional[int | float]
    unite: Optional[str]
    base: Optional[str]
    famille: Optional[str]
    piece: Optional[str]
    source: Optional[str]
    retenu: bool
    motifNonRetenu: Optional[str]
    valeurCalculee: Optional[int | float]
    rang: Optional[int | float]
    effectif: Optional[int | float]
    force: Optional[int | float]
    fiabilite: Optional[int | float]
    score: Optional[int | float]
    note: Optional[str]


class ConstatHorsControles(_Modele):
    code: str
    gravite: str
    pieces: Optional[str]
    valeurs: Optional[str]
    explication: str
    a_verifier: Optional[str]


class Synthese(_Modele):
    vueEnsemble: Optional[str]
    avisComplementaire: Optional[str]
    points: list[str]
    constatsHorsControles: list[ConstatHorsControles]
    score: Optional[int | float]
    alerte: bool
    constats: list[ConstatLibre]
    disponible: bool
    aJour: bool
    date: Optional[str]


class DossierDetail(Dossier):
    businessData: Optional[BusinessData]
    pieces: list[Piece]
    analyses: list[AnalysisSummary]
    reanalyses: list[ReanalysisInfo]
    synthese: Optional[Synthese]
    latestAnalysis: Optional[LatestAnalysis]


class Monitoring(_Modele):
    dossiers: int | float
    enAttenteDonnees: int | float
    enErreur: int | float
    reanalyses: dict[str, int | float]
    intakeMessages: int | float


class BlacklistEntry(_Modele):
    id: str
    kind: BlacklistKind
    label: str
    normalized: Optional[str] = None
    active: bool
    createdAt: str


class LoginResponse(_Modele):
    token: str
    role: Literal['ANALYST', 'ADMIN', 'SUPERADMIN']
    fullName: str


Dossier.model_rebuild()
DossiersResponse_counts.model_rebuild()
DossiersResponse.model_rebuild()
Piece.model_rebuild()
AnalysisControl.model_rebuild()
AnalysisSummary.model_rebuild()
ReanalysisInfo_result.model_rebuild()
ReanalysisInfo.model_rebuild()
LatestAnalysis.model_rebuild()
BusinessData.model_rebuild()
ConstatLibre.model_rebuild()
ConstatHorsControles.model_rebuild()
Synthese.model_rebuild()
DossierDetail.model_rebuild()
Monitoring.model_rebuild()
BlacklistEntry.model_rebuild()
LoginResponse.model_rebuild()
