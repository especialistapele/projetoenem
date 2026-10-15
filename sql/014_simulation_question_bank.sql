-- Mantém o conjunto de questões de cada simulado separado das respostas dos alunos.
-- Pode ser executado mais de uma vez sem duplicar o banco de questões.
CREATE TABLE IF NOT EXISTS public.simulation_questions (
    id BIGSERIAL PRIMARY KEY,
    simulation_id BIGINT NOT NULL REFERENCES public.simulations(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES public.questions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    CONSTRAINT simulation_questions_simulation_question_key UNIQUE (simulation_id, question_id),
    CONSTRAINT simulation_questions_simulation_position_key UNIQUE (simulation_id, position)
);

-- Migra as linhas antigas que representavam apenas a composição do simulado.
INSERT INTO public.simulation_questions (simulation_id, question_id, position)
SELECT simulation_id, question_id, position
FROM public.simulation_attempts
WHERE user_id IS NULL
ON CONFLICT (simulation_id, question_id) DO NOTHING;

-- Remove apenas as linhas antigas de composição; respostas vinculadas a alunos são preservadas.
DELETE FROM public.simulation_attempts
WHERE user_id IS NULL;

-- Evita respostas duplicadas para a mesma questão de um mesmo aluno.
CREATE UNIQUE INDEX IF NOT EXISTS simulation_attempts_student_question_uidx
ON public.simulation_attempts (simulation_id, question_id, user_id)
WHERE user_id IS NOT NULL;

ALTER TABLE public.simulation_questions ENABLE ROW LEVEL SECURITY;

-- A API lê/escreve esta tabela usando a conexão backend do banco.
-- Não concedemos acesso direto aos papéis anon/authenticated.
REVOKE ALL ON TABLE public.simulation_questions FROM anon, authenticated;
