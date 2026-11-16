"""O painel abre sem exceção com results/ vazio e com results/ gerado pelo cenário."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAINEL = Path(__file__).resolve().parents[2] / "app" / "painel.py"
RESULTADOS = PAINEL.parents[1] / "results"


def _app(resultados: Path) -> AppTest:
    app = AppTest.from_file(str(PAINEL), default_timeout=60)
    app.run()
    return app


def test_painel_sem_resultados(tmp_path):
    codigo = PAINEL.read_text(encoding="utf-8").replace(
        'RESULTADOS = RAIZ / "results"', f'RESULTADOS = __import__("pathlib").Path(r"{tmp_path}")')
    app = AppTest.from_string(codigo, default_timeout=60)
    app.run()
    assert not app.exception
    assert any("Reproduzir cenário" in i.value for i in app.info)


@pytest.mark.skipif(not (RESULTADOS / "cenario.json").exists(), reason="rode python -m experiments.run_cenario antes")
def test_painel_com_cenario():
    app = _app(RESULTADOS)
    assert not app.exception
    pacientes = app.radio(key="paciente").options
    ids = [p.split(" ")[0] for p in pacientes]  # o rótulo é "<id> · <nível>"
    leitos = [p for p in ids if p.startswith("leito-")]
    assert leitos == sorted(leitos, key=lambda p: int(p.split("-")[1]))
    assert ids[:len(leitos)] == leitos
    for pid in pacientes:
        app.radio(key="paciente").set_value(pid).run()
        assert not app.exception, pid
    assert [t.label for t in app.tabs] == ["Alertas", "Sinais vitais", "Vídeo", "Áudio", "Prescrições"]


def test_avaliacao_e_visao_separada():
    app = _app(RESULTADOS)
    app.radio(key="visao").set_value("Avaliação do sistema").run()
    assert not app.exception
    assert app.title[0].value == "Avaliação do sistema"
    assert not app.tabs
    assert not [r for r in app.radio if r.key == "paciente"]
