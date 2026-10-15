# ENEM Predict — Fases avançadas implementadas

- Importador seguro em staging: validação PDF, hash, deduplicação, versões especiais, preflight, preparação e dry-run.
- Gestão de usuários: admin cria aluno/professor/admin e associa curso.
- Gestão professor → alunos e permissões por perfil.
- Três simulados por ciclo anual.
- Resultado de simulado com TRI 3PL estimativa por área.
- Teste de proficiência inicial: iniciar, responder, finalizar e gravar resultados por área.
- Teia Cognitiva: área → disciplina → conteúdo, com domínio e prioridade.
- Prioridades de estudo persistidas e checklist concluível.
- Redação mensal e fila de correção do professor com janela operacional de 7 dias.
- Dashboard do aluno com histórico de simulados e redações.
- Dashboard administrativo ampliado e endpoint operacional.
- Seleção de curso do aluno persistida em `user_profiles.program_id`.

## SQL
Executar `sql/012_learning_completion.sql` no SQL Editor do Supabase após as migrations anteriores.

## TRI
A TRI é explicitamente uma **estimativa pedagógica**. Parâmetros não calibrados oficialmente continuam marcados como `estimated`.

## Dados reais
A classificação conteúdo → habilidade → competência e uma calibração psicométrica real dependem da alimentação e validação do banco com provas/gabaritos históricos. O sistema não inventa essas classificações.

## Atualização final — 2026-08-27

- Migration `013_proficiency_assessment_items.sql` adicionada ao pacote.
- A migration foi aplicada ao projeto Supabase correto `evqbhkrjguramcphdjtk`.
- O arquivo `.env` mantém `SUPABASE_SERVICE_ROLE_KEY` como placeholder; a chave real não é gravada no pacote.
