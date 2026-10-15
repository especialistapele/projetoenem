-- Liga a questão à taxonomia oficial somente após aprovação/revisão.
ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS taxonomy_competency_id INTEGER REFERENCES competencies(id),
    ADD COLUMN IF NOT EXISTS taxonomy_skill_id INTEGER REFERENCES skill_definitions(id);

CREATE INDEX IF NOT EXISTS idx_questions_taxonomy_competency ON questions(taxonomy_competency_id);
CREATE INDEX IF NOT EXISTS idx_questions_taxonomy_skill ON questions(taxonomy_skill_id);
