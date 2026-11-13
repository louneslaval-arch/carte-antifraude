-- Miroir de la base de la v2 de Kamal (couche 0), dialecte sqlite.
-- FICHIER GÉNÉRÉ par outils/v2/generer_miroir.py depuis schema.prisma : ne pas le modifier à la main.

CREATE TABLE "Dossier" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "ref" TEXT NOT NULL UNIQUE,
    "actif" INTEGER NOT NULL DEFAULT 1 CHECK ("actif" IN (0, 1)),
    "personType" TEXT CHECK ("personType" IN ('PP', 'PM')),
    "csp" TEXT,
    "productType" TEXT,
    "paymentMode" TEXT,
    "clientName" TEXT,
    "agence" TEXT,
    "canal" TEXT,
    "businessData" TEXT,
    "category" TEXT CHECK ("category" IN ('A', 'B', 'C', 'D', 'E', 'NON_CLASSIFIABLE')),
    "categoryRule" INTEGER,
    "categoryReason" TEXT,
    "analysisStatus" TEXT NOT NULL DEFAULT 'EN_ATTENTE_DONNEES' CHECK ("analysisStatus" IN ('EN_ATTENTE_DONNEES', 'EN_COURS', 'COMPLETE', 'INCOMPLETE', 'EN_ERREUR')),
    "verdict" TEXT CHECK ("verdict" IN ('CONFORME', 'OK_ALERTES_MINEURES', 'SUSPECT', 'TRES_SUSPECT')),
    "verdictProvisional" INTEGER NOT NULL DEFAULT 0 CHECK ("verdictProvisional" IN (0, 1)),
    "alertsMinor" INTEGER NOT NULL DEFAULT 0,
    "alertsMajor" INTEGER NOT NULL DEFAULT 0,
    "alertsCritical" INTEGER NOT NULL DEFAULT 0,
    "matrixVersion" TEXT,
    "businessReceivedAt" TEXT,
    "resultsReceivedAt" TEXT,
    "commentaireScore" REAL,
    "commentaireAlerte" INTEGER NOT NULL DEFAULT 0 CHECK ("commentaireAlerte" IN (0, 1)),
    "createdAt" TEXT NOT NULL,
    "updatedAt" TEXT NOT NULL
);
CREATE INDEX "Dossier_category_idx" ON "Dossier" ("category");
CREATE INDEX "Dossier_verdict_idx" ON "Dossier" ("verdict");
CREATE INDEX "Dossier_analysisStatus_idx" ON "Dossier" ("analysisStatus");
CREATE INDEX "Dossier_createdAt_idx" ON "Dossier" ("createdAt");

CREATE TABLE "IntakeMessage" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "kind" TEXT NOT NULL CHECK ("kind" IN ('BUSINESS_DATA', 'TANDEM_RESULTS', 'PDF')),
    "payload" TEXT,
    "filePath" TEXT,
    "sha256" TEXT,
    "receivedAt" TEXT NOT NULL,
    FOREIGN KEY ("dossierId") REFERENCES "Dossier" ("id") ON DELETE CASCADE
);
CREATE INDEX "IntakeMessage_dossierId_kind_idx" ON "IntakeMessage" ("dossierId", "kind");

CREATE TABLE "Piece" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "upstreamPieceId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "pdfPath" TEXT,
    "sha256" TEXT,
    "extractionStatus" TEXT NOT NULL,
    "fields" TEXT NOT NULL,
    "source" TEXT NOT NULL DEFAULT 'AMONT' CHECK ("source" IN ('AMONT', 'REANALYSE')),
    "createdAt" TEXT NOT NULL,
    "updatedAt" TEXT NOT NULL,
    UNIQUE ("dossierId", "upstreamPieceId"),
    FOREIGN KEY ("dossierId") REFERENCES "Dossier" ("id") ON DELETE CASCADE
);
CREATE INDEX "Piece_dossierId_type_idx" ON "Piece" ("dossierId", "type");

