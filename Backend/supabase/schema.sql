-- =====================================================================
-- AP Exception Handling Agent - Normalized Enterprise Schema
-- =====================================================================
-- Single source of truth for the relational persistence layer. This is
-- generated from the SQLAlchemy ORM (app/db/models.py) so it matches the
-- code EXACTLY, and mirrors the 9-table architecture in
-- docs/DATABASE_ARCHITECTURE.md (ERD in section 1).
--
-- Enum-valued columns are VARCHAR here (not native PG enums) on purpose: the
-- app stores the pipeline's own values (e.g. severity HIGH/MEDIUM/LOW,
-- resolution_path AUTO_APPROVE, ...), so VARCHAR avoids enum-value mismatches.
-- See DATABASE_ARCHITECTURE.md section 2 for an optional native-enum +
-- monthly-partition hardening variant.
--
-- Run in the Supabase SQL Editor, OR let the app create these automatically
-- (DB_PERSISTENCE_ENABLED=true -> init_db), OR: python -m scripts.init_db
-- =====================================================================


CREATE TABLE upload_batches (
	batch_id UUID NOT NULL, 
	tenant_id VARCHAR(128) NOT NULL, 
	file_name VARCHAR(512) NOT NULL, 
	source_file_hash VARCHAR(128), 
	total_records INTEGER NOT NULL, 
	processed_records INTEGER NOT NULL, 
	failed_records INTEGER NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	uploaded_by VARCHAR(256), 
	upload_time TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (batch_id)
);
CREATE INDEX ix_upload_batches_tenant_id ON upload_batches (tenant_id);

CREATE TABLE vendors (
	vendor_id UUID NOT NULL, 
	tenant_id VARCHAR(128) NOT NULL, 
	vendor_name VARCHAR(256) NOT NULL, 
	total_invoices_seen INTEGER NOT NULL, 
	total_amount_processed NUMERIC(16, 2) NOT NULL,
	reliability_score NUMERIC(4, 3),
	exception_type_counts JSON NOT NULL,
	-- Full VendorProfile snapshot (added by Alembic 42a0cabaea47). The DB-backed
	-- vendor store reads/writes this; the classifier prompt is enriched from it.
	profile JSONB NOT NULL DEFAULT '{}'::jsonb,
	first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (vendor_id),
	CONSTRAINT uq_vendor_tenant_name UNIQUE (tenant_id, vendor_name)
);
CREATE INDEX ix_vendors_tenant_id ON vendors (tenant_id);
CREATE INDEX ix_vendors_vendor_name ON vendors (vendor_name);

CREATE TABLE exceptions (
	exception_id UUID NOT NULL, 
	batch_id UUID NOT NULL, 
	vendor_id UUID, 
	tenant_id VARCHAR(128) NOT NULL, 
	invoice_id VARCHAR(64) NOT NULL, 
	vendor_name VARCHAR(256) NOT NULL, 
	invoice_amount NUMERIC(16, 2) NOT NULL, 
	po_number VARCHAR(64), 
	exception_type VARCHAR(64) NOT NULL, 
	exception_description TEXT NOT NULL, 
	days_outstanding INTEGER NOT NULL, 
	approver_assigned VARCHAR(256), 
	source_file_name VARCHAR(512), 
	uploaded_by VARCHAR(256), 
	upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	current_status VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (exception_id), 
	CONSTRAINT uq_exc_batch_invoice UNIQUE (batch_id, invoice_id), 
	FOREIGN KEY(batch_id) REFERENCES upload_batches (batch_id) ON DELETE CASCADE, 
	FOREIGN KEY(vendor_id) REFERENCES vendors (vendor_id) ON DELETE SET NULL
);
CREATE INDEX ix_exceptions_batch_id ON exceptions (batch_id);
CREATE INDEX ix_exceptions_tenant_id ON exceptions (tenant_id);
CREATE INDEX ix_exceptions_current_status ON exceptions (current_status);
CREATE INDEX ix_exceptions_vendor_id ON exceptions (vendor_id);
CREATE INDEX ix_exceptions_invoice_id ON exceptions (invoice_id);

CREATE TABLE agent_executions (
	execution_id UUID NOT NULL, 
	batch_id UUID, 
	exception_id UUID, 
	node_name VARCHAR(64) NOT NULL, 
	node_input JSON, 
	node_output JSON, 
	success_flag BOOLEAN NOT NULL, 
	error_message TEXT, 
	duration_ms INTEGER, 
	execution_timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (execution_id), 
	FOREIGN KEY(batch_id) REFERENCES upload_batches (batch_id) ON DELETE CASCADE, 
	FOREIGN KEY(exception_id) REFERENCES exceptions (exception_id) ON DELETE CASCADE
);
CREATE INDEX ix_agent_executions_exception_id ON agent_executions (exception_id);
CREATE INDEX ix_agent_executions_execution_timestamp ON agent_executions (execution_timestamp);
CREATE INDEX ix_agent_executions_batch_id ON agent_executions (batch_id);

