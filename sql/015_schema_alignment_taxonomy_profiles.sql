-- Reconcilia o esquema usado pelo backend com o banco ENEM.
-- A migração é aditiva e pode ser reaplicada sem remover conteúdo existente.

CREATE TABLE IF NOT EXISTS public.taxonomy_versions (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,
    source_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.competencies (
    id BIGSERIAL PRIMARY KEY,
    taxonomy_version_id BIGINT NOT NULL REFERENCES public.taxonomy_versions(id) ON DELETE CASCADE,
    knowledge_area_id INTEGER NOT NULL REFERENCES public.knowledge_areas(id) ON DELETE CASCADE,
    code VARCHAR(10) NOT NULL,
    name TEXT NOT NULL,
    CONSTRAINT competencies_version_area_code_key UNIQUE (taxonomy_version_id, knowledge_area_id, code)
);

CREATE TABLE IF NOT EXISTS public.skill_definitions (
    id BIGSERIAL PRIMARY KEY,
    competency_id BIGINT NOT NULL REFERENCES public.competencies(id) ON DELETE CASCADE,
    code VARCHAR(10) NOT NULL,
    description TEXT,
    source_status VARCHAR(30) NOT NULL DEFAULT 'official',
    CONSTRAINT skill_definitions_competency_code_key UNIQUE (competency_id, code)
);

CREATE TABLE IF NOT EXISTS public.knowledge_objects (
    id BIGSERIAL PRIMARY KEY,
    taxonomy_version_id BIGINT NOT NULL REFERENCES public.taxonomy_versions(id) ON DELETE CASCADE,
    knowledge_area_id INTEGER NOT NULL REFERENCES public.knowledge_areas(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    CONSTRAINT knowledge_objects_version_area_name_key UNIQUE (taxonomy_version_id, knowledge_area_id, name)
);

ALTER TABLE public.questions
    ADD COLUMN IF NOT EXISTS taxonomy_competency_id BIGINT,
    ADD COLUMN IF NOT EXISTS taxonomy_skill_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'questions_taxonomy_competency_id_fkey') THEN
        ALTER TABLE public.questions ADD CONSTRAINT questions_taxonomy_competency_id_fkey
            FOREIGN KEY (taxonomy_competency_id) REFERENCES public.competencies(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'questions_taxonomy_skill_id_fkey') THEN
        ALTER TABLE public.questions ADD CONSTRAINT questions_taxonomy_skill_id_fkey
            FOREIGN KEY (taxonomy_skill_id) REFERENCES public.skill_definitions(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS questions_taxonomy_competency_idx ON public.questions(taxonomy_competency_id);
CREATE INDEX IF NOT EXISTS questions_taxonomy_skill_idx ON public.questions(taxonomy_skill_id);

CREATE OR REPLACE VIEW public.v_enem_taxonomy
WITH (security_invoker = true)
AS
SELECT tv.code AS taxonomy_version,
       ka.code AS area_code,
       ka.name AS area,
       c.code AS competency_code,
       c.name AS competency,
       sd.code AS skill_code,
       sd.description AS skill_description,
       sd.source_status AS source_status
FROM public.taxonomy_versions tv
JOIN public.competencies c ON c.taxonomy_version_id = tv.id
JOIN public.knowledge_areas ka ON ka.id = c.knowledge_area_id
LEFT JOIN public.skill_definitions sd ON sd.competency_id = c.id;

ALTER TABLE public.taxonomy_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.competencies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.skill_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_objects ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.taxonomy_versions, public.competencies, public.skill_definitions, public.knowledge_objects, public.v_enem_taxonomy FROM anon, authenticated;

-- Sincroniza usuários que já existiam no Auth/perfis antes de a tabela user_profiles ser usada.
INSERT INTO public.user_profiles (user_id, role, program_id, display_name)
SELECT u.id,
       CASE
         WHEN COALESCE(NULLIF(u.raw_app_meta_data->>'role',''), NULLIF(p.role,'')) IN ('admin','teacher','student')
           THEN COALESCE(NULLIF(u.raw_app_meta_data->>'role',''), NULLIF(p.role,''))
         ELSE 'student'
       END,
       NULL,
       COALESCE(NULLIF(p.full_name,''), NULLIF(u.raw_user_meta_data->>'display_name',''), NULLIF(split_part(COALESCE(u.email,''),'@',1),''), 'Usuário')
FROM auth.users u
LEFT JOIN public.profiles p ON p.id = u.id
ON CONFLICT (user_id) DO UPDATE
SET role = CASE
             WHEN public.user_profiles.role IN ('admin','teacher','student') THEN public.user_profiles.role
             ELSE EXCLUDED.role
           END,
    display_name = COALESCE(NULLIF(public.user_profiles.display_name,''), EXCLUDED.display_name),
    updated_at = now();
