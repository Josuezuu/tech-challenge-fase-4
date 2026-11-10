from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from monitor.config import Credenciais
from monitor.nuvem.azure_linguagem import ClienteLinguagem
from monitor.nuvem.gravacao import Gravador
from monitor.prescricoes.catalogo import CATALOGO
from monitor.prescricoes.modelo import ItemPrescricao

T0 = datetime(2026, 11, 11, 8, 0, 0)


@pytest.fixture
def cliente_simulado(tmp_path) -> ClienteLinguagem:  # noqa: ANN001
    """Léxico local, sem chave e sem ler gravações do repositório."""
    sem_chave = Credenciais(None, None, None, None, None, "gpt-4o-mini")
    return ClienteLinguagem(credenciais=sem_chave, modo="simulado", gravador=Gravador("azure_linguagem", tmp_path))


def item(dia: float, medicamento: str, dose: float, acao: str = "manutencao", via: str | None = None,
         paciente: str = "leito-12", texto: str = "") -> ItemPrescricao:
    med = CATALOGO[medicamento]
    return ItemPrescricao(paciente, T0 + timedelta(days=dia), medicamento, float(dose), med.unidade,
                          via or med.vias[0], float(med.intervalo_h), acao,  # type: ignore[arg-type]
                          texto or f"{medicamento} {dose:g} {med.unidade}", f"{paciente}-{medicamento}-{dia:g}")
