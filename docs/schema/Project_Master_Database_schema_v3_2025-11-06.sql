--
-- PostgreSQL database dump
--

\restrict zmv1dYAUo2JABbwv9fVL6Ci2whVusvJRVED4HjSkI9scIrmdXBYSIn2DaHFBLnB

-- Dumped from database version 15.13
-- Dumped by pg_dump version 18.0

-- Started on 2025-11-06 15:09:21

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 12 (class 2615 OID 41442134)
-- Name: Project_Master_Database; Type: SCHEMA; Schema: -; Owner: capostgresadmin
--

CREATE SCHEMA "Project_Master_Database";


ALTER SCHEMA "Project_Master_Database" OWNER TO capostgresadmin;

--
-- TOC entry 407 (class 1255 OID 41442135)
-- Name: uuid_v4(); Type: FUNCTION; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE FUNCTION "Project_Master_Database".uuid_v4() RETURNS uuid
    LANGUAGE sql
    AS $$
SELECT (
  lpad(to_hex((random()*2^32)::bigint),8,'0') || '-' ||
  lpad(to_hex((random()*2^16)::int),4,'0') || '-' ||
  '4' || right(lpad(to_hex((random()*2^16)::int),4,'0'),3) || '-' ||
  substr('89ab', (floor(random()*4)+1)::int, 1) ||
  right(lpad(to_hex((random()*2^16)::int),4,'0'),3) || '-' ||
  lpad(to_hex((random()*2^48)::bigint),12,'0')
)::uuid;
$$;


ALTER FUNCTION "Project_Master_Database".uuid_v4() OWNER TO capostgresadmin;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 380 (class 1259 OID 41442166)
-- Name: ClientContact; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ClientContact" (
    contact_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    contact_name text,
    role_to_ssa text,
    organization text,
    internal_role text,
    email text,
    client_id uuid,
    CONSTRAINT clientcontact_email_format_chk CHECK (((email IS NULL) OR (btrim(email) ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text)))
);


ALTER TABLE "Project_Master_Database"."ClientContact" OWNER TO capostgresadmin;

--
-- TOC entry 399 (class 1259 OID 41442428)
-- Name: ClientContactResource; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ClientContactResource" (
    contact_id uuid NOT NULL,
    resource_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."ClientContactResource" OWNER TO capostgresadmin;

--
-- TOC entry 381 (class 1259 OID 41442181)
-- Name: ClientEngagement; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ClientEngagement" (
    engagement_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    project_name text,
    client_id uuid,
    problem text,
    approach text,
    milestones_activities text,
    deliverables text,
    recurring_impact_annual numeric(12,2),
    one_time_impact numeric(12,2),
    outcomes_impact text,
    notes text,
    case_study text,
    start_date date,
    status text,
    end_date date,
    capex_baseline numeric(14,2),
    current_spend_baseline numeric(14,2),
    CONSTRAINT "ck_ClientEngagement_capex_baseline_nonneg" CHECK (((capex_baseline IS NULL) OR (capex_baseline >= (0)::numeric))),
    CONSTRAINT "ck_ClientEngagement_current_spend_baseline_nonneg" CHECK (((current_spend_baseline IS NULL) OR (current_spend_baseline >= (0)::numeric))),
    CONSTRAINT clientengagement_dates_chk CHECK (((end_date IS NULL) OR (start_date IS NULL) OR (end_date >= start_date)))
);


ALTER TABLE "Project_Master_Database"."ClientEngagement" OWNER TO capostgresadmin;

--
-- TOC entry 379 (class 1259 OID 41442152)
-- Name: ClientList; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ClientList" (
    client_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    client_firm_name text,
    industry text,
    field text,
    geographic_presence text,
    ownership_type text,
    pe_firm_id uuid
);


ALTER TABLE "Project_Master_Database"."ClientList" OWNER TO capostgresadmin;

--
-- TOC entry 382 (class 1259 OID 41442195)
-- Name: ConsolidatedResourceRoster; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ConsolidatedResourceRoster" (
    resource_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    name text,
    resource_type text,
    education text,
    qualifications text,
    previous_work_experience text,
    role_rank text,
    title_id uuid
);


ALTER TABLE "Project_Master_Database"."ConsolidatedResourceRoster" OWNER TO capostgresadmin;

--
-- TOC entry 383 (class 1259 OID 41442209)
-- Name: ConsultantRoster; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ConsultantRoster" (
    consultant_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    name text,
    title_id uuid,
    email text,
    phone_number text,
    CONSTRAINT consultantroster_email_format_chk CHECK (((email IS NULL) OR (btrim(email) ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text))),
    CONSTRAINT consultantroster_phone_format_chk CHECK (((phone_number IS NULL) OR (btrim(phone_number) ~ '^\([0-9]{3}\) [0-9]{3}-[0-9]{4}$'::text)))
);


ALTER TABLE "Project_Master_Database"."ConsultantRoster" OWNER TO capostgresadmin;