CREATE TABLE "Analysis" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "matrixVersion" TEXT NOT NULL,
    "engineVersion" TEXT NOT NULL,
    "trigger" TEXT NOT NULL CHECK ("trigger" IN ('INTAKE', 'REANALYSE', 'REPLAY')),
    "status" TEXT NOT NULL CHECK ("status" IN ('EN_ATTENTE_DONNEES', 'EN_COURS', 'COMPLETE', 'INCOMPLETE', 'EN_ERREUR')),
    "verdict" TEXT CHECK ("verdict" IN ('CONFORME', 'OK_ALERTES_MINEURES', 'SUSPECT', 'TRES_SUSPECT')),
    "provisional" INTEGER NOT NULL DEFAULT 0 CHECK ("provisional" IN (0, 1)),
    "startedAt" TEXT NOT NULL,
    "endedAt" TEXT,
    "error" TEXT,
    FOREIGN KEY ("dossierId") REFERENCES "Dossier" ("id") ON DELETE CASCADE
);
CREATE INDEX "Analysis_dossierId_startedAt_idx" ON "Analysis" ("dossierId", "startedAt");

CREATE TABLE "AnalysisControl" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "analysisId" TEXT NOT NULL,
    "dossierId" TEXT NOT NULL,
    "controlId" TEXT NOT NULL,
    "applicable" INTEGER NOT NULL CHECK ("applicable" IN (0, 1)),
    "applicabilityReason" TEXT NOT NULL,
    "outcome" TEXT NOT NULL CHECK ("outcome" IN ('CONFORME', 'ANOMALIE', 'NON_EXECUTABLE', 'ERREUR_TECHNIQUE', 'NON_APPLICABLE')),
    "criticality" TEXT CHECK ("criticality" IN ('MINEURE', 'MAJEURE', 'CRITIQUE', 'INFORMATION')),
    "escalade" TEXT CHECK ("escalade" IN ('CONSEILLER_CLIENTELE', 'DIRECTEUR_AGENCE', 'CELLULE_FRAUDES')),
    "explanation" TEXT,
    "details" TEXT,
    "missing" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "computedAt" TEXT NOT NULL,
    UNIQUE ("analysisId", "controlId"),
    FOREIGN KEY ("analysisId") REFERENCES "Analysis" ("id") ON DELETE CASCADE
);
CREATE INDEX "AnalysisControl_dossierId_controlId_idx" ON "AnalysisControl" ("dossierId", "controlId");

CREATE TABLE "Reanalysis" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "analysisId" TEXT,
    "controlId" TEXT NOT NULL,
    "pieceId" TEXT,
    "requestedFields" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'PENDING' CHECK ("status" IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "model" TEXT,
    "costUsd" REAL,
    "result" TEXT,
    "error" TEXT,
    "createdAt" TEXT NOT NULL,
    "completedAt" TEXT,
    FOREIGN KEY ("dossierId") REFERENCES "Dossier" ("id") ON DELETE CASCADE,
    FOREIGN KEY ("analysisId") REFERENCES "Analysis" ("id")
);
CREATE INDEX "Reanalysis_status_createdAt_idx" ON "Reanalysis" ("status", "createdAt");

CREATE TABLE "BlacklistEntry" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "kind" TEXT NOT NULL CHECK ("kind" IN ('CLIENT', 'EMPLOYEUR', 'GERANT', 'BENEFICIAIRE', 'TIERS_BANCAIRE', 'ZONE')),
    "label" TEXT NOT NULL,
    "normalized" TEXT NOT NULL,
    "city" TEXT,
    "active" INTEGER NOT NULL DEFAULT 1 CHECK ("active" IN (0, 1)),
    "createdAt" TEXT NOT NULL,
    "personne" TEXT,
    "nom" TEXT,
    "prenom" TEXT,
    "raisonSociale" TEXT,
    "cin" TEXT,
    "rc" TEXT,
    "typeListe" TEXT,
    "motif" TEXT,
    "source" TEXT
);
CREATE INDEX "BlacklistEntry_kind_normalized_idx" ON "BlacklistEntry" ("kind", "normalized");
CREATE INDEX "BlacklistEntry_kind_cin_idx" ON "BlacklistEntry" ("kind", "cin");
CREATE INDEX "BlacklistEntry_kind_rc_idx" ON "BlacklistEntry" ("kind", "rc");

