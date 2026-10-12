-- Migration 0028: Custom Properties (Notion-style "database properties")
-- Adds two tables: property_definition (schema) and property_value (per-entity values).
-- Both are tenant-scoped via organization_id with cascade deletes.

CREATE TYPE "public"."property_entity_type" AS ENUM('candidate', 'application');--> statement-breakpoint
CREATE TYPE "public"."property_type" AS ENUM('text', 'long_text', 'number', 'select', 'multi_select', 'date', 'checkbox', 'url', 'email', 'person', 'file');--> statement-breakpoint
CREATE TABLE "property_definition" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"job_id" text,
	"entity_type" "property_entity_type" NOT NULL,
	"type" "property_type" NOT NULL,
	"name" text NOT NULL,
	"description" text,
	"display_order" integer DEFAULT 0 NOT NULL,
	"config" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "property_value" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"property_definition_id" text NOT NULL,
	"entity_type" "property_entity_type" NOT NULL,
	"entity_id" text NOT NULL,
	"value" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "property_definition" ADD CONSTRAINT "property_definition_organization_id_organization_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organization"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "property_definition" ADD CONSTRAINT "property_definition_job_id_job_id_fk" FOREIGN KEY ("job_id") REFERENCES "public"."job"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "property_value" ADD CONSTRAINT "property_value_organization_id_organization_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organization"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "property_value" ADD CONSTRAINT "property_value_property_definition_id_property_definition_id_fk" FOREIGN KEY ("property_definition_id") REFERENCES "public"."property_definition"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "property_definition_org_idx" ON "property_definition" USING btree ("organization_id");--> statement-breakpoint
CREATE INDEX "property_definition_org_entity_idx" ON "property_definition" USING btree ("organization_id","entity_type");--> statement-breakpoint
CREATE INDEX "property_definition_job_idx" ON "property_definition" USING btree ("job_id");--> statement-breakpoint
CREATE INDEX "property_value_org_idx" ON "property_value" USING btree ("organization_id");--> statement-breakpoint
CREATE INDEX "property_value_entity_idx" ON "property_value" USING btree ("entity_type","entity_id");--> statement-breakpoint
CREATE INDEX "property_value_definition_idx" ON "property_value" USING btree ("property_definition_id");--> statement-breakpoint
CREATE UNIQUE INDEX "property_value_def_entity_idx" ON "property_value" USING btree ("property_definition_id","entity_id");