--
-- TOC entry 396 (class 1259 OID 41442383)
-- Name: CourseCapability; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."CourseCapability" (
    course_id uuid NOT NULL,
    capability_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."CourseCapability" OWNER TO capostgresadmin;

--
-- TOC entry 397 (class 1259 OID 41442398)
-- Name: CourseResource; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."CourseResource" (
    course_id uuid NOT NULL,
    resource_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."CourseResource" OWNER TO capostgresadmin;

--
-- TOC entry 395 (class 1259 OID 41442368)
-- Name: CourseTool; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."CourseTool" (
    course_id uuid NOT NULL,
    tool_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."CourseTool" OWNER TO capostgresadmin;

--
-- TOC entry 391 (class 1259 OID 41442308)
-- Name: EngagementCapability; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."EngagementCapability" (
    engagement_id uuid NOT NULL,
    capability_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."EngagementCapability" OWNER TO capostgresadmin;

--
-- TOC entry 390 (class 1259 OID 41442293)
-- Name: EngagementContact; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."EngagementContact" (
    engagement_id uuid NOT NULL,
    contact_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."EngagementContact" OWNER TO capostgresadmin;

--
-- TOC entry 385 (class 1259 OID 41442235)
-- Name: FirmCapabilities; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."FirmCapabilities" (
    capability_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    capability_name text
);


ALTER TABLE "Project_Master_Database"."FirmCapabilities" OWNER TO capostgresadmin;

--
-- TOC entry 386 (class 1259 OID 41442243)
-- Name: FirmTool; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."FirmTool" (
    tool_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    tool_name text,
    vendor_name text,
    tool_type text,
    licensing text,
    cost numeric(12,2)
);


ALTER TABLE "Project_Master_Database"."FirmTool" OWNER TO capostgresadmin;

--
-- TOC entry 384 (class 1259 OID 41442225)
-- Name: ICRoster; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ICRoster" (
    ic_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    name text,
    rate_daily numeric(12,2),
    email text,
    phone_number text,
    CONSTRAINT icroster_email_format_chk CHECK (((email IS NULL) OR (btrim(email) ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text))),
    CONSTRAINT icroster_phone_format_chk CHECK (((phone_number IS NULL) OR (btrim(phone_number) ~ '^\([0-9]{3}\) [0-9]{3}-[0-9]{4}$'::text)))
);


ALTER TABLE "Project_Master_Database"."ICRoster" OWNER TO capostgresadmin;

--
-- TOC entry 402 (class 1259 OID 41442514)
-- Name: ICSSAContact; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ICSSAContact" (
    ic_id uuid NOT NULL,
    resource_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."ICSSAContact" OWNER TO capostgresadmin;

--
-- TOC entry 377 (class 1259 OID 41442136)
-- Name: PERoster; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."PERoster" (
    pe_firm_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    pe_firm_name text,
    fund_size text
);


ALTER TABLE "Project_Master_Database"."PERoster" OWNER TO capostgresadmin;

--
-- TOC entry 388 (class 1259 OID 41442259)
-- Name: ProjectReviewForm; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ProjectReviewForm" (
    review_form_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    name text,
    engagement_id uuid,
    specific_expertise text
);


ALTER TABLE "Project_Master_Database"."ProjectReviewForm" OWNER TO capostgresadmin;

--
-- TOC entry 389 (class 1259 OID 41442273)
-- Name: ProjectTeam; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ProjectTeam" (
    team_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    engagement_id uuid,
    resource_id uuid,
    project_role text,
    start_date date,
    end_date date
);


ALTER TABLE "Project_Master_Database"."ProjectTeam" OWNER TO capostgresadmin;

--
-- TOC entry 398 (class 1259 OID 41442413)
-- Name: ResourceCapability; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ResourceCapability" (
    resource_id uuid NOT NULL,
    capability_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."ResourceCapability" OWNER TO capostgresadmin;

--
-- TOC entry 401 (class 1259 OID 41442497)
-- Name: ResourceIC; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ResourceIC" (
    resource_id uuid NOT NULL,
    ic_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."ResourceIC" OWNER TO capostgresadmin;

--
-- TOC entry 400 (class 1259 OID 41442479)
-- Name: ResourceTool; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ResourceTool" (
    resource_id uuid NOT NULL,
    tool_id uuid NOT NULL,
    proficiency_level text,
    last_validated date
);


ALTER TABLE "Project_Master_Database"."ResourceTool" OWNER TO capostgresadmin;

--
-- TOC entry 392 (class 1259 OID 41442323)
-- Name: ReviewFormCapability; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ReviewFormCapability" (
    review_form_id uuid NOT NULL,
    capability_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."ReviewFormCapability" OWNER TO capostgresadmin;

--
-- TOC entry 393 (class 1259 OID 41442338)
-- Name: ReviewFormResource; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ReviewFormResource" (
    review_form_id uuid NOT NULL,
    resource_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."ReviewFormResource" OWNER TO capostgresadmin;

--
-- TOC entry 378 (class 1259 OID 41442144)
-- Name: TitleMaster; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."TitleMaster" (
    title_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    title text
);


ALTER TABLE "Project_Master_Database"."TitleMaster" OWNER TO capostgresadmin;

--
-- TOC entry 394 (class 1259 OID 41442353)
-- Name: ToolCapability; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."ToolCapability" (
    tool_id uuid NOT NULL,
    capability_id uuid NOT NULL
);


ALTER TABLE "Project_Master_Database"."ToolCapability" OWNER TO capostgresadmin;

--
-- TOC entry 387 (class 1259 OID 41442251)
-- Name: TrainingLearning; Type: TABLE; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE TABLE "Project_Master_Database"."TrainingLearning" (
    course_id uuid DEFAULT "Project_Master_Database".uuid_v4() NOT NULL,
    course_name text,
    link_to_course text,
    pre_requisites text,
    learning_path text,
    success_criteria text
);


ALTER TABLE "Project_Master_Database"."TrainingLearning" OWNER TO capostgresadmin;

--
-- TOC entry 4327 (class 2606 OID 41442432)
-- Name: ClientContactResource ClientContactResource_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientContactResource"
    ADD CONSTRAINT "ClientContactResource_pkey" PRIMARY KEY (contact_id, resource_id);


--
-- TOC entry 4273 (class 2606 OID 41442174)
-- Name: ClientContact ClientContact_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientContact"
    ADD CONSTRAINT "ClientContact_pkey" PRIMARY KEY (contact_id);


--
-- TOC entry 4276 (class 2606 OID 41442188)
-- Name: ClientEngagement ClientEngagement_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientEngagement"
    ADD CONSTRAINT "ClientEngagement_pkey" PRIMARY KEY (engagement_id);


--
-- TOC entry 4270 (class 2606 OID 41442159)
-- Name: ClientList ClientList_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientList"
    ADD CONSTRAINT "ClientList_pkey" PRIMARY KEY (client_id);


--
-- TOC entry 4279 (class 2606 OID 41442202)
-- Name: ConsolidatedResourceRoster ConsolidatedResourceRoster_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ConsolidatedResourceRoster"
    ADD CONSTRAINT "ConsolidatedResourceRoster_pkey" PRIMARY KEY (resource_id);


--
-- TOC entry 4282 (class 2606 OID 41442218)
-- Name: ConsultantRoster ConsultantRoster_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ConsultantRoster"
    ADD CONSTRAINT "ConsultantRoster_pkey" PRIMARY KEY (consultant_id);


--
-- TOC entry 4318 (class 2606 OID 41442387)
-- Name: CourseCapability CourseCapability_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseCapability"
    ADD CONSTRAINT "CourseCapability_pkey" PRIMARY KEY (course_id, capability_id);


--
-- TOC entry 4321 (class 2606 OID 41442402)
-- Name: CourseResource CourseResource_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseResource"
    ADD CONSTRAINT "CourseResource_pkey" PRIMARY KEY (course_id, resource_id);


--
-- TOC entry 4315 (class 2606 OID 41442372)
-- Name: CourseTool CourseTool_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseTool"
    ADD CONSTRAINT "CourseTool_pkey" PRIMARY KEY (course_id, tool_id);


--
-- TOC entry 4303 (class 2606 OID 41442312)
-- Name: EngagementCapability EngagementCapability_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."EngagementCapability"
    ADD CONSTRAINT "EngagementCapability_pkey" PRIMARY KEY (engagement_id, capability_id);


--
-- TOC entry 4300 (class 2606 OID 41442297)
-- Name: EngagementContact EngagementContact_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."EngagementContact"
    ADD CONSTRAINT "EngagementContact_pkey" PRIMARY KEY (engagement_id, contact_id);


--
-- TOC entry 4287 (class 2606 OID 41442242)
-- Name: FirmCapabilities FirmCapabilities_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."FirmCapabilities"
    ADD CONSTRAINT "FirmCapabilities_pkey" PRIMARY KEY (capability_id);


--
-- TOC entry 4289 (class 2606 OID 41442250)
-- Name: FirmTool FirmTool_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."FirmTool"
    ADD CONSTRAINT "FirmTool_pkey" PRIMARY KEY (tool_id);


--
-- TOC entry 4285 (class 2606 OID 41442234)
-- Name: ICRoster ICRoster_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ICRoster"
    ADD CONSTRAINT "ICRoster_pkey" PRIMARY KEY (ic_id);


--
-- TOC entry 4336 (class 2606 OID 41442518)
-- Name: ICSSAContact ICSSAContact_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ICSSAContact"
    ADD CONSTRAINT "ICSSAContact_pkey" PRIMARY KEY (ic_id, resource_id);


--
-- TOC entry 4266 (class 2606 OID 41442143)
-- Name: PERoster PERoster_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."PERoster"
    ADD CONSTRAINT "PERoster_pkey" PRIMARY KEY (pe_firm_id);


--
-- TOC entry 4293 (class 2606 OID 41442266)
-- Name: ProjectReviewForm ProjectReviewForm_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ProjectReviewForm"
    ADD CONSTRAINT "ProjectReviewForm_pkey" PRIMARY KEY (review_form_id);


--
-- TOC entry 4296 (class 2606 OID 41442280)
-- Name: ProjectTeam ProjectTeam_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ProjectTeam"
    ADD CONSTRAINT "ProjectTeam_pkey" PRIMARY KEY (team_id);


--
-- TOC entry 4324 (class 2606 OID 41442417)
-- Name: ResourceCapability ResourceCapability_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceCapability"
    ADD CONSTRAINT "ResourceCapability_pkey" PRIMARY KEY (resource_id, capability_id);


--
-- TOC entry 4333 (class 2606 OID 41442501)
-- Name: ResourceIC ResourceIC_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceIC"
    ADD CONSTRAINT "ResourceIC_pkey" PRIMARY KEY (resource_id, ic_id);


--
-- TOC entry 4330 (class 2606 OID 41442485)
-- Name: ResourceTool ResourceTool_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceTool"
    ADD CONSTRAINT "ResourceTool_pkey" PRIMARY KEY (resource_id, tool_id);


--
-- TOC entry 4306 (class 2606 OID 41442327)
-- Name: ReviewFormCapability ReviewFormCapability_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ReviewFormCapability"
    ADD CONSTRAINT "ReviewFormCapability_pkey" PRIMARY KEY (review_form_id, capability_id);


--
-- TOC entry 4309 (class 2606 OID 41442342)
-- Name: ReviewFormResource ReviewFormResource_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ReviewFormResource"
    ADD CONSTRAINT "ReviewFormResource_pkey" PRIMARY KEY (review_form_id, resource_id);


--
-- TOC entry 4268 (class 2606 OID 41442151)
-- Name: TitleMaster TitleMaster_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."TitleMaster"
    ADD CONSTRAINT "TitleMaster_pkey" PRIMARY KEY (title_id);


--
-- TOC entry 4312 (class 2606 OID 41442357)
-- Name: ToolCapability ToolCapability_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ToolCapability"
    ADD CONSTRAINT "ToolCapability_pkey" PRIMARY KEY (tool_id, capability_id);


--
-- TOC entry 4291 (class 2606 OID 41442258)
-- Name: TrainingLearning TrainingLearning_pkey; Type: CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."TrainingLearning"
    ADD CONSTRAINT "TrainingLearning_pkey" PRIMARY KEY (course_id);


--
-- TOC entry 4274 (class 1259 OID 41442180)
-- Name: idx_clientcontact_client_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_clientcontact_client_id ON "Project_Master_Database"."ClientContact" USING btree (client_id);


--
-- TOC entry 4328 (class 1259 OID 41442467)
-- Name: idx_clientcontactresource_resource_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_clientcontactresource_resource_id ON "Project_Master_Database"."ClientContactResource" USING btree (resource_id);


--
-- TOC entry 4277 (class 1259 OID 41442194)
-- Name: idx_clientengagement_client_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_clientengagement_client_id ON "Project_Master_Database"."ClientEngagement" USING btree (client_id);


--
-- TOC entry 4271 (class 1259 OID 41442165)
-- Name: idx_clientlist_pe_firm_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_clientlist_pe_firm_id ON "Project_Master_Database"."ClientList" USING btree (pe_firm_id);


--
-- TOC entry 4280 (class 1259 OID 41442208)
-- Name: idx_consolidatedresource_title_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_consolidatedresource_title_id ON "Project_Master_Database"."ConsolidatedResourceRoster" USING btree (title_id);


--
-- TOC entry 4283 (class 1259 OID 41442224)
-- Name: idx_consultantroster_title_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_consultantroster_title_id ON "Project_Master_Database"."ConsultantRoster" USING btree (title_id);


--
-- TOC entry 4319 (class 1259 OID 41442464)
-- Name: idx_coursecapability_capability_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_coursecapability_capability_id ON "Project_Master_Database"."CourseCapability" USING btree (capability_id);


--
-- TOC entry 4322 (class 1259 OID 41442465)
-- Name: idx_courseresource_resource_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_courseresource_resource_id ON "Project_Master_Database"."CourseResource" USING btree (resource_id);


--
-- TOC entry 4316 (class 1259 OID 41442463)
-- Name: idx_coursetool_tool_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_coursetool_tool_id ON "Project_Master_Database"."CourseTool" USING btree (tool_id);


--
-- TOC entry 4304 (class 1259 OID 41442459)
-- Name: idx_engagementcapability_capability_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_engagementcapability_capability_id ON "Project_Master_Database"."EngagementCapability" USING btree (capability_id);


--
-- TOC entry 4301 (class 1259 OID 41442458)
-- Name: idx_engagementcontact_contact_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_engagementcontact_contact_id ON "Project_Master_Database"."EngagementContact" USING btree (contact_id);


--
-- TOC entry 4337 (class 1259 OID 41442529)
-- Name: idx_icssacontact_resource_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_icssacontact_resource_id ON "Project_Master_Database"."ICSSAContact" USING btree (resource_id);


--
-- TOC entry 4294 (class 1259 OID 41442272)
-- Name: idx_projectreviewform_engagement_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_projectreviewform_engagement_id ON "Project_Master_Database"."ProjectReviewForm" USING btree (engagement_id);


--
-- TOC entry 4297 (class 1259 OID 41442291)
-- Name: idx_projectteam_engagement_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_projectteam_engagement_id ON "Project_Master_Database"."ProjectTeam" USING btree (engagement_id);


--
-- TOC entry 4298 (class 1259 OID 41442292)
-- Name: idx_projectteam_resource_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_projectteam_resource_id ON "Project_Master_Database"."ProjectTeam" USING btree (resource_id);


--
-- TOC entry 4325 (class 1259 OID 41442466)
-- Name: idx_resourcecapability_capability_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_resourcecapability_capability_id ON "Project_Master_Database"."ResourceCapability" USING btree (capability_id);


--
-- TOC entry 4334 (class 1259 OID 41442512)
-- Name: idx_resourceic_ic_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_resourceic_ic_id ON "Project_Master_Database"."ResourceIC" USING btree (ic_id);


--
-- TOC entry 4331 (class 1259 OID 41442496)
-- Name: idx_resourcetool_tool_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_resourcetool_tool_id ON "Project_Master_Database"."ResourceTool" USING btree (tool_id);


--
-- TOC entry 4307 (class 1259 OID 41442460)
-- Name: idx_reviewformcapability_capability_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_reviewformcapability_capability_id ON "Project_Master_Database"."ReviewFormCapability" USING btree (capability_id);


--
-- TOC entry 4310 (class 1259 OID 41442461)
-- Name: idx_reviewformresource_resource_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_reviewformresource_resource_id ON "Project_Master_Database"."ReviewFormResource" USING btree (resource_id);


--
-- TOC entry 4313 (class 1259 OID 41442462)
-- Name: idx_toolcapability_capability_id; Type: INDEX; Schema: Project_Master_Database; Owner: capostgresadmin
--

CREATE INDEX idx_toolcapability_capability_id ON "Project_Master_Database"."ToolCapability" USING btree (capability_id);


--
-- TOC entry 4364 (class 2606 OID 41442433)
-- Name: ClientContactResource ClientContactResource_contact_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientContactResource"
    ADD CONSTRAINT "ClientContactResource_contact_id_fkey" FOREIGN KEY (contact_id) REFERENCES "Project_Master_Database"."ClientContact"(contact_id) ON DELETE CASCADE;


--
-- TOC entry 4365 (class 2606 OID 41442438)
-- Name: ClientContactResource ClientContactResource_resource_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientContactResource"
    ADD CONSTRAINT "ClientContactResource_resource_id_fkey" FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id) ON DELETE CASCADE;


