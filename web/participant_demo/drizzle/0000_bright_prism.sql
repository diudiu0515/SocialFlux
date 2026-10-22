CREATE TABLE `demo_sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`dataset_sha256` text NOT NULL,
	`release` text NOT NULL,
	`reviewer_alias` text NOT NULL,
	`prior_exposure` integer NOT NULL,
	`draft_json` text DEFAULT '{}' NOT NULL,
	`item_hashes_json` text NOT NULL,
	`revision` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'in_progress' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	`submitted_at` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `one_demo_per_user_release` ON `demo_sessions` (`user_id`,`dataset_sha256`);