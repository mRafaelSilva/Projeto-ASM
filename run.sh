#!/bin/sh

echo "A verificar o estado do Openfire..."

docker compose up -d

echo "Openfire pronto! Se nunca o tiveres configurado, acessa localhost:9090"

echo "À espera que o Openfire arranque (Porta 5222)..."

while ! curl --silent --output /dev/null http://localhost:9090; do
    sleep 1
done

echo "Servidor Openfire pronto!"
echo "A iniciar o Projeto ASM..."
echo "---------------------------------------"
echo ""

. .venv/bin/activate # Mudar de acordo com o nome do ambiente virtual
python3 main.py