--
-- TOC entry 4339 (class 2606 OID 41442175)
-- Name: ClientContact ClientContact_client_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientContact"
    ADD CONSTRAINT "ClientContact_client_id_fkey" FOREIGN KEY (client_id) REFERENCES "Project_Master_Database"."ClientList"(client_id);


--
-- TOC entry 4340 (class 2606 OID 41442189)
-- Name: ClientEngagement ClientEngagement_client_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientEngagement"
    ADD CONSTRAINT "ClientEngagement_client_id_fkey" FOREIGN KEY (client_id) REFERENCES "Project_Master_Database"."ClientList"(client_id);


--
-- TOC entry 4338 (class 2606 OID 41442160)
-- Name: ClientList ClientList_pe_firm_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ClientList"
    ADD CONSTRAINT "ClientList_pe_firm_id_fkey" FOREIGN KEY (pe_firm_id) REFERENCES "Project_Master_Database"."PERoster"(pe_firm_id);


--
-- TOC entry 4341 (class 2606 OID 41442203)
-- Name: ConsolidatedResourceRoster ConsolidatedResourceRoster_title_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ConsolidatedResourceRoster"
    ADD CONSTRAINT "ConsolidatedResourceRoster_title_id_fkey" FOREIGN KEY (title_id) REFERENCES "Project_Master_Database"."TitleMaster"(title_id);


