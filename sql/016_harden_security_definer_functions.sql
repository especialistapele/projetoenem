-- Endurece funções auxiliares sem alterar as regras de autorização baseadas no JWT.
-- SECURITY INVOKER evita que chamadas públicas executem com privilégios do proprietário.

CREATE OR REPLACE FUNCTION public.current_app_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $function$
  SELECT COALESCE((auth.jwt()->'app_metadata'->>'role'), 'student')
$function$;

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $function$
  SELECT public.current_app_role() = 'admin'
$function$;

CREATE OR REPLACE FUNCTION public.is_teacher_or_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $function$
  SELECT public.current_app_role() IN ('teacher','admin')
$function$;

CREATE OR REPLACE FUNCTION public.get_exam_storage_quota()
RETURNS TABLE(
  used_bytes bigint,
  used_mb numeric,
  soft_limit_bytes bigint,
  hard_limit_bytes bigint,
  remaining_bytes bigint,
  usage_percent numeric,
  status text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $function$
  WITH usage AS (
    SELECT COALESCE(SUM(file_size_bytes), 0)::bigint AS used_bytes
    FROM public.exam_documents
    WHERE file_size_bytes IS NOT NULL AND file_size_bytes > 0
  ), limits AS (
    SELECT (400::bigint * 1024 * 1024) AS soft_limit_bytes,
           (450::bigint * 1024 * 1024) AS hard_limit_bytes
  )
  SELECT u.used_bytes,
         round(u.used_bytes / 1024.0 / 1024.0, 2) AS used_mb,
         l.soft_limit_bytes,
         l.hard_limit_bytes,
         greatest(l.hard_limit_bytes - u.used_bytes, 0)::bigint AS remaining_bytes,
         round((u.used_bytes * 100.0) / l.hard_limit_bytes, 2) AS usage_percent,
         CASE
           WHEN u.used_bytes >= l.hard_limit_bytes THEN 'blocked'
           WHEN u.used_bytes >= l.soft_limit_bytes THEN 'warning'
           ELSE 'ok'
         END AS status
  FROM usage u CROSS JOIN limits l
$function$;

CREATE OR REPLACE FUNCTION public.touch_exam_document_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $function$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.detect_enem_document_metadata(p_filename text)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
SET search_path = ''
AS $function$
DECLARE
  f text := lower(coalesce(p_filename,''));
  y int;
  d int;
  c text;
  t text;
  app text := 'regular';
BEGIN
  y := substring(f from '(20[0-9]{2})')::int;
  d := CASE
    WHEN f ~ '(dia[_ -]?1|1[_ -]?dia|d1)' THEN 1
    WHEN f ~ '(dia[_ -]?2|2[_ -]?dia|d2)' THEN 2
    ELSE NULL
  END;
  c := CASE
    WHEN f ~ 'amarelo' THEN 'amarelo'
    WHEN f ~ 'azul' THEN 'azul'
    WHEN f ~ 'branco' THEN 'branco'
    WHEN f ~ 'cinza' THEN 'cinza'
    WHEN f ~ 'rosa' THEN 'rosa'
    WHEN f ~ 'verde' THEN 'verde'
    ELSE NULL
  END;
  t := CASE
    WHEN f ~ '(gabarito|gabarit)' THEN 'answer_key'
    WHEN f ~ '(caderno|prova)' THEN 'question_booklet'
    ELSE 'other'
  END;
  IF f ~ '(ppl|privad[oa]s? de liberdade)' THEN app := 'ppl';
  ELSIF f ~ '(reaplic|reaplica)' THEN app := 'reaplicacao';
  ELSIF f ~ '(segunda aplic|2a aplic|2ª aplic)' THEN app := 'segunda_aplicacao';
  END IF;
  RETURN jsonb_build_object(
    'year', y, 'day', d, 'color', c, 'document_type', t,
    'application_type', app,
    'confidence', CASE WHEN y IS NOT NULL AND d IS NOT NULL AND c IS NOT NULL AND t <> 'other'
                       THEN 0.99 WHEN y IS NOT NULL THEN 0.75 ELSE 0.20 END
  );
END;
$function$;

CREATE OR REPLACE FUNCTION public.parse_enem_filename(p_filename text)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
SET search_path = ''
AS $function$
DECLARE
  f text := lower(regexp_replace(coalesce(p_filename,''), '\s+', '', 'g'));
  y int;
  d int;
  c text;
  t text;
  a text;
  conf numeric := 0.55;
BEGIN
  y := (regexp_match(f, '(19|20)[0-9]{2}'))[1]::int;
  d := (regexp_match(f, '(?:dia|d)([12])'))[1]::int;
  c := CASE
    WHEN f LIKE '%amarelo%' THEN 'amarelo'
    WHEN f LIKE '%azul%' THEN 'azul'
    WHEN f LIKE '%branco%' THEN 'branco'
    WHEN f LIKE '%cinza%' THEN 'cinza'
    WHEN f LIKE '%rosa%' THEN 'rosa'
    WHEN f LIKE '%verde%' THEN 'verde'
    WHEN f LIKE '%laranja%' THEN 'laranja'
    ELSE NULL
  END;
  IF c IS NOT NULL THEN conf := conf + 0.20; END IF;
  IF d IS NOT NULL THEN conf := conf + 0.15; END IF;
  IF y IS NOT NULL THEN conf := conf + 0.10; END IF;
  IF f LIKE '%gabarito%' OR f LIKE '%gab%' THEN t := 'answer_key';
  ELSE t := 'question_booklet'; END IF;
  IF f LIKE '%ppl%' THEN a := 'ppl';
  ELSIF f LIKE '%reaplic%' THEN a := 'reapplication';
  ELSE a := 'regular'; END IF;
  RETURN jsonb_build_object('year',y,'day',d,'color',c,'document_type',t,
                            'application_type',a,'confidence',least(conf,0.99));
END;
$function$;
