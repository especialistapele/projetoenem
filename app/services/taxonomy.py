"""Catálogo estrutural da Matriz de Referência do ENEM.

A fonte normativa é o Inep. Este módulo não inventa uma habilidade: os códigos H1-H30
são associados às competências oficiais e ficam prontos para receber a descrição
oficial/versionada. Isso permite manter o banco auditável e atualizar a matriz sem
quebrar o histórico das classificações.
"""

AREAS = {
    "LC": {
        "name": "Linguagens, Códigos e suas Tecnologias",
        "subjects": ["Língua Portuguesa", "Literatura", "Língua Estrangeira", "Artes", "Educação Física", "Tecnologias da Informação e Comunicação"],
        "competencies": {
            1: ("Aplicar as tecnologias da comunicação e da informação na escola, no trabalho e em outros contextos relevantes para sua vida.", range(1, 5)),
            2: ("Conhecer e usar língua(s) estrangeira(s) moderna(s) como instrumento de acesso a informações e a outras culturas e grupos sociais.", range(5, 8)),
            3: ("Compreender e usar a linguagem corporal como relevante para a própria vida, integradora social e formadora da identidade.", range(8, 11)),
            4: ("Compreender a arte como saber cultural e estético gerador de significação e integrador da organização do mundo e da própria identidade.", range(11, 15)),
            5: ("Analisar, interpretar e aplicar recursos expressivos das linguagens, relacionando textos com seus contextos, mediante a natureza, função, organização, estrutura e condições de produção e recepção.", range(15, 18)),
            6: ("Compreender e usar os sistemas simbólicos das diferentes linguagens como meios de organização cognitiva da realidade pela constituição de significados, expressão, comunicação e informação.", range(18, 21)),
            7: ("Confrontar opiniões e pontos de vista sobre as diferentes linguagens e suas manifestações específicas.", range(21, 25)),
            8: ("Compreender e usar a língua portuguesa como língua materna, geradora de significação e integradora da organização do mundo e da própria identidade.", range(25, 28)),
            9: ("Entender os princípios, a natureza, a função e o impacto das tecnologias da comunicação e da informação na vida pessoal e social e no desenvolvimento do conhecimento.", range(28, 31)),
        },
    },
    "CH": {
        "name": "Ciências Humanas e suas Tecnologias",
        "subjects": ["História", "Geografia", "Filosofia", "Sociologia"],
        "competencies": {
            1: ("Compreender os elementos culturais que constituem as identidades.", range(1, 6)),
            2: ("Compreender as transformações dos espaços geográficos como produto das relações socioeconômicas e culturais de poder.", range(6, 10)),
            3: ("Compreender a produção e o papel histórico das instituições sociais, políticas e econômicas, associando-as aos diferentes grupos, conflitos e movimentos sociais.", range(10, 15)),
            4: ("Entender as transformações técnicas e tecnológicas e seu impacto nos processos de produção, no desenvolvimento do conhecimento e na vida social.", range(15, 21)),
            5: ("Utilizar os conhecimentos históricos para compreender e valorizar os fundamentos da cidadania e da democracia, favorecendo uma atuação consciente do indivíduo na sociedade.", range(21, 26)),
            6: ("Compreender a sociedade e a natureza, reconhecendo suas interações no espaço em diferentes contextos históricos e geográficos.", range(26, 31)),
        },
    },
    "CN": {
        "name": "Ciências da Natureza e suas Tecnologias",
        "subjects": ["Biologia", "Química", "Física"],
        "competencies": {
            1: ("Compreender as ciências naturais e as tecnologias a elas associadas como construções humanas, percebendo seus papéis nos processos de produção e no desenvolvimento econômico e social da humanidade.", range(1, 5)),
            2: ("Identificar a presença e aplicar as tecnologias associadas às ciências naturais em diferentes contextos.", range(5, 8)),
            3: ("Associar intervenções que resultam em degradação ou conservação ambiental a processos naturais e sociais.", range(8, 13)),
            4: ("Compreender interações entre organismos e ambiente, em particular aquelas relacionadas à saúde humana, relacionando conhecimentos científicos, culturais e sociais.", range(13, 17)),
            5: ("Entender métodos e procedimentos próprios das ciências naturais e aplicá-los em diferentes contextos.", range(17, 20)),
            6: ("Apropriar-se de conhecimentos da física para, em situações-problema, interpretar, avaliar ou planejar intervenções científico-tecnológicas.", range(20, 24)),
            7: ("Apropriar-se de conhecimentos da química para, em situações-problema, interpretar, avaliar ou planejar intervenções científico-tecnológicas.", range(24, 28)),
            8: ("Apropriar-se de conhecimentos da biologia para, em situações-problema, interpretar, avaliar ou planejar intervenções científico-tecnológicas.", range(28, 31)),
        },
    },
    "MT": {
        "name": "Matemática e suas Tecnologias",
        "subjects": ["Matemática"],
        "competencies": {
            1: ("Construir significados para os números naturais, inteiros, racionais e reais.", range(1, 6)),
            2: ("Utilizar o conhecimento geométrico para realizar a leitura e a representação da realidade e agir sobre ela.", range(6, 10)),
            3: ("Construir noções de grandezas e medidas para a compreensão da realidade e a solução de problemas do cotidiano.", range(10, 15)),
            4: ("Construir noções de variação de grandezas para a compreensão da realidade e a solução de problemas do cotidiano.", range(15, 18)),
            5: ("Modelar e resolver problemas que envolvem variáveis socioeconômicas ou técnico-científicas, usando representações algébricas.", range(18, 21)),
            6: ("Interpretar informações de natureza científica e social obtidas da leitura de gráficos e tabelas, realizando previsão de tendência, extrapolação, interpolação e interpretação.", range(21, 25)),
            7: ("Compreender o caráter aleatório e não determinístico dos fenômenos naturais e sociais e utilizar instrumentos adequados para medidas, determinação de amostras e cálculos de probabilidade.", range(25, 31)),
        },
    },
}


def iter_skills():
    for area_code, area in AREAS.items():
        for competency_number, (name, skill_range) in area["competencies"].items():
            for h in skill_range:
                yield area_code, competency_number, f"H{h}", None