--
-- TOC entry 4342 (class 2606 OID 41442219)
-- Name: ConsultantRoster ConsultantRoster_title_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ConsultantRoster"
    ADD CONSTRAINT "ConsultantRoster_title_id_fkey" FOREIGN KEY (title_id) REFERENCES "Project_Master_Database"."TitleMaster"(title_id);


--
-- TOC entry 4358 (class 2606 OID 41442393)
-- Name: CourseCapability CourseCapability_capability_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseCapability"
    ADD CONSTRAINT "CourseCapability_capability_id_fkey" FOREIGN KEY (capability_id) REFERENCES "Project_Master_Database"."FirmCapabilities"(capability_id) ON DELETE CASCADE;


--
-- TOC entry 4359 (class 2606 OID 41442388)
-- Name: CourseCapability CourseCapability_course_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseCapability"
    ADD CONSTRAINT "CourseCapability_course_id_fkey" FOREIGN KEY (course_id) REFERENCES "Project_Master_Database"."TrainingLearning"(course_id) ON DELETE CASCADE;


--
-- TOC entry 4360 (class 2606 OID 41442403)
-- Name: CourseResource CourseResource_course_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseResource"
    ADD CONSTRAINT "CourseResource_course_id_fkey" FOREIGN KEY (course_id) REFERENCES "Project_Master_Database"."TrainingLearning"(course_id) ON DELETE CASCADE;


