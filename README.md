# ENEM Predict — versão 0.8.0

Esta entrega alinha **backend + frontend + Supabase** e acrescenta a camada de conteúdo/experiência do estudante.

## Novidades
- Importador ENEM com descoberta pela página oficial do Inep e fallback para o catálogo RIEP.
- Catálogo de provas, cadernos e gabaritos em staging antes da gravação definitiva.
- Três simulados por ciclo, com estrutura para 180 questões e análise por área/competência quando a taxonomia estiver vinculada.
- Estimativa pedagógica de desempenho (não é nota oficial TRI).
- Histórico e gráficos de evolução dos simulados.
- Uma redação por mês por estudante.
- Fila de correção para professor/admin, com prazo operacional de 7 dias.
- Notas por Competência I–V e gráfico histórico de redações.
- Programa padrão **ENEM Geral** para permitir a seleção inicial de curso/programa.

## Fontes oficiais
O importador prioriza as páginas de Provas e Gabaritos do Inep e usa o RIEP como fallback. A matriz de referência deve ser usada como base oficial da taxonomia.

## Banco
Migration principal desta entrega:
- `sql/009_simulations_redactions.sql`

Também foi aplicado no projeto Supabase `evqbhkrjguramcphdjtk` o seed do programa ENEM Geral e dos três simulados do ciclo atual.

## Execução local
```powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Acesse `http://127.0.0.1:8001`.


## Importação oficial de questões e taxonomia

Com o backend local ativo, autenticado como administrador, os endpoints abaixo permitem executar o fluxo sem acessar diretamente o banco pelo navegador:

- `POST /enem-import/import-official-2025-blue` com `{"dry_run": true}`: baixa os cadernos azuis regulares dos dois dias do ENEM 2025, extrai questões e gabaritos e valida o lote sem gravar questões no banco.
- Repita com `{"dry_run": false}` somente quando o relatório indicar 90 questões por dia, gabaritos correspondentes e nenhuma falha estrutural.
- `POST /enem-import/taxonomy` com `{"dry_run": true}`: baixa a Matriz de Referência oficial do INEP e verifica as quatro áreas, 30 competências e 120 habilidades antes de gravar.
- Repita a importação da taxonomia com `{"dry_run": false}` após o relatório de validação estar correto.

As questões cuja disciplina não puder ser inferida ficam sob **Classificação pendente**, vinculadas à área oficial pelo número da questão e marcadas para revisão. A taxonomia só recebe descrições extraídas do PDF oficial. Os endpoints exigem o administrador e mantêm o TLS validado.

## Camada TRI estimativa e painel administrativo
- TRI 3PL implementada como **estimativa pedagógica**, sem alegar equivalência à nota oficial do ENEM.
- Parâmetros por item ficam separados em `item_tri_parameters`, permitindo futura calibração com dados históricos.
- Endpoint `GET /learning/proficiency/estimate` calcula proficiência por área a partir das respostas do aluno.
- Endpoint `GET /admin/overview` fornece visão geral de usuários, vínculos professor-aluno, banco, simulados, redações e estado da camada TRI.
- A chave `SUPABASE_SERVICE_ROLE_KEY` continua exclusivamente no backend local; nunca deve ser colocada no frontend.
