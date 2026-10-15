-- Corrige a leitura de nomes oficiais PV/GB e preserva o ano completo.
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
    WHEN f ~ '(^|[_ .-])gb([_. -]|$)|gabarito|gabarit' THEN 'answer_key'
    WHEN f ~ '(^|[_ .-])pv([_. -]|$)|caderno|prova' THEN 'question_booklet'
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
  -- A expressão retorna os quatro dígitos do ano, não apenas o prefixo 19/20.
  y := substring(f from '(19[0-9]{2}|20[0-9]{2})')::int;
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
  IF f ~ '(^|[_ .-])gb([_. -]|$)|gabarito|gabarit|gab' THEN t := 'answer_key';
  ELSIF f ~ '(^|[_ .-])pv([_. -]|$)|caderno|prova' THEN t := 'question_booklet';
  ELSE t := 'other'; END IF;
  IF f LIKE '%ppl%' THEN a := 'ppl';
  ELSIF f LIKE '%reaplic%' THEN a := 'reapplication';
  ELSE a := 'regular'; END IF;
  RETURN jsonb_build_object('year',y,'day',d,'color',c,'document_type',t,
                            'application_type',a,'confidence',least(conf,0.99));
END;
$function$;
