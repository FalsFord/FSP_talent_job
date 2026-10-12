CREATE TYPE "public"."candidate_response" AS ENUM('pending', 'accepted', 'declined', 'tentative');--> statement-breakpoint
ALTER TABLE "interview" ADD COLUMN "candidate_response" "candidate_response" DEFAULT 'pending' NOT NULL;--> statement-breakpoint
ALTER TABLE "interview" ADD COLUMN "candidate_responded_at" timestamp;