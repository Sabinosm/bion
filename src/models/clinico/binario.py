"""Binário (Bloco 2/3) -- objeto PURO, sem tabela.

O estado da conferência mora numa coluna JSON do próprio Atendimento
(`atendimento.binario`). Este objeto lê e escreve esse JSON e concentra as
regras: o resto do código nunca mexe no dict cru.

PAPEL: no 1º atendimento o binário registra as escolhas do profissional. Nos
seguintes ele passa a refletir "como estão os dados do paciente": é DERIVADO
dos registros do paciente (a verdade) cruzados com a última conferência.

FORMATO DO JSON (guardamos o TEXTO, não 1/0, porque são estados reais):

    {"v": 1,
     "alergias":       {"estado": "nega"},
     "medicamentos":   {"estado": "preenchido", "origem": "automatico"},
     "tipo_sanguineo": {"estado": "nao-coletado"},
     "doenca_cronica": {"estado": "requer-revisao", "origem": "automatico",
                        "motivo": "dado-novo", "anterior": "nega"}}

  chave ausente    -> seção pendente (nada conferido nem derivado)
  "preenchido"     -> o paciente possui o dado   (possui = True)
  "nega"           -> o paciente nega o dado     (possui = False)
  "nao-coletado"   -> não foi possível coletar   (possui = None)
  "requer-revisao" -> o dado do paciente mudou desde a última conferência
                      (ex: alergia inserida fora do atendimento). NÃO vale:
                      conta como PENDENTE no gate, o InputModel não o aceita e
                      o front deve desmarcar a seção até o profissional
                      confirmar.

  origem: ausente = "manual" (profissional confirmou NESTE atendimento);
          "automatico" = derivado do paciente na abertura. Automático
          consistente (nada mudou) vale; o profissional pode sobrescrevê-lo.
  motivo: só em requer-revisao: "dado-novo" | "registro-removido".
  anterior: estado da última conferência (só em requer-revisao).
  reconciliado: true quando `reconciliar` promoveu a seção a "preenchido".

INSERT-ONLY MANUAL: `registrar` recusa uma seção já confirmada MANUALMENTE
(ConflictoError, 409). Seção automática ou em requer-revisao é sobrescrita
pela confirmação do profissional, sem 409.
"""

from typing import Dict, List, Optional

SECOES_BINARIO = ("alergias", "medicamentos", "tipo_sanguineo", "doenca_cronica")
ESTADOS_CONFIRMAVEIS = ("preenchido", "nega", "nao-coletado")
ESTADO_REVISAO = "requer-revisao"
ESTADOS = ESTADOS_CONFIRMAVEIS + (ESTADO_REVISAO,)
ORIGEM_MANUAL = "manual"
ORIGEM_AUTOMATICO = "automatico"
MOTIVOS_REVISAO = ("dado-novo", "registro-removido")
VERSAO = 1

_POSSUI = {"preenchido": True, "nega": False, "nao-coletado": None, ESTADO_REVISAO: None}


def estado_de(possui: Optional[bool]) -> str:
    """Tradução inversa: possui (True/False/None) -> texto do estado."""
    if possui is None:
        return "nao-coletado"
    return "preenchido" if possui else "nega"


