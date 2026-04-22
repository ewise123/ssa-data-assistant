-- Create the Deliverable table
-- One-to-many: each ClientEngagement can have many Deliverables
--
-- Run against the Project_Master_Database schema:
--   psql "$PG_DSN" -f sql/001_create_deliverable.sql

CREATE TABLE "Project_Master_Database"."Deliverable" (
    deliverable_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id       UUID NOT NULL
        REFERENCES "Project_Master_Database"."ClientEngagement"(engagement_id)
        ON DELETE CASCADE,
    name                TEXT NOT NULL,
    description         TEXT,
    deliverable_type    TEXT,
    delivered_date      DATE,
    notes               TEXT
);

CREATE INDEX idx_deliverable_engagement
    ON "Project_Master_Database"."Deliverable"(engagement_id);

COMMENT ON TABLE  "Project_Master_Database"."Deliverable"
    IS 'Individual deliverables produced for a client engagement.';
COMMENT ON COLUMN "Project_Master_Database"."Deliverable".name
    IS 'Short name of the deliverable (e.g., "Cost Model", "Final Report").';
COMMENT ON COLUMN "Project_Master_Database"."Deliverable".deliverable_type
    IS 'Optional category (e.g., Report, Model, Dashboard, Presentation, Tool).';
COMMENT ON COLUMN "Project_Master_Database"."Deliverable".delivered_date
    IS 'Date the deliverable was provided to the client.';
