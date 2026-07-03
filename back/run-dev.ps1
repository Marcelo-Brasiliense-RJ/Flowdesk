# Inicia o backend FlowDesk: UM servidor, na :8000, com auto-reload SEGURO.
#
# O watcher observa APENAS a pasta app/ (--reload-dir app). Isso e essencial: o
# runtime regrava o script .py de cada projeto em back/storage/<id>/ a CADA
# execucao; se o watcher visse storage/ (como faz o --reload padrao, que observa o
# diretorio inteiro), REINICIARIA o servidor no meio da execucao e o teste morreria
# ("o servidor foi reiniciado"). Excluir storage/ via --reload-exclude nao e
# confiavel no Python 3.11 (PurePath.match nao casa ** aninhado); restringir o
# watch a app/ resolve na raiz e ainda recarrega ao editar rotas/servicos/config.
#
# Editou main.py (fora de app/)? Ele nao esta no watch: rode este script de novo.
# Ele DERRUBA o servidor anterior antes de subir, evitando dois processos na mesma
# porta (Windows aceita) ou um processo zumbi servindo codigo velho.
Set-Location $PSScriptRoot

# derruba qualquer uvicorn main:app anterior (evita zumbi / codigo velho)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn*main:app*' } |
    ForEach-Object {
        Write-Host "Derrubando uvicorn anterior (pid $($_.ProcessId))..."
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Milliseconds 400

Write-Host "Subindo FlowDesk em http://127.0.0.1:8000 (reload so em app/)"
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
