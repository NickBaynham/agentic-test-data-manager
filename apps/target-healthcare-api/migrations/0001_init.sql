-- Target Healthcare API initial schema (Phase 2)
--
-- Seven entities per BRD §9. Every mutable table carries test_run_id NOT NULL
-- and an index on it (DR-001 — powers reset_run). Reference tables
-- (procedure_code, diagnosis_code) allow test_run_id NULL for shared rows.
--
-- NFR-010 enforced at DDL:
--   - member.first_name / last_name must start with 'FAKE_' literal.
--   - member.address_state must equal 'ZZ' (fictional state code).
--
-- This file is run by Postgres's docker-entrypoint-initdb.d on first volume
-- initialization. It is also idempotent (CREATE ... IF NOT EXISTS), so the
-- integration test fixture can re-apply it against a running Postgres.
-- If you change the schema, run `make down-clean` to wipe the volume and let
-- the entrypoint re-run, or apply your changes via a new migration file.

-- ---------------------------------------------------------------------------
-- Reference tables: shared baseline rows + per-run "invalid" variants
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS procedure_code (
    code        TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    is_valid    BOOLEAN NOT NULL DEFAULT TRUE,
    test_run_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS diagnosis_code (
    code        TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    is_valid    BOOLEAN NOT NULL DEFAULT TRUE,
    test_run_id TEXT NULL
);

-- ---------------------------------------------------------------------------
-- Plan (independent — no FKs in)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plan (
    plan_id        TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    coverage_type  TEXT NOT NULL CHECK (coverage_type IN ('hmo', 'ppo', 'epo', 'pos')),
    effective_date DATE NOT NULL,
    test_run_id    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_test_run_id ON plan(test_run_id);

-- ---------------------------------------------------------------------------
-- Provider (independent — no FKs in)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS provider (
    provider_id    TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    network_status TEXT NOT NULL CHECK (network_status IN ('in_network', 'out_of_network')),
    npi_fake       TEXT NOT NULL,
    test_run_id    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_test_run_id ON provider(test_run_id);

-- ---------------------------------------------------------------------------
-- Member (FK to plan; CHECKs enforce NFR-010 markers)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS member (
    member_id     TEXT PRIMARY KEY,
    status        TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
    first_name    TEXT NOT NULL CHECK (first_name LIKE 'FAKE\_%' ESCAPE '\'),
    last_name     TEXT NOT NULL CHECK (last_name  LIKE 'FAKE\_%' ESCAPE '\'),
    date_of_birth DATE NOT NULL,
    address_line1 TEXT NOT NULL,
    address_city  TEXT NOT NULL,
    address_state TEXT NOT NULL CHECK (address_state = 'ZZ'),
    address_zip   TEXT NOT NULL,
    plan_id       TEXT NOT NULL REFERENCES plan(plan_id),
    test_run_id   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_member_test_run_id ON member(test_run_id);
CREATE INDEX IF NOT EXISTS idx_member_plan_id     ON member(plan_id);

-- ---------------------------------------------------------------------------
-- Eligibility (FK to member; temporal CHECK)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eligibility (
    eligibility_id TEXT PRIMARY KEY,
    member_id      TEXT NOT NULL REFERENCES member(member_id),
    effective_from DATE NOT NULL,
    effective_to   DATE NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('active', 'inactive', 'expired')),
    test_run_id    TEXT NOT NULL,
    CHECK (effective_to >= effective_from)
);
CREATE INDEX IF NOT EXISTS idx_eligibility_test_run_id ON eligibility(test_run_id);
CREATE INDEX IF NOT EXISTS idx_eligibility_member_id   ON eligibility(member_id);

-- ---------------------------------------------------------------------------
-- Claim (FK to member, provider, procedure_code, diagnosis_code)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claim (
    claim_id       TEXT PRIMARY KEY,
    member_id      TEXT NOT NULL REFERENCES member(member_id),
    provider_id    TEXT NOT NULL REFERENCES provider(provider_id),
    procedure_code TEXT NOT NULL REFERENCES procedure_code(code),
    diagnosis_code TEXT NOT NULL REFERENCES diagnosis_code(code),
    status         TEXT NOT NULL CHECK (status IN ('paid', 'denied', 'pending')),
    submitted_at   TIMESTAMPTZ NOT NULL,
    denial_reason  TEXT NULL,
    test_run_id    TEXT NOT NULL,
    CHECK (
        (status = 'denied' AND denial_reason IS NOT NULL)
        OR
        (status <> 'denied')
    )
);
CREATE INDEX IF NOT EXISTS idx_claim_test_run_id  ON claim(test_run_id);
CREATE INDEX IF NOT EXISTS idx_claim_member_id    ON claim(member_id);
CREATE INDEX IF NOT EXISTS idx_claim_provider_id  ON claim(provider_id);

-- ---------------------------------------------------------------------------
-- Baseline reference data (shared across all runs — test_run_id IS NULL)
-- ---------------------------------------------------------------------------
INSERT INTO procedure_code (code, description, is_valid, test_run_id) VALUES
    ('99213', 'Office visit, established patient',                TRUE, NULL),
    ('99214', 'Office visit, established patient, moderate',      TRUE, NULL),
    ('70553', 'MRI brain with and without contrast',              TRUE, NULL),
    ('00000', 'Synthetic invalid procedure code (denial driver)', FALSE, NULL)
ON CONFLICT (code) DO NOTHING;

INSERT INTO diagnosis_code (code, description, is_valid, test_run_id) VALUES
    ('Z00.00', 'Encounter for general adult medical examination', TRUE, NULL),
    ('M54.5',  'Low back pain',                                   TRUE, NULL),
    ('R51',    'Headache',                                        TRUE, NULL),
    ('ZZZ.99', 'Synthetic invalid diagnosis code (denial driver)', FALSE, NULL)
ON CONFLICT (code) DO NOTHING;
