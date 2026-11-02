-- The corpus-fragment safety workflow (029, 030) was replaced by model-knowledge safety (031, 036-038).
-- These tables are no longer written or read; dropped in foreign-key order, without CASCADE.
DROP TABLE IF EXISTS herb_safety_evidence;
DROP TABLE IF EXISTS herb_safety_warnings;
DROP TABLE IF EXISTS herb_safety_analysis;
DROP TABLE IF EXISTS herb_safety_cache;
DROP TABLE IF EXISTS herb_safety_runs;
