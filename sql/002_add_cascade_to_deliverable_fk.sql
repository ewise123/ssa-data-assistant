-- Patch: add ON DELETE CASCADE to Deliverable FK
-- The original CREATE TABLE omitted the cascade policy.
-- Run this once against the live database.

ALTER TABLE "Project_Master_Database"."Deliverable"
    DROP CONSTRAINT "Deliverable_engagement_id_fkey",
    ADD CONSTRAINT "Deliverable_engagement_id_fkey"
        FOREIGN KEY (engagement_id)
        REFERENCES "Project_Master_Database"."ClientEngagement"(engagement_id)
        ON DELETE CASCADE;