--
-- TOC entry 4361 (class 2606 OID 41442408)
-- Name: CourseResource CourseResource_resource_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseResource"
    ADD CONSTRAINT "CourseResource_resource_id_fkey" FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id) ON DELETE CASCADE;


--
-- TOC entry 4356 (class 2606 OID 41442373)
-- Name: CourseTool CourseTool_course_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseTool"
    ADD CONSTRAINT "CourseTool_course_id_fkey" FOREIGN KEY (course_id) REFERENCES "Project_Master_Database"."TrainingLearning"(course_id) ON DELETE CASCADE;


--
-- TOC entry 4357 (class 2606 OID 41442378)
-- Name: CourseTool CourseTool_tool_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."CourseTool"
    ADD CONSTRAINT "CourseTool_tool_id_fkey" FOREIGN KEY (tool_id) REFERENCES "Project_Master_Database"."FirmTool"(tool_id) ON DELETE CASCADE;


--
-- TOC entry 4348 (class 2606 OID 41442318)
-- Name: EngagementCapability EngagementCapability_capability_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."EngagementCapability"
    ADD CONSTRAINT "EngagementCapability_capability_id_fkey" FOREIGN KEY (capability_id) REFERENCES "Project_Master_Database"."FirmCapabilities"(capability_id) ON DELETE CASCADE;


