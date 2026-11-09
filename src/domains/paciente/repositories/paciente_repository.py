"""paciente_repository.py

Acesso a dados de Paciente (e do seu PacienteDadosPessoais): busca por ID, UUID
e CPF, listagem paginada, contagens (com "hoje" no fuso da empresa), checagem de
consulta aberta e a linha de auditoria das escritas excepcionais.

O isolamento entre empresas vive aqui, não na rota: toda busca por UUID, CPF e
listagem filtra a empresa, porque o UUID sozinho não prova posse e o mesmo CPF
pode existir como pacientes distintos em empresas diferentes. Todo
commit/flush/rollback do domínio Paciente também vive aqui: os métodos de escrita
aceitam `commit` (True confirma; False só faz flush, deixando a transação aberta
para o chamador, em operações maiores e atômicas como abrir consulta com cadastro
ou uma ação sensível que comita junto com o log). Nada é apagado fisicamente.
"""
from datetime import datetime, time, timezone
from typing import Optional, List, Union

from sqlalchemy import func

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import Paciente, PacienteDadosPessoais
from src.models.corp.empresa import Empresa

POR_PAGINA_RESUMO = 8


class PacienteRepository(IRepository[Paciente]):

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        """Fecha a unidade de trabalho: commit, ou só flush se o chamador vai comitar depois."""
        if commit:
            db.session.commit()
        else:
            db.session.flush()

    def rollback(self) -> None:
        db.session.rollback()

    # ---------------------------------------------------------------- leitura
    def find_by_id(self, id: int) -> Optional[Paciente]:
        return db.session.get(Paciente, id)

    def find_by_uuid(self, uuid: str, id_empresa: int) -> Optional[Paciente]:
        """Busca pelo UUID público, DENTRO da empresa (isolamento de tenant no repository)."""
        return Paciente.query.filter_by(uuid=uuid, id_empresa=id_empresa).first()

    def find_por_cpf_hash(self, cpf_hash: str, id_empresa: int) -> Optional[Paciente]:
        """Busca por CPF pelo hash HMAC-SHA256 (determinístico), não pelo valor cifrado com AES-256-GCM.

        Escopada por empresa: o mesmo CPF pode existir como pacientes distintos em empresas
        diferentes, e buscar sem esse filtro vazaria a existência do paciente entre empresas, mesmo
        sem vazar PII. O `id_empresa` vive em PacienteDadosPessoais (desnormalizado de
        Paciente.id_empresa) para sustentar a UNIQUE composta (id_empresa, cpf_hash) no banco.
        """
        pessoal = PacienteDadosPessoais.query.filter_by(
            cpf_hash=cpf_hash, id_empresa=id_empresa
        ).first()
        return pessoal.paciente if pessoal else None

    def tem_consulta_aberta(self, id_paciente: int, id_empresa: int) -> bool:
        """True se o paciente tem Consulta aberta (status_consulta != 'encerrada', o mesmo critério
        do índice único de consulta aberta). Escopada por empresa.

        A classe Consulta vem do relationship Paciente.consultas, para este repository não depender
        do módulo onde Consulta mora. Quando houver um método equivalente em ConsultaRepository,
        troque por ele e apague este: o critério de "aberta" deve viver num lugar só.
        """
        Consulta = Paciente.consultas.property.mapper.class_
        return db.session.query(
            db.session.query(Paciente.id)
            .filter(
                Paciente.id == id_paciente,
                Paciente.id_empresa == id_empresa,
                Paciente.consultas.any(Consulta.status_consulta != "encerrada"),
            )
            .exists()
        ).scalar()

    def find_all(self, id_empresa: int) -> List[Paciente]:
        """Todos os pacientes da empresa."""
        return Paciente.query.filter_by(id_empresa=id_empresa).all()

    def find_all_param(self, id_empresa: int, offset: int = 0, status: str = None,
                       sexo_biologico: str = None) -> List[Paciente]:
        """Listagem paginada (POR_PAGINA_RESUMO por página, do mais recente ao mais antigo) para a
        listagem enxuta (to_dict_few).

        Nome e CPF não filtram aqui: vivem cifrados em PacienteDadosPessoais (AES-256-GCM) e não dá
        para fazer ILIKE ou igualdade sobre coluna cifrada. O CPF tem busca exata pelo hash
        (find_por_cpf_hash) e o nome é buscado em memória pelo service.
        """
        filtros = {"id_empresa": id_empresa}
        if status:
            filtros["status"] = status
        if sexo_biologico:
            filtros["sexo_biologico"] = sexo_biologico

        return (
            Paciente.query.filter_by(**filtros)
            .order_by(Paciente.criado_em.desc())
            .offset(offset)
            .limit(POR_PAGINA_RESUMO)
            .all()
        )

    # --------------------------------------------------------------- escrita
    def save(self, entity: Union[Paciente, PacienteDadosPessoais], commit: bool = True):
        """Persiste Paciente OU PacienteDadosPessoais (mesma sessão, mesma transação)."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int, commit: bool = True) -> bool:
        """Paciente nunca é apagado fisicamente: prontuário e consultas dependem dele (e apagar
        levaria o histórico clínico junto, pelo cascade). Para LGPD use anonimizar; para encerrar
        acompanhamento, status='inativo'."""
        raise NotImplementedError(
            "Paciente não é removido fisicamente; use anonimizar() (LGPD) ou status='inativo'."
        )

    def registrar_auditoria(self, id_usuario: int, acao: str, uuid_paciente: str,
                            commit: bool = True) -> None:
        """Linha em RegistroAuditoria sobre um paciente (escrita excepcional de admin). Import local:
        o domínio de auditoria não deve ser carregado junto com este repository em toda importação."""
        from src.models.auditoria import RegistroAuditoria
        db.session.add(RegistroAuditoria(
            id_usuario=id_usuario,
            acao=acao,
            entidade="paciente",
            entidade_uuid=uuid_paciente,
        ))
        self.confirmar(commit)

    # ------------------------------------------------------------ contagens
    def _limites_do_dia_utc(self, id_empresa: int):
        """Início e fim do dia de HOJE no fuso da empresa (Empresa.fuso_horario), convertidos para
        UTC, porque `criado_em` é gravado em UTC. Sem isso "hoje" seria calculado em UTC puro, o que
        desloca a virada do dia em algumas horas em relação ao horário local da empresa."""
        empresa = db.session.get(Empresa, id_empresa)
        fuso = empresa.fuso_horario if empresa else timezone.utc

        hoje_local = datetime.now(fuso).date()
        inicio_local = datetime.combine(hoje_local, time.min, tzinfo=fuso)
        fim_local = datetime.combine(hoje_local, time.max, tzinfo=fuso)

        return inicio_local.astimezone(timezone.utc), fim_local.astimezone(timezone.utc)

    def count_pacientes_hoje(self, id_empresa: int) -> int:
        """Pacientes cadastrados hoje no fuso da empresa."""
        inicio_dia, fim_dia = self._limites_do_dia_utc(id_empresa)

        return (
            db.session.query(func.count(Paciente.id))
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Paciente.criado_em >= inicio_dia)
            .filter(Paciente.criado_em < fim_dia)
            .scalar()
        )

    def count_pacientes(self, id_empresa: int) -> int:
        """Total de pacientes da empresa."""
        return (
            db.session.query(func.count(Paciente.id))
            .filter(Paciente.id_empresa == id_empresa)
            .scalar()
        )
