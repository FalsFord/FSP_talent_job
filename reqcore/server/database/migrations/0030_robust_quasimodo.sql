CREATE TYPE "public"."retention_audit_action" AS ENUM('quarantined', 'restored', 'erased', 'exempted', 'unexempted', 'exported');--> statement-breakpoint
CREATE TABLE "retention_audit" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"candidate_id" text NOT NULL,
	"action" "retention_audit_action" NOT NULL,
	"result" text DEFAULT 'success' NOT NULL,
	"actor_id" text,
	"metadata" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "candidate" ADD COLUMN "retention_exempt_until" timestamp;--> statement-breakpoint
ALTER TABLE "candidate" ADD COLUMN "retention_exempt_reason" text;--> statement-breakpoint
ALTER TABLE "candidate" ADD COLUMN "quarantined_at" timestamp;--> statement-breakpoint
ALTER TABLE "candidate" ADD COLUMN "scheduled_purge_at" timestamp;--> statement-breakpoint
ALTER TABLE "org_settings" ADD COLUMN "retention_enabled" boolean DEFAULT false NOT NULL;--> statement-breakpoint
ALTER TABLE "org_settings" ADD COLUMN "retention_months" integer DEFAULT 24 NOT NULL;--> statement-breakpoint
ALTER TABLE "org_settings" ADD COLUMN "quarantine_days" integer DEFAULT 30 NOT NULL;--> statement-breakpoint
ALTER TABLE "org_settings" ADD COLUMN "retention_activated_at" timestamp;--> statement-breakpoint
ALTER TABLE "org_settings" ADD COLUMN "privacy_policy_url" text;--> statement-breakpoint
ALTER TABLE "org_settings" ADD COLUMN "privacy_policy_text" text;--> statement-breakpoint
ALTER TABLE "org_settings" ADD COLUMN "privacy_contact_email" text;--> statement-breakpoint
ALTER TABLE "retention_audit" ADD CONSTRAINT "retention_audit_organization_id_organization_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organization"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "retention_audit_organization_id_idx" ON "retention_audit" USING btree ("organization_id");--> statement-breakpoint
CREATE INDEX "retention_audit_candidate_id_idx" ON "retention_audit" USING btree ("candidate_id");--> statement-breakpoint
CREATE INDEX "retention_audit_created_at_idx" ON "retention_audit" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "candidate_quarantine_idx" ON "candidate" USING btree ("organization_id","scheduled_purge_at");