--
-- TOC entry 4349 (class 2606 OID 41442313)
-- Name: EngagementCapability EngagementCapability_engagement_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."EngagementCapability"
    ADD CONSTRAINT "EngagementCapability_engagement_id_fkey" FOREIGN KEY (engagement_id) REFERENCES "Project_Master_Database"."ClientEngagement"(engagement_id) ON DELETE CASCADE;


--
-- TOC entry 4346 (class 2606 OID 41442303)
-- Name: EngagementContact EngagementContact_contact_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."EngagementContact"
    ADD CONSTRAINT "EngagementContact_contact_id_fkey" FOREIGN KEY (contact_id) REFERENCES "Project_Master_Database"."ClientContact"(contact_id) ON DELETE CASCADE;


--
-- TOC entry 4347 (class 2606 OID 41442298)
-- Name: EngagementContact EngagementContact_engagement_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."EngagementContact"
    ADD CONSTRAINT "EngagementContact_engagement_id_fkey" FOREIGN KEY (engagement_id) REFERENCES "Project_Master_Database"."ClientEngagement"(engagement_id) ON DELETE CASCADE;


--
-- TOC entry 4370 (class 2606 OID 41442519)
-- Name: ICSSAContact ICSSAContact_ic_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ICSSAContact"
    ADD CONSTRAINT "ICSSAContact_ic_id_fkey" FOREIGN KEY (ic_id) REFERENCES "Project_Master_Database"."ICRoster"(ic_id) ON DELETE CASCADE;


--
-- TOC entry 4371 (class 2606 OID 41442524)
-- Name: ICSSAContact ICSSAContact_resource_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ICSSAContact"
    ADD CONSTRAINT "ICSSAContact_resource_id_fkey" FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id) ON DELETE CASCADE;


--
-- TOC entry 4343 (class 2606 OID 41442267)
-- Name: ProjectReviewForm ProjectReviewForm_engagement_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ProjectReviewForm"
    ADD CONSTRAINT "ProjectReviewForm_engagement_id_fkey" FOREIGN KEY (engagement_id) REFERENCES "Project_Master_Database"."ClientEngagement"(engagement_id);


--
-- TOC entry 4344 (class 2606 OID 41442281)
-- Name: ProjectTeam ProjectTeam_engagement_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ProjectTeam"
    ADD CONSTRAINT "ProjectTeam_engagement_id_fkey" FOREIGN KEY (engagement_id) REFERENCES "Project_Master_Database"."ClientEngagement"(engagement_id);


--
-- TOC entry 4345 (class 2606 OID 41442286)
-- Name: ProjectTeam ProjectTeam_resource_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ProjectTeam"
    ADD CONSTRAINT "ProjectTeam_resource_id_fkey" FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id);


