-- Consultas auxiliares para o catálogo da taxonomia.
CREATE OR REPLACE VIEW v_enem_taxonomy AS
SELECT
    tv.code AS taxonomy_version,
    ka.code AS area_code,
    ka.name AS area,
    c.code AS competency_code,
    c.name AS competency,
    sd.code AS skill_code,
    sd.description AS skill_description,
    sd.source_status
FROM skill_definitions sd
JOIN competencies c ON c.id = sd.competency_id
JOIN taxonomy_versions tv ON tv.id = c.taxonomy_version_id
JOIN knowledge_areas ka ON ka.id = c.knowledge_area_id;