CREATE TABLE classifications (
	classification_id UUID NOT NULL, 
	exception_id UUID NOT NULL, 
	primary_exception_type VARCHAR(64) NOT NULL, 
	root_cause_hypothesis TEXT NOT NULL, 
	confidence_score NUMERIC(4, 3) NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	severity_ai_suggested VARCHAR(16) NOT NULL, 
	ai_reasoning TEXT, 
	model_id VARCHAR(128), 
	prompt_version VARCHAR(64), 
	classified_timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (classification_id), 
	FOREIGN KEY(exception_id) REFERENCES exceptions (exception_id) ON DELETE CASCADE
);
CREATE INDEX ix_classifications_exception_id ON classifications (exception_id);

CREATE TABLE communications (
	email_id UUID NOT NULL, 
	exception_id UUID NOT NULL, 
	email_type VARCHAR(32) NOT NULL, 
	channel VARCHAR(32) NOT NULL, 
	recipient_email VARCHAR(320), 
	cc_email VARCHAR(320), 
	subject VARCHAR(512), 
	email_body TEXT NOT NULL, 
	template_id VARCHAR(128), 
	generated_by_ai BOOLEAN NOT NULL, 
	model_id VARCHAR(128), 
	sent_flag BOOLEAN NOT NULL, 
	sent_timestamp TIMESTAMP WITH TIME ZONE, 
	delivery_status VARCHAR(16) NOT NULL, 
	provider VARCHAR(64), 
	message_id VARCHAR(256), 
	error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (email_id), 
	FOREIGN KEY(exception_id) REFERENCES exceptions (exception_id) ON DELETE CASCADE
);
CREATE INDEX ix_communications_exception_id ON communications (exception_id);
CREATE INDEX ix_communications_delivery_status ON communications (delivery_status);

CREATE TABLE priorities (
	priority_id UUID NOT NULL, 
	exception_id UUID NOT NULL, 
	priority_score NUMERIC(5, 4) NOT NULL, 
	priority_bucket VARCHAR(16) NOT NULL, 
	ranking_position INTEGER, 
	drivers JSON NOT NULL, 
	last_priority_update TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (priority_id), 
	FOREIGN KEY(exception_id) REFERENCES exceptions (exception_id) ON DELETE CASCADE
);
CREATE INDEX ix_priorities_priority_bucket ON priorities (priority_bucket);
CREATE UNIQUE INDEX ix_priorities_exception_id ON priorities (exception_id);

CREATE TABLE resolutions (
	resolution_id UUID NOT NULL, 
	exception_id UUID NOT NULL, 
	resolution_path VARCHAR(48) NOT NULL, 
	assigned_team VARCHAR(128), 
	assigned_user VARCHAR(256), 
	resolution_status VARCHAR(32) NOT NULL, 
	rule_id VARCHAR(128), 
	rule_version VARCHAR(64), 
	sla_hours INTEGER, 
	requires_communication BOOLEAN NOT NULL, 
	resolution_notes TEXT, 
	resolved_date TIMESTAMP WITH TIME ZONE, 
	closed_date TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (resolution_id), 
	FOREIGN KEY(exception_id) REFERENCES exceptions (exception_id) ON DELETE CASCADE
);
CREATE INDEX ix_resolutions_exception_id ON resolutions (exception_id);
CREATE INDEX ix_resolutions_resolution_status ON resolutions (resolution_status);

CREATE TABLE status_history (
	history_id UUID NOT NULL, 
	exception_id UUID NOT NULL, 
	old_status VARCHAR(32), 
	new_status VARCHAR(32) NOT NULL, 
	changed_by VARCHAR(256) NOT NULL, 
	comments TEXT, 
	changed_timestamp TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (history_id), 
	FOREIGN KEY(exception_id) REFERENCES exceptions (exception_id) ON DELETE CASCADE
);
CREATE INDEX ix_status_history_exception_id ON status_history (exception_id);

-- Operational run store (app/api/db_store.py). One row per run: the full
-- serialized RunState as JSONB plus indexed scalar columns. The app creates
-- this automatically via init_db()/create_all; included here so schema.sql is
-- a complete source of truth.
CREATE TABLE IF NOT EXISTS runs (
	run_id VARCHAR(64) NOT NULL,
	tenant_id VARCHAR(128),
	status VARCHAR(32),
	current_node VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	rows_accepted INTEGER NOT NULL DEFAULT 0,
	rows_quarantined INTEGER NOT NULL DEFAULT 0,
	state JSONB NOT NULL,
	PRIMARY KEY (run_id)
);
CREATE INDEX IF NOT EXISTS ix_runs_tenant_id ON runs (tenant_id);
CREATE INDEX IF NOT EXISTS ix_runs_status ON runs (status);
CREATE INDEX IF NOT EXISTS ix_runs_created_at ON runs (created_at DESC);
