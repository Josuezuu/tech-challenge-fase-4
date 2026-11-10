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
    pacientes = app.sidebar.radio[0].options
    for pid in pacientes:
        app.sidebar.radio[0].set_value(pid).run()
        assert not app.exception, pid
