# Inicia o backend FlowDesk: UM servidor, na :8000, SEM auto-reload.
#
# POR QUE SEM --reload:
# O runtime regrava o script .py de cada projeto em back/storage/<id>/ a CADA
# execucao. Com `uvicorn --reload`, o watcher enxerga esse .py e REINICIA o
# servidor no meio da execucao: o teste/publicacao morre ("o servidor foi
# reiniciado"), a acao nao reflete na tela e a taxa de erro dispara. No Python
# 3.11 nao da para excluir storage/ do watcher de forma confiavel (PurePath.match
# nao casa ** aninhado), entao a opcao estavel e nao usar --reload.
#
# Editou o codigo do backend? Rode este script de novo. Ele DERRUBA o servidor
# anterior antes de subir, evitando dois processos na mesma porta (Windows aceita)
# ou um processo zumbi servindo codigo velho.
Set-Location $PSScriptRoot

# derruba qualquer uvicorn main:app anterior (evita zumbi / codigo velho)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*uvicorn*main:app*' } |
    ForEach-Object {
        Write-Host "Derrubando uvicorn anterior (pid $($_.ProcessId))..."
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Start-Sleep -Milliseconds 400

Write-Host "Subindo FlowDesk em http://127.0.0.1:8000 (sem --reload)"
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
