CREATE TYPE "public"."interview_status" AS ENUM('scheduled', 'completed', 'cancelled', 'no_show');--> statement-breakpoint
CREATE TYPE "public"."interview_type" AS ENUM('phone', 'video', 'in_person', 'panel', 'technical', 'take_home');--> statement-breakpoint
CREATE TABLE "interview" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"application_id" text NOT NULL,
	"title" text NOT NULL,
	"type" "interview_type" DEFAULT 'video' NOT NULL,
	"status" "interview_status" DEFAULT 'scheduled' NOT NULL,
	"scheduled_at" timestamp NOT NULL,
	"duration" integer DEFAULT 60 NOT NULL,
	"location" text,
	"notes" text,
	"interviewers" jsonb,
	"created_by_id" text NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "interview" ADD CONSTRAINT "interview_organization_id_organization_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organization"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "interview" ADD CONSTRAINT "interview_application_id_application_id_fk" FOREIGN KEY ("application_id") REFERENCES "public"."application"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "interview" ADD CONSTRAINT "interview_created_by_id_user_id_fk" FOREIGN KEY ("created_by_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "interview_organization_id_idx" ON "interview" USING btree ("organization_id");--> statement-breakpoint
CREATE INDEX "interview_application_id_idx" ON "interview" USING btree ("application_id");--> statement-breakpoint
CREATE INDEX "interview_scheduled_at_idx" ON "interview" USING btree ("scheduled_at");--> statement-breakpoint
CREATE INDEX "interview_status_idx" ON "interview" USING btree ("status");--> statement-breakpoint
CREATE INDEX "interview_created_by_id_idx" ON "interview" USING btree ("created_by_id");