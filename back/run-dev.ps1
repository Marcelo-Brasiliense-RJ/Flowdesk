# Inicia o backend FlowDesk em modo desenvolvimento.
#
# O reload observa SOMENTE back/app (caminho absoluto) e exclui storage/.
# Isso é essencial: o runtime regrava scripts .py em back/storage/<projeto>/src
# a cada execução; se o watcher enxergar isso, cada execução reinicia o servidor
# e o ceifador de zumbis cancela a própria execução em andamento.
# Para operação estável (suíte de QA, uso real), prefira sem --reload:
#   .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
Set-Location $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn main:app `
    --host 127.0.0.1 --port 8000 `
    --reload --reload-dir "$PSScriptRoot\app" `
    --reload-exclude "$PSScriptRoot\storage\*"
