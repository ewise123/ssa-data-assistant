# app/schema_hints.py

SCHEMA_NAME = "Project_Master_Database"  # your Postgres schema

SCHEMA_HINTS = {
    # === DATASET: clients & contacts ===
    "clients": f"""
    Tables (schema-qualified, quoted):
      - "{SCHEMA_NAME}"."ClientList"(client_id, client_firm_name, industry, field, geographic_presence, ownership_type, pe_firm_id)
      - "{SCHEMA_NAME}"."ClientContact"(contact_id, contact_name, role_to_ssa, organization, internal_role, email, client_id)
      - "{SCHEMA_NAME}"."ClientContactResource"(contact_id, resource_id)
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster"(resource_id, name, resource_type, education, qualifications, previous_work_experience, role_rank, title_id)
      - "{SCHEMA_NAME}"."ClientEngagement"(engagement_id, project_name, client_id, problem, approach, milestones_activities, recurring_impact_annual, one_time_impact, outcomes_impact, notes, case_study, start_date, status, end_date, capex_baseline, current_spend_baseline)
      - "{SCHEMA_NAME}"."Deliverable"(deliverable_id, engagement_id, name, description, deliverable_type, delivered_date, notes)
      - "{SCHEMA_NAME}"."EngagementContact"(engagement_id, contact_id)

    Relationships:
      - "{SCHEMA_NAME}"."ClientContact".client_id → "{SCHEMA_NAME}"."ClientList".client_id
      - "{SCHEMA_NAME}"."ClientEngagement".client_id → "{SCHEMA_NAME}"."ClientList".client_id
      - "{SCHEMA_NAME}"."Deliverable".engagement_id → "{SCHEMA_NAME}"."ClientEngagement".engagement_id
      - "{SCHEMA_NAME}"."ClientContactResource".contact_id → "{SCHEMA_NAME}"."ClientContact".contact_id
      - "{SCHEMA_NAME}"."ClientContactResource".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."EngagementContact".engagement_id → "{SCHEMA_NAME}"."ClientEngagement".engagement_id
      - "{SCHEMA_NAME}"."EngagementContact".contact_id → "{SCHEMA_NAME}"."ClientContact".contact_id

    Notes:
      - Use "{SCHEMA_NAME}"."ClientList" for firm-level attributes (client_firm_name, industry, etc.).
      - Join to "{SCHEMA_NAME}"."ClientContact" for people + emails at those firms.
      - "{SCHEMA_NAME}"."ClientContact" stores external client stakeholders only; do not use it for SSA internal contacts or IC relationships.
      - Traverse "{SCHEMA_NAME}"."ClientContactResource" to reach "{SCHEMA_NAME}"."ConsolidatedResourceRoster" when you need the resources tied to each contact (IDs only; join for names).
      - Always schema-qualify and double-quote identifiers exactly as listed above.
      - Baseline engagement finances live on "{SCHEMA_NAME}"."ClientEngagement": capex_baseline for capital expenditure and current_spend_baseline for current spend.
    """,

    # === DATASET: consultants / resources / tools / capabilities ===
    "consultants": f"""
    Tables:
      - "{SCHEMA_NAME}"."ConsultantRoster"(consultant_id, name, title_id, email, phone_number)
      - "{SCHEMA_NAME}"."ICRoster"(ic_id, name, rate_daily, email, phone_number)
      - "{SCHEMA_NAME}"."ResourceIC"(resource_id, ic_id)
      - "{SCHEMA_NAME}"."ICSSAContact"(ic_id, resource_id)
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster"(resource_id, name, resource_type, education, qualifications, previous_work_experience, role_rank, title_id)
      - "{SCHEMA_NAME}"."ClientContactResource"(contact_id, resource_id)
      - "{SCHEMA_NAME}"."TitleMaster"(title_id, title)
      - "{SCHEMA_NAME}"."FirmCapabilities"(capability_id, capability_name)
      - "{SCHEMA_NAME}"."ResourceCapability"(resource_id, capability_id)
      - "{SCHEMA_NAME}"."FirmTool"(tool_id, tool_name, vendor_name, tool_type, licensing, cost)
      - "{SCHEMA_NAME}"."ToolCapability"(tool_id, capability_id)
      - "{SCHEMA_NAME}"."ResourceTool"(resource_id, tool_id, proficiency_level, last_validated)

    Relationships:
      - "{SCHEMA_NAME}"."ConsultantRoster".title_id → "{SCHEMA_NAME}"."TitleMaster".title_id
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster".title_id → "{SCHEMA_NAME}"."TitleMaster".title_id
      - "{SCHEMA_NAME}"."ResourceCapability".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ResourceCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
      - "{SCHEMA_NAME}"."ClientContactResource".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ResourceIC".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ResourceIC".ic_id → "{SCHEMA_NAME}"."ICRoster".ic_id
      - "{SCHEMA_NAME}"."ICSSAContact".ic_id → "{SCHEMA_NAME}"."ICRoster".ic_id
      - "{SCHEMA_NAME}"."ICSSAContact".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ToolCapability".tool_id → "{SCHEMA_NAME}"."FirmTool".tool_id
      - "{SCHEMA_NAME}"."ToolCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
      - "{SCHEMA_NAME}"."ResourceTool".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ResourceTool".tool_id → "{SCHEMA_NAME}"."FirmTool".tool_id

    Notes:
      - Ontology:
          * Tools live in "{SCHEMA_NAME}"."FirmTool" and map to capabilities via "{SCHEMA_NAME}"."ToolCapability".
          * Resources link directly to tools via "{SCHEMA_NAME}"."ResourceTool" (with proficiency_level and last_validated metadata).
          * Capabilities live in "{SCHEMA_NAME}"."FirmCapabilities" and map to people/resources via "{SCHEMA_NAME}"."ResourceCapability".
          * Independent contractors connect to resources via "{SCHEMA_NAME}"."ResourceIC" (legacy "ConsultantIC" is deprecated).
          * SSA contact assignments for ICs live in "{SCHEMA_NAME}"."ICSSAContact". It only stores the IC/resource UUIDs, so join to "{SCHEMA_NAME}"."ICRoster" for contractor names and "{SCHEMA_NAME}"."ConsolidatedResourceRoster" for SSA resource details.
          * There are no SSA contact name/email columns on "{SCHEMA_NAME}"."ICSSAContact"; pull that info from the joined tables instead.
          * When retrieving SSA contacts, always join "{SCHEMA_NAME}"."ICSSAContact".ic_id = "{SCHEMA_NAME}"."ICRoster".ic_id and "{SCHEMA_NAME}"."ICSSAContact".resource_id = "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id (both UUIDs). Never join these IDs to email columns.
          * SSA contacts are SSA internal resources; avoid "{SCHEMA_NAME}"."ClientContact" unless the question explicitly mentions client stakeholders.
          * Client contacts link to resources through "{SCHEMA_NAME}"."ClientContactResource" (IDs only; join out for people details).
      - To answer “who uses <tool>”:
          FirmTool → ResourceTool → ConsolidatedResourceRoster (optionally join ResourceCapability/FirmCapabilities for capability context).
      - To answer “who has <capability>”:
          ResourceCapability → (resource) ← ConsolidatedResourceRoster joined to FirmCapabilities.
      - Managing Directors: join ConsultantRoster → TitleMaster and filter TitleMaster.title ILIKE '%Managing Director%'.
    """,

    # === DATASET: engagements / projects ===
    "engagements": f"""
    Tables:
      - "{SCHEMA_NAME}"."ClientEngagement"(engagement_id, project_name, client_id, problem, approach, milestones_activities, recurring_impact_annual, one_time_impact, outcomes_impact, notes, case_study, start_date, status, end_date, capex_baseline, current_spend_baseline)
      - "{SCHEMA_NAME}"."Deliverable"(deliverable_id, engagement_id, name, description, deliverable_type, delivered_date, notes)
      - "{SCHEMA_NAME}"."ProjectTeam"(team_id, engagement_id, resource_id, project_role, start_date, end_date)
      - "{SCHEMA_NAME}"."ProjectReviewForm"(review_form_id, name, engagement_id, specific_expertise)
      - "{SCHEMA_NAME}"."ReviewFormResource"(review_form_id, resource_id)
      - "{SCHEMA_NAME}"."ReviewFormCapability"(review_form_id, capability_id)
      - "{SCHEMA_NAME}"."EngagementCapability"(engagement_id, capability_id)
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster"(resource_id, name, resource_type, role_rank, title_id)
      - "{SCHEMA_NAME}"."FirmCapabilities"(capability_id, capability_name)
      - "{SCHEMA_NAME}"."ClientList"(client_id, client_firm_name)

    Relationships:
      - "{SCHEMA_NAME}"."Deliverable".engagement_id → "{SCHEMA_NAME}"."ClientEngagement".engagement_id
      - "{SCHEMA_NAME}"."ProjectTeam".engagement_id → "{SCHEMA_NAME}"."ClientEngagement".engagement_id
      - "{SCHEMA_NAME}"."ProjectTeam".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ProjectReviewForm".engagement_id → "{SCHEMA_NAME}"."ClientEngagement".engagement_id
      - "{SCHEMA_NAME}"."ReviewFormResource".review_form_id → "{SCHEMA_NAME}"."ProjectReviewForm".review_form_id
      - "{SCHEMA_NAME}"."ReviewFormResource".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ReviewFormCapability".review_form_id → "{SCHEMA_NAME}"."ProjectReviewForm".review_form_id
      - "{SCHEMA_NAME}"."ReviewFormCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
      - "{SCHEMA_NAME}"."EngagementCapability".engagement_id → "{SCHEMA_NAME}"."ClientEngagement".engagement_id
      - "{SCHEMA_NAME}"."EngagementCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
      - "{SCHEMA_NAME}"."ClientEngagement".client_id → "{SCHEMA_NAME}"."ClientList".client_id

    Notes:
      - Join to ClientList for client_firm_name on engagement views.
      - Deliverables are in the separate "{SCHEMA_NAME}"."Deliverable" table (one-to-many). Join via engagement_id. Use ILIKE on name or deliverable_type to filter.
      - Use ILIKE for text filters and LIMIT 100 by default.
      - Baseline engagement finances: capex_baseline (capital expenditure) and current_spend_baseline (current spend).
    """,

    # === DATASET: training / learning ===
    "training": f"""
    Tables:
      - "{SCHEMA_NAME}"."TrainingLearning"(course_id, course_name, link_to_course, pre_requisites, learning_path, success_criteria)
      - "{SCHEMA_NAME}"."CourseResource"(course_id, resource_id)
      - "{SCHEMA_NAME}"."CourseCapability"(course_id, capability_id)
      - "{SCHEMA_NAME}"."CourseTool"(course_id, tool_id)
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster"(resource_id, name, role_rank, title_id)
      - "{SCHEMA_NAME}"."FirmCapabilities"(capability_id, capability_name)
      - "{SCHEMA_NAME}"."FirmTool"(tool_id, tool_name, vendor_name, tool_type, licensing, cost)

    Relationships:
      - "{SCHEMA_NAME}"."CourseResource".course_id → "{SCHEMA_NAME}"."TrainingLearning".course_id
      - "{SCHEMA_NAME}"."CourseResource".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."CourseCapability".course_id → "{SCHEMA_NAME}"."TrainingLearning".course_id
      - "{SCHEMA_NAME}"."CourseCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
      - "{SCHEMA_NAME}"."CourseTool".course_id → "{SCHEMA_NAME}"."TrainingLearning".course_id
      - "{SCHEMA_NAME}"."CourseTool".tool_id → "{SCHEMA_NAME}"."FirmTool".tool_id

    Notes:
      - Courses can be queried with their capabilities or tools via the junction tables above.
    """,
}