CREATE TABLE "Employeur" (
    "ice" TEXT NOT NULL PRIMARY KEY,
    "noms" TEXT NOT NULL,
    "vus" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TEXT NOT NULL,
    "updatedAt" TEXT NOT NULL
);

CREATE TABLE "Synthese" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "analysisId" TEXT NOT NULL UNIQUE,
    "vueEnsemble" TEXT,
    "avisComplementaire" TEXT,
    "points" TEXT,
    "status" TEXT NOT NULL DEFAULT 'EN_COURS',
    "error" TEXT,
    "costUsd" REAL,
    "score" REAL,
    "alerte" INTEGER NOT NULL DEFAULT 0 CHECK ("alerte" IN (0, 1)),
    "noteeLe" TEXT,
    "createdAt" TEXT NOT NULL,
    "completedAt" TEXT
);
CREATE INDEX "Synthese_dossierId_idx" ON "Synthese" ("dossierId");

CREATE TABLE "IndicateurDossier" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "indicateur" TEXT NOT NULL,
    "valeur" REAL NOT NULL,
    "source" TEXT NOT NULL,
    "details" TEXT,
    "updatedAt" TEXT NOT NULL,
    UNIQUE ("dossierId", "indicateur"),
    FOREIGN KEY ("dossierId") REFERENCES "Dossier" ("id") ON DELETE CASCADE
);
CREATE INDEX "IndicateurDossier_indicateur_idx" ON "IndicateurDossier" ("indicateur");

CREATE TABLE "ConstatLibre" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "syntheseId" TEXT NOT NULL,
    "dossierId" TEXT NOT NULL,
    "ordre" INTEGER NOT NULL,
    "texte" TEXT NOT NULL,
    "indicateur" TEXT,
    "valeurCitee" REAL,
    "unite" TEXT,
    "base" TEXT,
    "famille" TEXT,
    "piece" TEXT,
    "source" TEXT,
    "retenu" INTEGER NOT NULL DEFAULT 0 CHECK ("retenu" IN (0, 1)),
    "motifNonRetenu" TEXT,
    "valeurCalculee" REAL,
    "rang" REAL,
    "effectif" INTEGER,
    "force" INTEGER,
    "fiabilite" REAL,
    "score" REAL,
    "note" TEXT,
    "createdAt" TEXT NOT NULL,
    FOREIGN KEY ("syntheseId") REFERENCES "Synthese" ("id") ON DELETE CASCADE,
    FOREIGN KEY ("dossierId") REFERENCES "Dossier" ("id") ON DELETE CASCADE
);
CREATE INDEX "ConstatLibre_dossierId_idx" ON "ConstatLibre" ("dossierId");
CREATE INDEX "ConstatLibre_syntheseId_idx" ON "ConstatLibre" ("syntheseId");

CREATE TABLE "User" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "email" TEXT NOT NULL UNIQUE,
    "passwordHash" TEXT NOT NULL,
    "fullName" TEXT,
    "role" TEXT NOT NULL DEFAULT 'ANALYST' CHECK ("role" IN ('ANALYST', 'ADMIN', 'SUPERADMIN')),
    "createdAt" TEXT NOT NULL
);

CREATE TABLE "LlmBudget" (
    "day" TEXT NOT NULL PRIMARY KEY,
    "costUsd" REAL NOT NULL DEFAULT 0,
    "calls" INTEGER NOT NULL DEFAULT 0
);
