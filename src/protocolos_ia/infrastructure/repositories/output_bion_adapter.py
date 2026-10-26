"""Este arquivo implementa OutputRepository sobre o EnvioIaService do host, para que a IA use a mesma trilha de persistência do restante do sistema.

abrir_envio resolve o Atendimento pelo InputProtocolo dentro da empresa do autor e delega ao host o guard,
o snapshot do InputModel e a criação do OutputBion. gravar_resposta completa o mesmo registro.
"""
from __future__ import annotations

from typing import Optional

from src.core.exceptions import RecursoNaoEncontradoError

from ...application.ports.output_repository import AutorRequisicao, EnvioAberto, RegistroGravado
from ...repository import OutputBionRepository


class OutputBionAdapter:
    def __init__(self, envio_service=None, repositorio: Optional[OutputBionRepository] = None):
        self._envio_service = envio_service
        self._repo = repositorio or OutputBionRepository()

    @property
    def _envio(self):
        """O EnvioIaService do host é carregado só quando há persistência, para que a consulta avulsa não dependa dele."""
        if self._envio_service is None:
            from src.domains.dados_clinicos.envio_ia_service import EnvioIaService

            self._envio_service = EnvioIaService()
        return self._envio_service

    def abrir_envio(self, id_input_protocolo: int, autor: AutorRequisicao) -> EnvioAberto:
        """Esta função abre o envio. Input inexistente e input de outra empresa geram o mesmo 404."""
        from src.domains.atendimento.contexto_clinico_service import AutorClinico

        atendimento = self._repo.find_atendimento_por_input(id_input_protocolo, autor.id_empresa)
        if atendimento is None:
            raise RecursoNaoEncontradoError("Input de protocolo não encontrado.")
        output = self._envio.abrir_envio(
            atendimento.uuid,
            atendimento.consulta.paciente.uuid,
            AutorClinico(id_usuario=autor.id_usuario, funcao_clinica=autor.funcao_clinica, id_empresa=autor.id_empresa),
        )
        return EnvioAberto(
            uuid=output.uuid,
            snapshot=output.input_ia_json,
            versao_input_model=output.versao_input_model,
            criado_em=output.criado_em.isoformat() if output.criado_em else None,
            handle=output,
        )

    def gravar_resposta(
        self, envio: EnvioAberto, output_ia: dict, versao_modelo_ia: str,
        indice_completude: Optional[float] = None, indice_confianca: Optional[float] = None,
    ) -> RegistroGravado:
        salvo = self._envio.gravar_resposta(envio.handle, output_ia, versao_modelo_ia, indice_completude, indice_confianca)
        return RegistroGravado(
            uuid=salvo.uuid,
            versao_input_model=salvo.versao_input_model,
            criado_em=salvo.criado_em.isoformat() if salvo.criado_em else None,
            indice_completude=float(salvo.indice_completude) if salvo.indice_completude is not None else None,
            indice_confianca=float(salvo.indice_confianca) if salvo.indice_confianca is not None else None,
        )
