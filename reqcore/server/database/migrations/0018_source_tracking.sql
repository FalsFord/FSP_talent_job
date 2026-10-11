CREATE TYPE "public"."source_channel" AS ENUM('linkedin', 'indeed', 'glassdoor', 'ziprecruiter', 'monster', 'handshake', 'angellist', 'wellfound', 'dice', 'stackoverflow', 'weworkremotely', 'remoteok', 'builtin', 'hired', 'lever', 'greenhouse_board', 'google_jobs', 'facebook', 'twitter', 'instagram', 'tiktok', 'reddit', 'referral', 'career_site', 'email', 'event', 'agency', 'direct', 'other', 'custom');--> statement-breakpoint
CREATE TABLE "application_source" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"application_id" text NOT NULL,
	"channel" "source_channel" DEFAULT 'direct' NOT NULL,
	"tracking_link_id" text,
	"utm_source" text,
	"utm_medium" text,
	"utm_campaign" text,
	"utm_term" text,
	"utm_content" text,
	"referrer_domain" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "tracking_link" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"job_id" text,
	"channel" "source_channel" DEFAULT 'custom' NOT NULL,
	"name" text NOT NULL,
	"code" text NOT NULL,
	"utm_source" text,
	"utm_medium" text,
	"utm_campaign" text,
	"utm_term" text,
	"utm_content" text,
	"click_count" integer DEFAULT 0 NOT NULL,
	"application_count" integer DEFAULT 0 NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"created_by_id" text NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "tracking_link_code_unique" UNIQUE("code")
);
--> statement-breakpoint
ALTER TABLE "application_source" ADD CONSTRAINT "application_source_organization_id_organization_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organization"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "application_source" ADD CONSTRAINT "application_source_application_id_application_id_fk" FOREIGN KEY ("application_id") REFERENCES "public"."application"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "application_source" ADD CONSTRAINT "application_source_tracking_link_id_tracking_link_id_fk" FOREIGN KEY ("tracking_link_id") REFERENCES "public"."tracking_link"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tracking_link" ADD CONSTRAINT "tracking_link_organization_id_organization_id_fk" FOREIGN KEY ("organization_id") REFERENCES "public"."organization"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tracking_link" ADD CONSTRAINT "tracking_link_job_id_job_id_fk" FOREIGN KEY ("job_id") REFERENCES "public"."job"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "tracking_link" ADD CONSTRAINT "tracking_link_created_by_id_user_id_fk" FOREIGN KEY ("created_by_id") REFERENCES "public"."user"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "application_source_organization_id_idx" ON "application_source" USING btree ("organization_id");--> statement-breakpoint
CREATE INDEX "application_source_application_id_idx" ON "application_source" USING btree ("application_id");--> statement-breakpoint
CREATE INDEX "application_source_channel_idx" ON "application_source" USING btree ("channel");--> statement-breakpoint
CREATE INDEX "application_source_tracking_link_id_idx" ON "application_source" USING btree ("tracking_link_id");--> statement-breakpoint
CREATE UNIQUE INDEX "application_source_application_idx" ON "application_source" USING btree ("application_id");--> statement-breakpoint
CREATE INDEX "tracking_link_organization_id_idx" ON "tracking_link" USING btree ("organization_id");--> statement-breakpoint
CREATE INDEX "tracking_link_job_id_idx" ON "tracking_link" USING btree ("job_id");--> statement-breakpoint
CREATE INDEX "tracking_link_code_idx" ON "tracking_link" USING btree ("code");--> statement-breakpoint
CREATE INDEX "tracking_link_channel_idx" ON "tracking_link" USING btree ("channel");