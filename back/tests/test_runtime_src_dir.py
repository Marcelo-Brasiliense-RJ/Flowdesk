from app.config import BACK_DIR, RUNTIME_SRC_DIR


def test_runtime_src_fora_do_back_dir():
    # o watcher do `uvicorn --reload` observa back/ (o diretório de trabalho); o
    # código do projeto é regravado a cada execução, então PRECISA ficar fora daí,
    # senão o servidor reinicia no meio do teste e a execução morre.
    src = RUNTIME_SRC_DIR.resolve()
    back = BACK_DIR.resolve()
    assert back != src and back not in src.parents
