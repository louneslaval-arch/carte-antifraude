-- Miroir de la base de la v2 de Kamal (couche 0), dialecte postgresql.
-- FICHIER GÉNÉRÉ par outils/v2/generer_miroir.py depuis schema.prisma : ne pas le modifier à la main.

CREATE TABLE "Dossier" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "ref" TEXT NOT NULL UNIQUE,
    "actif" BOOLEAN NOT NULL DEFAULT true,
    "personType" TEXT CHECK ("personType" IN ('PP', 'PM')),
    "csp" TEXT,
    "productType" TEXT,
    "paymentMode" TEXT,
    "clientName" TEXT,
    "agence" TEXT,
    "canal" TEXT,
    "businessData" JSONB,
    "category" TEXT CHECK ("category" IN ('A', 'B', 'C', 'D', 'E', 'NON_CLASSIFIABLE')),
    "categoryRule" INTEGER,
    "categoryReason" TEXT,
    "analysisStatus" TEXT NOT NULL DEFAULT 'EN_ATTENTE_DONNEES' CHECK ("analysisStatus" IN ('EN_ATTENTE_DONNEES', 'EN_COURS', 'COMPLETE', 'INCOMPLETE', 'EN_ERREUR')),
    "verdict" TEXT CHECK ("verdict" IN ('CONFORME', 'OK_ALERTES_MINEURES', 'SUSPECT', 'TRES_SUSPECT')),
    "verdictProvisional" BOOLEAN NOT NULL DEFAULT false,
    "alertsMinor" INTEGER NOT NULL DEFAULT 0,
    "alertsMajor" INTEGER NOT NULL DEFAULT 0,
    "alertsCritical" INTEGER NOT NULL DEFAULT 0,
    "matrixVersion" TEXT,
    "businessReceivedAt" TIMESTAMP(3),
    "resultsReceivedAt" TIMESTAMP(3),
    "commentaireScore" DOUBLE PRECISION,
    "commentaireAlerte" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL
);
CREATE INDEX "Dossier_category_idx" ON "Dossier" ("category");
CREATE INDEX "Dossier_verdict_idx" ON "Dossier" ("verdict");
CREATE INDEX "Dossier_analysisStatus_idx" ON "Dossier" ("analysisStatus");
CREATE INDEX "Dossier_createdAt_idx" ON "Dossier" ("createdAt");

CREATE TABLE "IntakeMessage" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "kind" TEXT NOT NULL CHECK ("kind" IN ('BUSINESS_DATA', 'TANDEM_RESULTS', 'PDF')),
    "payload" JSONB,
    "filePath" TEXT,
    "sha256" TEXT,
    "receivedAt" TIMESTAMP(3) NOT NULL,
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
    "fields" JSONB NOT NULL,
    "source" TEXT NOT NULL DEFAULT 'AMONT' CHECK ("source" IN ('AMONT', 'REANALYSE')),
    "createdAt" TIMESTAMP(3) NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL,
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
    "provisional" BOOLEAN NOT NULL DEFAULT false,
    "startedAt" TIMESTAMP(3) NOT NULL,
    "endedAt" TIMESTAMP(3),
    "error" TEXT,
    FOREIGN KEY ("dossierId") REFERENCES "Dossier" ("id") ON DELETE CASCADE
);
CREATE INDEX "Analysis_dossierId_startedAt_idx" ON "Analysis" ("dossierId", "startedAt");

CREATE TABLE "AnalysisControl" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "analysisId" TEXT NOT NULL,
    "dossierId" TEXT NOT NULL,
    "controlId" TEXT NOT NULL,
    "applicable" BOOLEAN NOT NULL,
    "applicabilityReason" TEXT NOT NULL,
    "outcome" TEXT NOT NULL CHECK ("outcome" IN ('CONFORME', 'ANOMALIE', 'NON_EXECUTABLE', 'ERREUR_TECHNIQUE', 'NON_APPLICABLE')),
    "criticality" TEXT CHECK ("criticality" IN ('MINEURE', 'MAJEURE', 'CRITIQUE', 'INFORMATION')),
    "escalade" TEXT CHECK ("escalade" IN ('CONSEILLER_CLIENTELE', 'DIRECTEUR_AGENCE', 'CELLULE_FRAUDES')),
    "explanation" TEXT,
    "details" JSONB,
    "missing" TEXT[] NOT NULL,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL,
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
    "requestedFields" TEXT[] NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'PENDING' CHECK ("status" IN ('PENDING', 'RUNNING', 'DONE', 'FAILED')),
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "model" TEXT,
    "costUsd" DOUBLE PRECISION,
    "result" JSONB,
    "error" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL,
    "completedAt" TIMESTAMP(3),
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
    "active" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL,
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
    "noms" TEXT[] NOT NULL,
    "vus" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMP(3) NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL
);

CREATE TABLE "Synthese" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "analysisId" TEXT NOT NULL UNIQUE,
    "vueEnsemble" TEXT,
    "avisComplementaire" TEXT,
    "points" JSONB,
    "status" TEXT NOT NULL DEFAULT 'EN_COURS',
    "error" TEXT,
    "costUsd" DOUBLE PRECISION,
    "score" DOUBLE PRECISION,
    "alerte" BOOLEAN NOT NULL DEFAULT false,
    "noteeLe" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL,
    "completedAt" TIMESTAMP(3)
);
CREATE INDEX "Synthese_dossierId_idx" ON "Synthese" ("dossierId");

CREATE TABLE "IndicateurDossier" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "dossierId" TEXT NOT NULL,
    "indicateur" TEXT NOT NULL,
    "valeur" DOUBLE PRECISION NOT NULL,
    "source" TEXT NOT NULL,
    "details" JSONB,
    "updatedAt" TIMESTAMP(3) NOT NULL,
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
    "valeurCitee" DOUBLE PRECISION,
    "unite" TEXT,
    "base" TEXT,
    "famille" TEXT,
    "piece" TEXT,
    "source" TEXT,
    "retenu" BOOLEAN NOT NULL DEFAULT false,
    "motifNonRetenu" TEXT,
    "valeurCalculee" DOUBLE PRECISION,
    "rang" DOUBLE PRECISION,
    "effectif" INTEGER,
    "force" INTEGER,
    "fiabilite" DOUBLE PRECISION,
    "score" DOUBLE PRECISION,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL,
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
    "createdAt" TIMESTAMP(3) NOT NULL
);

CREATE TABLE "LlmBudget" (
    "day" DATE NOT NULL PRIMARY KEY,
    "costUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "calls" INTEGER NOT NULL DEFAULT 0
);
