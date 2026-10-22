import { integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const demoSessions = sqliteTable("demo_sessions", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull(),
  datasetSha256: text("dataset_sha256").notNull(),
  release: text("release").notNull(),
  alias: text("reviewer_alias").notNull(),
  priorExposure: integer("prior_exposure", {mode: "boolean"}).notNull(),
  draftJson: text("draft_json").notNull().default("{}"),
  itemHashesJson: text("item_hashes_json").notNull(),
  mediaReviewsJson: text("media_reviews_json").notNull().default("{}"),
  mediaHashesJson: text("media_hashes_json").notNull().default("{}"),
  assignmentJson: text("assignment_json").notNull().default("{}"),
  workflowJson: text("workflow_json").notNull().default("{}"),
  revision: integer("revision").notNull().default(0),
  status: text("status").notNull().default("in_progress"),
  createdAt: text("created_at").notNull(),
  updatedAt: text("updated_at").notNull(),
  submittedAt: text("submitted_at"),
}, table => [uniqueIndex("one_demo_per_user_release").on(table.userId, table.datasetSha256)]);
