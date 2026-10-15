-- Preserva questões oficialmente anuladas sem inventar uma alternativa correta.
ALTER TABLE public.questions
    ADD COLUMN IF NOT EXISTS is_annulled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.questions.is_annulled IS
    'True quando o gabarito oficial do INEP declara a questão anulada; não deve pontuar como certa ou errada.';
