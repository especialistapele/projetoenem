-- Índices para chaves estrangeiras adicionadas pela migração de taxonomia.
CREATE INDEX IF NOT EXISTS competencies_knowledge_area_idx
  ON public.competencies (knowledge_area_id);
CREATE INDEX IF NOT EXISTS knowledge_objects_knowledge_area_idx
  ON public.knowledge_objects (knowledge_area_id);
CREATE INDEX IF NOT EXISTS knowledge_objects_taxonomy_version_idx
  ON public.knowledge_objects (taxonomy_version_id);
