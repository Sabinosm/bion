from typing import Optional, List, Union

from src.models import db
from src.core.interfaces import IRepository
from src.models.pacientes import (
    Paciente, PacienteDadosPessoais, Alergia, ReacaoAlergia,
    DoencaCronica, MedicamentoEmUso, Consentimento, ObservacaoTipoSanguineo,
)
from src.models.corp.empresa import Empresa
from datetime import datetime, time, timezone, timedelta
from sqlalchemy import func



class PacienteRepository(IRepository[Paciente]):
    """Acesso a dados de Paciente.

    TRANSAÇÃO: todo commit/flush/rollback do domínio Paciente vive AQUI,
    nunca no service. Os métodos de escrita aceitam `commit`:
      - commit=True  (padrão): confirma a transação.
      - commit=False: só faz flush (gera ids, detecta violação de
        constraint) e deixa a transação aberta para o chamador -- usado
        quando a escrita faz parte de uma operação maior e atômica
        (ex: abrir consulta + cadastrar paciente, ou acao_sensivel, que
        comita junto com o log de auditoria).
    """

    # ------------------------------------------------------------ transação
    def confirmar(self, commit: bool = True) -> None:
        """Fecha a unidade de trabalho: commit, ou só flush se o chamador
        vai comitar depois."""
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
        """ALTERADO: passou a exigir id_empresa. Sem esse filtro, um
        usuário autenticado em qualquer empresa poderia acessar/editar
        o paciente de outra empresa só sabendo (ou adivinhando) o UUID
        -- isolamento de tenant tem que estar no repository, não
        confiado à camada de rota."""
        return Paciente.query.filter_by(uuid=uuid, id_empresa=id_empresa).first()

    def find_por_cpf_hash(self, cpf_hash: str, id_empresa: int) -> Optional[Paciente]:
        """Busca por CPF via hash HMAC-SHA256 (determinístico), não pelo
        valor cifrado com AES-256-GCM (ver nota original mantida).

        ALTERADO: escopado por id_empresa -- o mesmo CPF pode existir
        legitimamente como pacientes distintos em empresas diferentes;
        buscar sem esse filtro vazaria a existência do paciente entre
        tenants, mesmo sem vazar PII."""
        pessoal = PacienteDadosPessoais.query.filter_by(
            cpf_hash=cpf_hash, id_empresa=id_empresa
        ).first()
        return pessoal.paciente if pessoal else None

    # --------------------------------------------------------------- escrita
    def save(self, entity: Union[Paciente, PacienteDadosPessoais], commit: bool = True):
        """Persiste Paciente OU PacienteDadosPessoais (mesma sessão, mesma
        transação). Ver `commit` na docstring da classe."""
        db.session.add(entity)
        self.confirmar(commit)
        return entity

    def delete(self, id: int, commit: bool = True) -> bool:
        e = self.find_by_id(id)
        if not e:
            return False
        db.session.delete(e)
        self.confirmar(commit)
        return True

    def registrar_auditoria(self, id_usuario: int, acao: str, uuid_paciente: str,
                            commit: bool = True) -> None:
        """Linha em RegistroAuditoria sobre um paciente. Import local: o
        domínio de auditoria não deve ser carregado junto com o
        repository de paciente em toda importação."""
        from src.models.auditoria import RegistroAuditoria
        db.session.add(RegistroAuditoria(
            id_usuario=id_usuario,
            acao=acao,
            entidade="paciente",
            entidade_uuid=uuid_paciente,
        ))
        self.confirmar(commit)

    def find_all(self, id_empresa: int) -> List[Paciente]:
        """ALTERADO: escopado por empresa -- sem isso, `listar()` do
        service devolveria pacientes de TODAS as empresas pra qualquer
        usuário logado."""
        return Paciente.query.filter_by(id_empresa=id_empresa).all()

    def find_all_param(self, id_empresa: int, offset: int = 0, status: str = None,
                        sexo_biologico: str = None):
        """NOVO: listagem paginada para o endpoint de listagem enxuta
        (to_dict_few). Segue o mesmo padrão usado em UsuarioRepository.

        Filtro por nome (`nome`) e por cpf ficam de fora por ora: ambos
        vivem em PacienteDadosPessoais cifrados com AES-256-GCM -- não dá
        pra fazer ILIKE/igualdade direta no banco sobre coluna cifrada.
        Nome exigiria busca em memória (descriptografar e comparar) ou
        um índice cego (blind index) dedicado; CPF já tem esse mecanismo
        via cpf_hash (ver find_por_cpf_hash) mas ele é busca exata, não
        paginada por padrão -- se precisar disso no mesmo endpoint,
        me avisa que desenhamos separado.
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
            .limit(8)
            .all()
        )

    def _limites_do_dia_utc(self, id_empresa: int):
        """Calcula o início e o fim do dia de HOJE no fuso horário da
        empresa (ver Empresa.fuso_horario), já convertidos para UTC --
        necessário porque `criado_em` é gravado em UTC, então a
        comparação no banco precisa acontecer nesse mesmo referencial.

        Sem isso, "hoje" seria calculado em UTC puro, o que desloca a
        virada do dia em até algumas horas em relação ao horário local
        da empresa (ex: consultas perto da meia-noite local caindo no
        dia errado da contagem).
        """
        empresa = db.session.get(Empresa, id_empresa)
        fuso = empresa.fuso_horario if empresa else timezone.utc

        agora_local = datetime.now(fuso)
        hoje_local = agora_local.date()

        inicio_local = datetime.combine(hoje_local, time.min, tzinfo=fuso)
        fim_local = datetime.combine(hoje_local, time.max, tzinfo=fuso)

        return inicio_local.astimezone(timezone.utc), fim_local.astimezone(timezone.utc)

    def count_pacientes_hoje(self, id_empresa: int) -> int:
        """SIMPLIFICADO: filtra direto por Paciente.id_empresa, sem JOIN
        com Usuario -- o JOIN via cadastrado_por era um contorno pro fato
        de Paciente não ter id_empresa próprio (agora tem).

        ALTERADO: "hoje" agora é calculado no fuso da empresa (ver
        _limites_do_dia_utc), não em UTC direto.
        """
        inicio_dia, fim_dia = self._limites_do_dia_utc(id_empresa)

        return (
            db.session.query(func.count(Paciente.id))
            .filter(Paciente.id_empresa == id_empresa)
            .filter(Paciente.criado_em >= inicio_dia)
            .filter(Paciente.criado_em < fim_dia)
            .scalar()
        )

    def count_pacientes(self, id_empresa: int) -> int:
        return (
            db.session.query(func.count(Paciente.id))
            .filter(Paciente.id_empresa == id_empresa)
            .scalar()
        )