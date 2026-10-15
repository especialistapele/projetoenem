#!/bin/bash
# Duplo-clique neste arquivo (Mac) ou execute-o (Linux) para subir o sistema
# sem precisar digitar comandos manualmente.

cd "$(dirname "$0")"

echo "============================================"
echo " Sistema de Analise Historica do ENEM"
echo "============================================"
echo

if [ ! -f "venv/bin/python" ]; then
    echo "[1/3] Nenhum ambiente virtual encontrado. Criando um novo..."
    python3 -m venv venv
else
    echo "[1/3] Ambiente virtual encontrado."
fi

echo
echo "[2/3] Instalando/atualizando dependencias..."
"venv/bin/python" -m pip install --quiet --upgrade pip
"venv/bin/python" -m pip install --quiet -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp ".env.example" ".env"
fi

echo
echo "[3/3] Iniciando o servidor..."
echo "A pagina vai abrir automaticamente em alguns segundos."
echo "Para PARAR o sistema, feche esta janela ou pressione Ctrl+C."
echo

( sleep 3 && (open http://127.0.0.1:8000/docs 2>/dev/null || xdg-open http://127.0.0.1:8000/docs 2>/dev/null) ) &

"venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo
echo "Servidor encerrado."
read -p "Pressione Enter para fechar..."
