-- Fase 9.3 — Taxonomia ENEM v1
-- Baseada na Matriz de Referência do ENEM (Inep).
-- A versão de referência é registrada para manter rastreabilidade histórica.

CREATE TABLE IF NOT EXISTS taxonomy_versions (
    id SERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    source_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS competencies (
    id SERIAL PRIMARY KEY,
    taxonomy_version_id INTEGER NOT NULL REFERENCES taxonomy_versions(id) ON DELETE CASCADE,
    knowledge_area_id INTEGER NOT NULL REFERENCES knowledge_areas(id) ON DELETE CASCADE,
    code VARCHAR(10) NOT NULL,
    name TEXT NOT NULL,
    UNIQUE(taxonomy_version_id, knowledge_area_id, code)
);

CREATE TABLE IF NOT EXISTS skill_definitions (
    id SERIAL PRIMARY KEY,
    competency_id INTEGER NOT NULL REFERENCES competencies(id) ON DELETE CASCADE,
    code VARCHAR(10) NOT NULL,
    description TEXT,
    source_status VARCHAR(30) NOT NULL DEFAULT 'official',
    UNIQUE(competency_id, code)
);

CREATE TABLE IF NOT EXISTS knowledge_objects (
    id SERIAL PRIMARY KEY,
    taxonomy_version_id INTEGER NOT NULL REFERENCES taxonomy_versions(id) ON DELETE CASCADE,
    knowledge_area_id INTEGER NOT NULL REFERENCES knowledge_areas(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    UNIQUE(taxonomy_version_id, knowledge_area_id, name)
);

CREATE TABLE IF NOT EXISTS question_classifications (
    id BIGSERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    taxonomy_version_id INTEGER NOT NULL REFERENCES taxonomy_versions(id) ON DELETE RESTRICT,
    predicted_area_id INTEGER REFERENCES knowledge_areas(id),
    predicted_subject_id INTEGER REFERENCES subjects(id),
    predicted_competency_id INTEGER REFERENCES competencies(id),
    predicted_skill_id INTEGER REFERENCES skill_definitions(id),
    confidence NUMERIC(5,4) NOT NULL DEFAULT 0,
    method VARCHAR(40) NOT NULL DEFAULT 'heuristic',
    status VARCHAR(30) NOT NULL DEFAULT 'candidate',
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_competencies_area ON competencies(knowledge_area_id);
CREATE INDEX IF NOT EXISTS idx_skills_definition_competency ON skill_definitions(competency_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_objects_area ON knowledge_objects(knowledge_area_id);
CREATE INDEX IF NOT EXISTS idx_question_classifications_question ON question_classifications(question_id);
CREATE INDEX IF NOT EXISTS idx_question_classifications_skill ON question_classifications(predicted_skill_id);
CREATE INDEX IF NOT EXISTS idx_question_classifications_confidence ON question_classifications(confidence);

INSERT INTO taxonomy_versions (code, name, source_url, notes)
VALUES (
    'ENEM-MR-2009-V1',
    'Matriz de Referência do ENEM — versão estrutural',
    'https://download.inep.gov.br/enem/outros_documentos/enem_matriz_referencia.pdf',
    'Estrutura compatível com as quatro áreas objetivas e suas competências/habilidades H1-H30. A taxonomia mantém a referência oficial separada dos classificadores heurísticos.'
)
ON CONFLICT (code) DO NOTHING;
