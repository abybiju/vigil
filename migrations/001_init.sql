-- Vigil schema (SQLite). Adapted from the Postgres design in vigil_build_spec.md §3.
-- Conventions: uuid -> TEXT (uuid4 from app code); timestamptz/date -> TEXT ISO-8601;
-- jsonb -> TEXT (json); boolean -> INTEGER 0/1. FKs require `PRAGMA foreign_keys=ON`.

-- Raw inbound, PII already masked before it is stored or sent to a model.
create table if not exists messages (
  id            text primary key,
  source        text,                 -- email | chat | review
  channel       text,
  received_at   text,
  customer_ref  text,                 -- masked / hashed
  order_ref     text,                 -- nullable
  journey_stage text,                 -- pre_kit | post_impression | preview_approved | in_treatment | post_treatment | unknown
  raw_text      text not null
);

-- One triage decision per message.
create table if not exists cases (
  id                text primary key,
  message_id        text references messages(id),
  intent_category   text,             -- json array of intents
  is_complaint      integer,
  complaint_basis   text,             -- safety | performance | durability | quality | none
  clinical_red_flag integer,
  severity          text,             -- none | minor | moderate | serious
  potential_mdr     integer,
  mdr_rationale     text,
  conf_complaint    real,
  conf_clinical     real,
  conf_mdr          real,
  routing_decision  text,             -- auto_send | agent_draft | clinical_review | vigilance_review
  routing_reason    text,
  status            text default 'open',
  model_version     text,
  prompt_version    text,
  created_at        text
);

-- Structured extraction for the messages that ARE complaints.
create table if not exists complaint_records (
  id                text primary key,
  case_id           text references cases(id),
  device            text,             -- day_aligner | night_aligner | retainer | impression_kit
  issue_type        text,
  onset             text,
  duration          text,
  alleged_harm      text,
  body_site         text,             -- tooth | gum | bite | other
  patient_narrative text,
  event_date        text,
  aligner_step      text,
  photo_requested   integer default 0
);

-- MedWatch 3500A-style draft for MDR candidates (human reviews before anything leaves).
create table if not exists mdr_drafts (
  id                  text primary key,
  complaint_record_id text references complaint_records(id),
  event_type          text,           -- malfunction | injury | death
  device_problem      text,
  patient_problem     text,
  narrative           text,
  draft_status        text default 'pending_review'
);

-- Everything is auditable (a selling point for a regulated buyer).
create table if not exists audit_log (
  id         text primary key,
  case_id    text references cases(id),
  actor      text,                     -- ai | human
  action     text,
  detail     text,                     -- json
  created_at text
);

-- Gold labels for the eval harness.
create table if not exists eval_labels (
  message_id             text references messages(id),
  gold_is_complaint      integer,
  gold_clinical_red_flag integer,
  gold_potential_mdr     integer,
  gold_severity          text,
  bucket                 text,
  notes                  text
);

-- FAQ/policy corpus + vectors for grounded retrieval (citation source).
create table if not exists faq_chunks (
  id           text primary key,
  source_title text,
  source_url   text,
  chunk_index  integer,
  content      text not null,
  vector       text                    -- json-encoded float array
);

-- Cache of raw model outputs so re-running the eval report is free.
create table if not exists model_cache (
  cache_key     text primary key,
  kind          text,                  -- triage | clinical_safety
  response_json text,
  created_at    text
);

-- Grounded safe-lane reply drafts (one per message; only for non-clinical lanes).
create table if not exists replies (
  message_id   text primary key references messages(id),
  body         text,
  source_title text,
  source_url   text,
  grounded     integer default 0,
  created_at   text
);

create index if not exists idx_cases_message on cases(message_id);
create index if not exists idx_cr_case       on complaint_records(case_id);
create index if not exists idx_mdr_cr        on mdr_drafts(complaint_record_id);
create index if not exists idx_audit_case    on audit_log(case_id);
create index if not exists idx_eval_message  on eval_labels(message_id);
create index if not exists idx_faq_idx       on faq_chunks(chunk_index);
