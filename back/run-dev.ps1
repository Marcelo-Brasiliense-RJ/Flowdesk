# Inicia o backend FlowDesk em modo desenvolvimento.
#
# --reload-dir app: o reload observa SOMENTE back/app. Isso é essencial porque o
# runtime regrava os scripts das automações em back/storage/<projeto>/src a cada
# execução; se o reload observasse a árvore inteira, cada execução reiniciaria o
# servidor e o ceifador de zumbis cancelaria a própria execução em andamento.
Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn main:app `
    --host 127.0.0.1 --port 8000 `
    --reload --reload-dir app