--
-- TOC entry 4362 (class 2606 OID 41442423)
-- Name: ResourceCapability ResourceCapability_capability_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceCapability"
    ADD CONSTRAINT "ResourceCapability_capability_id_fkey" FOREIGN KEY (capability_id) REFERENCES "Project_Master_Database"."FirmCapabilities"(capability_id) ON DELETE CASCADE;


--
-- TOC entry 4363 (class 2606 OID 41442418)
-- Name: ResourceCapability ResourceCapability_resource_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceCapability"
    ADD CONSTRAINT "ResourceCapability_resource_id_fkey" FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id) ON DELETE CASCADE;


--
-- TOC entry 4350 (class 2606 OID 41442333)
-- Name: ReviewFormCapability ReviewFormCapability_capability_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ReviewFormCapability"
    ADD CONSTRAINT "ReviewFormCapability_capability_id_fkey" FOREIGN KEY (capability_id) REFERENCES "Project_Master_Database"."FirmCapabilities"(capability_id) ON DELETE CASCADE;


--
-- TOC entry 4351 (class 2606 OID 41442328)
-- Name: ReviewFormCapability ReviewFormCapability_review_form_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ReviewFormCapability"
    ADD CONSTRAINT "ReviewFormCapability_review_form_id_fkey" FOREIGN KEY (review_form_id) REFERENCES "Project_Master_Database"."ProjectReviewForm"(review_form_id) ON DELETE CASCADE;


--
-- TOC entry 4352 (class 2606 OID 41442348)
-- Name: ReviewFormResource ReviewFormResource_resource_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ReviewFormResource"
    ADD CONSTRAINT "ReviewFormResource_resource_id_fkey" FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id) ON DELETE CASCADE;


--
-- TOC entry 4353 (class 2606 OID 41442343)
-- Name: ReviewFormResource ReviewFormResource_review_form_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ReviewFormResource"
    ADD CONSTRAINT "ReviewFormResource_review_form_id_fkey" FOREIGN KEY (review_form_id) REFERENCES "Project_Master_Database"."ProjectReviewForm"(review_form_id) ON DELETE CASCADE;


--
-- TOC entry 4354 (class 2606 OID 41442363)
-- Name: ToolCapability ToolCapability_capability_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ToolCapability"
    ADD CONSTRAINT "ToolCapability_capability_id_fkey" FOREIGN KEY (capability_id) REFERENCES "Project_Master_Database"."FirmCapabilities"(capability_id) ON DELETE CASCADE;


--
-- TOC entry 4355 (class 2606 OID 41442358)
-- Name: ToolCapability ToolCapability_tool_id_fkey; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ToolCapability"
    ADD CONSTRAINT "ToolCapability_tool_id_fkey" FOREIGN KEY (tool_id) REFERENCES "Project_Master_Database"."FirmTool"(tool_id) ON DELETE CASCADE;


--
-- TOC entry 4368 (class 2606 OID 41442507)
-- Name: ResourceIC resourceic_ic_fk; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceIC"
    ADD CONSTRAINT resourceic_ic_fk FOREIGN KEY (ic_id) REFERENCES "Project_Master_Database"."ICRoster"(ic_id) ON DELETE CASCADE;


--
-- TOC entry 4369 (class 2606 OID 41442502)
-- Name: ResourceIC resourceic_resource_fk; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceIC"
    ADD CONSTRAINT resourceic_resource_fk FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id) ON DELETE CASCADE;


--
-- TOC entry 4366 (class 2606 OID 41442486)
-- Name: ResourceTool resourcetool_resource_fk; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceTool"
    ADD CONSTRAINT resourcetool_resource_fk FOREIGN KEY (resource_id) REFERENCES "Project_Master_Database"."ConsolidatedResourceRoster"(resource_id) ON DELETE CASCADE;


--
-- TOC entry 4367 (class 2606 OID 41442491)
-- Name: ResourceTool resourcetool_tool_fk; Type: FK CONSTRAINT; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER TABLE ONLY "Project_Master_Database"."ResourceTool"
    ADD CONSTRAINT resourcetool_tool_fk FOREIGN KEY (tool_id) REFERENCES "Project_Master_Database"."FirmTool"(tool_id) ON DELETE CASCADE;


--
-- TOC entry 4530 (class 0 OID 0)
-- Dependencies: 12
-- Name: SCHEMA "Project_Master_Database"; Type: ACL; Schema: -; Owner: capostgresadmin
--

GRANT USAGE ON SCHEMA "Project_Master_Database" TO chat_reader;


--
-- TOC entry 4531 (class 0 OID 0)
-- Dependencies: 380
-- Name: TABLE "ClientContact"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ClientContact" TO chat_reader;


--
-- TOC entry 4532 (class 0 OID 0)
-- Dependencies: 399
-- Name: TABLE "ClientContactResource"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ClientContactResource" TO chat_reader;


