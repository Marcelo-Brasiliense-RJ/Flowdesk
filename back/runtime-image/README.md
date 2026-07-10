# Imagem de sandbox (flowdesk-runtime)

Imagem usada para executar os scripts das automações em container isolado (S1).

Build:

    docker build -t flowdesk-runtime:latest back/runtime-image

O stack de libs é fixo: a rede fica desligada no runtime, então não há
`pip install` durante a execução. Para adicionar uma dependência que os scripts
possam usar, edite `requirements.txt` e reconstrua a imagem.
