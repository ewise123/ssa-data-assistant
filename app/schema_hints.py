# app/schema_hints.py

SCHEMA_NAME = "Project_Master_Database"  # your schema

SCHEMA_HINTS = {
    # === DATASET: clients ===
    "clients": f"""
    Tables (schema-qualified, quoted):
      - "{SCHEMA_NAME}"."ClientList"(client_id, client_firm_name, industry, field, geographic_presence, ownership_type, pe_firm_id)
      - "{SCHEMA_NAME}"."ClientContact"(contact_id, contact_name, role_to_ssa, organization, internal_role, email, client_id)
      - "{SCHEMA_NAME}"."ClientEngagement"(engagement_id, project_name, client_id, problem, approach, milestones_activities, deliverables, recurring_impact_annual, one_time_impact, outcomes_impact, notes, case_study, project_duration_weeks, start_date, status)
      - "{SCHEMA_NAME}"."EngagementContact"(engagement_id, contact_id)

    Relationships:
      - "{SCHEMA_NAME}"."ClientContact".client_id → "{SCHEMA_NAME}"."ClientList".client_id
      - "{SCHEMA_NAME}"."ClientEngagement".client_id → "{SCHEMA_NAME}"."ClientList".client_id
      - "{SCHEMA_NAME}"."EngagementContact".engagement_id → "{SCHEMA_NAME}"."ClientEngagement".engagement_id
      - "{SCHEMA_NAME}"."EngagementContact".contact_id → "{SCHEMA_NAME}"."ClientContact".contact_id
    """,

    # === DATASET: consultants ===
    "consultants": f"""
    Tables:
      - "{SCHEMA_NAME}"."ConsultantRoster"(consultant_id, name, title_id, email, phone_number)
      - "{SCHEMA_NAME}"."ICRoster"(ic_id, name, rate_daily, email, phone_number)
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster"(resource_id, name, resource_type, education, qualifications, previous_work_experience, role_rank, title_id)
      - "{SCHEMA_NAME}"."ConsultantIC"(consultant_id, ic_id)
      - "{SCHEMA_NAME}"."TitleMaster"(title_id, title)
      - "{SCHEMA_NAME}"."FirmCapabilities"(capability_id, capability_name)
      - "{SCHEMA_NAME}"."FirmTool"(tool_id, tool_name, vendor_name, tool_type, licensing, cost)
      - "{SCHEMA_NAME}"."ToolCapability"(tool_id, capability_id)
      - "{SCHEMA_NAME}"."ResourceCapability"(resource_id, capability_id)

    Relationships:
      - "{SCHEMA_NAME}"."ConsultantRoster".title_id → "{SCHEMA_NAME}"."TitleMaster".title_id
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster".title_id → "{SCHEMA_NAME}"."TitleMaster".title_id
      - "{SCHEMA_NAME}"."ConsultantIC".consultant_id → "{SCHEMA_NAME}"."ConsultantRoster".consultant_id
      - "{SCHEMA_NAME}"."ConsultantIC".ic_id → "{SCHEMA_NAME}"."ICRoster".ic_id
      - "{SCHEMA_NAME}"."ResourceCapability".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."ResourceCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
      - "{SCHEMA_NAME}"."ToolCapability".tool_id → "{SCHEMA_NAME}"."FirmTool".tool_id
      - "{SCHEMA_NAME}"."ToolCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
    """,

    # === DATASET: engagements (projects) ===
    "engagements": f"""
    Tables:
      - "{SCHEMA_NAME}"."ClientEngagement"(engagement_id, project_name, client_id, problem, approach, milestones_activities, deliverables, recurring_impact_annual, one_time_impact, outcomes_impact, notes, case_study, project_duration_weeks, start_date, status)
      - "{SCHEMA_NAME}"."ProjectTeam"(team_id, engagement_id, resource_id, project_role, start_date, end_date)
      - "{SCHEMA_NAME}"."ProjectReviewForm"(review_form_id, name, engagement_id, specific_expertise)
      - "{SCHEMA_NAME}"."ReviewFormResource"(review_form_id, resource_id)
      - "{SCHEMA_NAME}"."ReviewFormCapability"(review_form_id, capability_id)
      - "{SCHEMA_NAME}"."EngagementCapability"(engagement_id, capability_id)
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster"(resource_id, name, resource_type, education, qualifications, previous_work_experience, role_rank, title_id)
      - "{SCHEMA_NAME}"."FirmCapabilities"(capability_id, capability_name)
      - "{SCHEMA_NAME}"."ClientList"(client_id, client_firm_name)

    Relationships:
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
    """,

    # === DATASET: training ===
    "training": f"""
    Tables:
      - "{SCHEMA_NAME}"."TrainingLearning"(course_id, course_name, link_to_course, pre_requisites, learning_path, success_criteria)
      - "{SCHEMA_NAME}"."CourseResource"(course_id, resource_id)
      - "{SCHEMA_NAME}"."CourseCapability"(course_id, capability_id)
      - "{SCHEMA_NAME}"."CourseTool"(course_id, tool_id)
      - "{SCHEMA_NAME}"."ConsolidatedResourceRoster"(resource_id, name, resource_type, education, qualifications, previous_work_experience, role_rank, title_id)
      - "{SCHEMA_NAME}"."FirmCapabilities"(capability_id, capability_name)
      - "{SCHEMA_NAME}"."FirmTool"(tool_id, tool_name, vendor_name, tool_type, licensing, cost)

    Relationships:
      - "{SCHEMA_NAME}"."CourseResource".course_id → "{SCHEMA_NAME}"."TrainingLearning".course_id
      - "{SCHEMA_NAME}"."CourseResource".resource_id → "{SCHEMA_NAME}"."ConsolidatedResourceRoster".resource_id
      - "{SCHEMA_NAME}"."CourseCapability".course_id → "{SCHEMA_NAME}"."TrainingLearning".course_id
      - "{SCHEMA_NAME}"."CourseCapability".capability_id → "{SCHEMA_NAME}"."FirmCapabilities".capability_id
      - "{SCHEMA_NAME}"."CourseTool".course_id → "{SCHEMA_NAME}"."TrainingLearning".course_id
      - "{SCHEMA_NAME}"."CourseTool".tool_id → "{SCHEMA_NAME}"."FirmTool".tool_id
    """,
}