--
-- TOC entry 4533 (class 0 OID 0)
-- Dependencies: 381
-- Name: TABLE "ClientEngagement"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ClientEngagement" TO chat_reader;


--
-- TOC entry 4534 (class 0 OID 0)
-- Dependencies: 379
-- Name: TABLE "ClientList"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ClientList" TO chat_reader;


--
-- TOC entry 4535 (class 0 OID 0)
-- Dependencies: 382
-- Name: TABLE "ConsolidatedResourceRoster"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ConsolidatedResourceRoster" TO chat_reader;


--
-- TOC entry 4536 (class 0 OID 0)
-- Dependencies: 383
-- Name: TABLE "ConsultantRoster"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ConsultantRoster" TO chat_reader;


--
-- TOC entry 4537 (class 0 OID 0)
-- Dependencies: 396
-- Name: TABLE "CourseCapability"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."CourseCapability" TO chat_reader;


--
-- TOC entry 4538 (class 0 OID 0)
-- Dependencies: 397
-- Name: TABLE "CourseResource"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."CourseResource" TO chat_reader;


--
-- TOC entry 4539 (class 0 OID 0)
-- Dependencies: 395
-- Name: TABLE "CourseTool"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."CourseTool" TO chat_reader;


--
-- TOC entry 4540 (class 0 OID 0)
-- Dependencies: 391
-- Name: TABLE "EngagementCapability"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."EngagementCapability" TO chat_reader;


--
-- TOC entry 4541 (class 0 OID 0)
-- Dependencies: 390
-- Name: TABLE "EngagementContact"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."EngagementContact" TO chat_reader;


--
-- TOC entry 4542 (class 0 OID 0)
-- Dependencies: 385
-- Name: TABLE "FirmCapabilities"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."FirmCapabilities" TO chat_reader;


--
-- TOC entry 4543 (class 0 OID 0)
-- Dependencies: 386
-- Name: TABLE "FirmTool"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."FirmTool" TO chat_reader;


--
-- TOC entry 4544 (class 0 OID 0)
-- Dependencies: 384
-- Name: TABLE "ICRoster"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ICRoster" TO chat_reader;


--
-- TOC entry 4545 (class 0 OID 0)
-- Dependencies: 402
-- Name: TABLE "ICSSAContact"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ICSSAContact" TO chat_reader;


--
-- TOC entry 4546 (class 0 OID 0)
-- Dependencies: 377
-- Name: TABLE "PERoster"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."PERoster" TO chat_reader;


--
-- TOC entry 4547 (class 0 OID 0)
-- Dependencies: 388
-- Name: TABLE "ProjectReviewForm"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ProjectReviewForm" TO chat_reader;


--
-- TOC entry 4548 (class 0 OID 0)
-- Dependencies: 389
-- Name: TABLE "ProjectTeam"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ProjectTeam" TO chat_reader;


--
-- TOC entry 4549 (class 0 OID 0)
-- Dependencies: 398
-- Name: TABLE "ResourceCapability"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ResourceCapability" TO chat_reader;


--
-- TOC entry 4550 (class 0 OID 0)
-- Dependencies: 401
-- Name: TABLE "ResourceIC"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ResourceIC" TO chat_reader;


--
-- TOC entry 4551 (class 0 OID 0)
-- Dependencies: 400
-- Name: TABLE "ResourceTool"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ResourceTool" TO chat_reader;


--
-- TOC entry 4552 (class 0 OID 0)
-- Dependencies: 392
-- Name: TABLE "ReviewFormCapability"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ReviewFormCapability" TO chat_reader;


--
-- TOC entry 4553 (class 0 OID 0)
-- Dependencies: 393
-- Name: TABLE "ReviewFormResource"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ReviewFormResource" TO chat_reader;


--
-- TOC entry 4554 (class 0 OID 0)
-- Dependencies: 378
-- Name: TABLE "TitleMaster"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."TitleMaster" TO chat_reader;


--
-- TOC entry 4555 (class 0 OID 0)
-- Dependencies: 394
-- Name: TABLE "ToolCapability"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."ToolCapability" TO chat_reader;


--
-- TOC entry 4556 (class 0 OID 0)
-- Dependencies: 387
-- Name: TABLE "TrainingLearning"; Type: ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

GRANT SELECT ON TABLE "Project_Master_Database"."TrainingLearning" TO chat_reader;


--
-- TOC entry 2517 (class 826 OID 41442478)
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: Project_Master_Database; Owner: capostgresadmin
--

ALTER DEFAULT PRIVILEGES FOR ROLE capostgresadmin IN SCHEMA "Project_Master_Database" GRANT SELECT ON TABLES TO chat_reader;


-- Completed on 2025-11-06 15:09:23

--
-- PostgreSQL database dump complete
--

\unrestrict zmv1dYAUo2JABbwv9fVL6Ci2whVusvJRVED4HjSkI9scIrmdXBYSIn2DaHFBLnB