class Binario:

    def __init__(self, itens: Optional[Dict[str, dict]] = None):
        self._itens: Dict[str, dict] = {}
        for secao, item in (itens or {}).items():
            self._validar(secao, item.get("estado"))
            self._itens[secao] = {k: v for k, v in item.items() if v is not None}

    # ------------------------------------------------------------ construção
    @classmethod
    def de_json(cls, dados: Optional[dict]) -> "Binario":
        """Aceita None/{} (atendimento sem nenhuma seção conferida). Ignora a
        chave de versão e chaves desconhecidas; estado inválido é erro de
        integridade (o JSON só é escrito por este objeto)."""
        itens = {}
        for secao in SECOES_BINARIO:
            item = (dados or {}).get(secao)
            if item is not None:
                itens[secao] = dict(item)
        return cls(itens)

    @classmethod
    def de_atendimento(cls, atendimento) -> "Binario":
        return cls.de_json(getattr(atendimento, "binario", None))

    # ---------------------------------------------------------------- leitura
    def conferida(self, secao: str) -> bool:
        """Tem estado válido (manual ou automático consistente). requer-revisao
        NÃO conta: é pendência."""
        item = self._itens.get(secao)
        return item is not None and item["estado"] != ESTADO_REVISAO

    def confirmada_manual(self, secao: str) -> bool:
        """Confirmada pelo profissional neste atendimento (não pode ser refeita)."""
        return self.conferida(secao) and self.origem(secao) == ORIGEM_MANUAL

    def estado(self, secao: str) -> Optional[str]:
        """Texto do estado, ou None se pendente."""
        item = self._itens.get(secao)
        return item["estado"] if item else None

    def origem(self, secao: str) -> Optional[str]:
        item = self._itens.get(secao)
        return (item.get("origem") or ORIGEM_MANUAL) if item else None

    def possui(self, secao: str) -> Optional[bool]:
        """True=preenchido, False=nega, None=não coletado, pendente OU
        requer-revisao (use `conferida` para distinguir)."""
        return _POSSUI.get(self.estado(secao))

    def foi_reconciliada(self, secao: str) -> bool:
        return bool(self._itens.get(secao, {}).get("reconciliado"))

    def revisao(self, secao: str) -> Optional[dict]:
        """Detalhes de uma seção em requer-revisao, ou None."""
        item = self._itens.get(secao)
        if not item or item["estado"] != ESTADO_REVISAO:
            return None
        return {"motivo": item.get("motivo"), "estado_anterior": item.get("anterior")}

    @property
    def pendentes(self) -> List[str]:
        """Sem estado OU em requer-revisao: o gate só abre sem nenhuma."""
        return [s for s in SECOES_BINARIO if not self.conferida(s)]

    @property
    def requer_revisao(self) -> List[str]:
        return [s for s in SECOES_BINARIO if self.estado(s) == ESTADO_REVISAO]

    @property
    def completo(self) -> bool:
        return not self.pendentes

    # ----------------------------------------------------------------- escrita
    def registrar(self, secao: str, estado: str) -> None:
        """Confirmação MANUAL do profissional. Pode ser refeita quantas vezes
        for preciso enquanto o atendimento estiver em andamento (o guard do
        service garante isso): a última confirmação vence e sobrescreve
        qualquer estado anterior (manual, automático, requer-revisão, reconciliado)."""
        self._validar(secao, estado)
        if estado == ESTADO_REVISAO:
            raise ValueError("requer-revisao não é uma confirmação do profissional")
        self._itens[secao] = {"estado": estado}

    def derivar(self, secao: str, anterior: Optional[str], tem_registro_ativo: bool) -> bool:
        """Deriva a seção NA ABERTURA do atendimento: cruza a última conferência
        (`anterior`: estado confirmado, ou None se nunca houve) com os registros
        ativos do paciente. Só age em seção ainda sem estado. Devolve True se
        gravou algo.

          anterior     registro ativo   resultado
          preenchido   sim              preenchido  (automatico)
          preenchido   não              requer-revisao / registro-removido
          nega         sim              requer-revisao / dado-novo
          nega         não              nega        (automatico)
          nao-coletado sim              requer-revisao / dado-novo
          nao-coletado não              (pendente: não registrado não vira nega)
          nunca houve  sim              requer-revisao / dado-novo
          nunca houve  não              (pendente)
        """
        if secao in self._itens:
            return False
        if anterior == "preenchido":
            if tem_registro_ativo:
                self._itens[secao] = {"estado": "preenchido", "origem": ORIGEM_AUTOMATICO}
            else:
                self._revisao(secao, "registro-removido", anterior)
            return True
        if anterior == "nega":
            if tem_registro_ativo:
                self._revisao(secao, "dado-novo", anterior)
            else:
                self._itens[secao] = {"estado": "nega", "origem": ORIGEM_AUTOMATICO}
            return True
        if tem_registro_ativo:
            self._revisao(secao, "dado-novo", anterior)
            return True
        return False

    def _revisao(self, secao: str, motivo: str, anterior: Optional[str]) -> None:
        item = {"estado": ESTADO_REVISAO, "origem": ORIGEM_AUTOMATICO, "motivo": motivo}
        if anterior:
            item["anterior"] = anterior
        self._itens[secao] = item

    def reconciliar(self, secao: str, tem_registro_ativo: bool) -> bool:
        """Dentro do MESMO atendimento (fim do atendimento / antes do envio à
        IA): promove "nega"/"nao-coletado" a "preenchido" quando o paciente
        passou a ter registro ativo (ex: alergia pela rota granular). Mantém a
        origem e marca "reconciliado". Pendente, requer-revisao, já
        "preenchido" ou sem registro: não mexe. True se mudou."""
        if not self.conferida(secao) or self.estado(secao) == "preenchido" or not tem_registro_ativo:
            return False
        self._itens[secao]["estado"] = "preenchido"
        self._itens[secao]["reconciliado"] = True
        return True

    # ------------------------------------------------------------ serialização
    def para_json(self) -> dict:
        """Dict novo a cada chamada (o SQLAlchemy só percebe a mudança da
        coluna JSON se for ATRIBUÍDO um objeto novo, não mutado)."""
        saida = {"v": VERSAO}
        for secao in SECOES_BINARIO:
            if secao in self._itens:
                saida[secao] = dict(self._itens[secao])
        return saida

    def to_dict(self, secao: str) -> dict:
        """Resposta da API para uma seção JÁ conferida (manual ou automática)."""
        return {
            "secao": secao,
            "conferida": True,
            "estado": self._itens[secao]["estado"],
            "possui": self.possui(secao),
            "origem": self.origem(secao),
            "reconciliado": self.foi_reconciliada(secao),
        }

    @staticmethod
    def _validar(secao: str, estado) -> None:
        if secao not in SECOES_BINARIO:
            raise ValueError(f"Seção do binário inexistente: {secao}")
        if estado not in ESTADOS:
            raise ValueError(f"Estado do binário inválido para '{secao}': {estado!r}")

    def __repr__(self):
        return f"<Binario {self._itens}>"
