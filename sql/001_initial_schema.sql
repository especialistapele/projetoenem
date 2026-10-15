-- =========================================================
-- ENEM Historical Analysis System — Initial Schema
-- Fase 3 (núcleo) + Fase 4 (grafo) + Fase 5.5 (pesos por curso)
-- Aplicado no Supabase (projeto: Sistema Enem / evqbhkrjguramcphdjtk)
-- =========================================================

CREATE TABLE knowledge_areas (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    code VARCHAR(20) UNIQUE
);

CREATE TABLE subjects (
    id SERIAL PRIMARY KEY,
    knowledge_area_id INTEGER NOT NULL REFERENCES knowledge_areas(id),
    name VARCHAR(100) NOT NULL,
    UNIQUE(knowledge_area_id, name)
);

CREATE TABLE skills (
    id SERIAL PRIMARY KEY,
    knowledge_area_id INTEGER NOT NULL REFERENCES knowledge_areas(id),
    code VARCHAR(10) NOT NULL,
    description TEXT NOT NULL,
    UNIQUE(knowledge_area_id, code)
);

CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    parent_topic_id INTEGER REFERENCES topics(id),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    UNIQUE(subject_id, name)
);

CREATE TABLE exams (
    id SERIAL PRIMARY KEY,
    year INTEGER NOT NULL,
    edition VARCHAR(20) NOT NULL DEFAULT 'regular',
    color VARCHAR(20) DEFAULT 'azul',
    day INTEGER,
    application_date DATE,
    UNIQUE(year, edition, color, day)
);

CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    subject_id INTEGER REFERENCES subjects(id),
    skill_id INTEGER REFERENCES skills(id),
    source_text TEXT,
    statement_text TEXT NOT NULL,
    image_url TEXT,
    difficulty_estimate NUMERIC(4,3),
    search_vector tsvector,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(exam_id, number)
);

CREATE INDEX idx_questions_search ON questions USING GIN(search_vector);
CREATE INDEX idx_questions_subject ON questions(subject_id);
CREATE INDEX idx_questions_skill ON questions(skill_id);
CREATE INDEX idx_questions_exam ON questions(exam_id);

CREATE OR REPLACE FUNCTION questions_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('portuguese',
        coalesce(NEW.source_text, '') || ' ' || coalesce(NEW.statement_text, ''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_questions_search_vector
BEFORE INSERT OR UPDATE ON questions
FOR EACH ROW EXECUTE FUNCTION questions_search_vector_update();

CREATE TABLE alternatives (
    id SERIAL PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    letter CHAR(1) NOT NULL,
    text TEXT NOT NULL,
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(question_id, letter)
);

CREATE TABLE question_topics (
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    relevance NUMERIC(3,2) DEFAULT 1.0,
    PRIMARY KEY (question_id, topic_id)
);

CREATE TABLE topic_edges (
    id SERIAL PRIMARY KEY,
    topic_a_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    topic_b_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    edge_type VARCHAR(30) NOT NULL DEFAULT 'co_occurrence',
    weight NUMERIC(6,3) NOT NULL DEFAULT 1.0,
    CHECK (topic_a_id < topic_b_id),
    UNIQUE(topic_a_id, topic_b_id, edge_type)
);

CREATE TABLE topic_year_frequency (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    question_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(topic_id, year)
);

CREATE TABLE institutions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE,
    acronym VARCHAR(20)
);

CREATE TABLE programs (
    id SERIAL PRIMARY KEY,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    UNIQUE(institution_id, name)
);

CREATE TABLE program_weights (
    id SERIAL PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    knowledge_area_id INTEGER NOT NULL REFERENCES knowledge_areas(id),
    weight NUMERIC(5,2) NOT NULL,
    source_year INTEGER,
    UNIQUE(program_id, knowledge_area_id, source_year)
);

INSERT INTO knowledge_areas (name, code) VALUES
    ('Linguagens, Códigos e suas Tecnologias', 'LC'),
    ('Ciências Humanas e suas Tecnologias', 'CH'),
    ('Ciências da Natureza e suas Tecnologias', 'CN'),
    ('Matemática e suas Tecnologias', 'MT'),
    ('Redação', 'RED');
