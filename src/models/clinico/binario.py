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
    if possui is None:
        return "nao-coletado"
    return "preenchido" if possui else "nega"


class Binario:
    def __init__(self, itens: Optional[Dict[str, dict]] = None):
        self._itens: Dict[str, dict] = {}
        for secao, item in (itens or {}).items():
            self._validar(secao, item.get("estado"))
            self._itens[secao] = {k: v for k, v in item.items() if v is not None}

    @classmethod
    def de_json(cls, dados: Optional[dict]) -> "Binario":
        itens = {}
        for secao in SECOES_BINARIO:
            item = (dados or {}).get(secao)
            if item is not None:
                itens[secao] = dict(item)
        return cls(itens)

    @classmethod
    def de_atendimento(cls, atendimento) -> "Binario":
        return cls.de_json(getattr(atendimento, "binario", None))

    def conferida(self, secao: str) -> bool:
        item = self._itens.get(secao)
        return item is not None and item["estado"] != ESTADO_REVISAO

    def confirmada_manual(self, secao: str) -> bool:
        return self.conferida(secao) and self.origem(secao) == ORIGEM_MANUAL

    def estado(self, secao: str) -> Optional[str]:
        item = self._itens.get(secao)
        return item["estado"] if item else None

    def origem(self, secao: str) -> Optional[str]:
        item = self._itens.get(secao)
        return (item.get("origem") or ORIGEM_MANUAL) if item else None

    def possui(self, secao: str) -> Optional[bool]:
        return _POSSUI.get(self.estado(secao))

    def foi_reconciliada(self, secao: str) -> bool:
        return bool(self._itens.get(secao, {}).get("reconciliado"))

    def revisao(self, secao: str) -> Optional[dict]:
        item = self._itens.get(secao)
        if not item or item["estado"] != ESTADO_REVISAO:
            return None
        return {"motivo": item.get("motivo"), "estado_anterior": item.get("anterior")}

    @property
    def pendentes(self) -> List[str]:
        return [s for s in SECOES_BINARIO if not self.conferida(s)]

    @property
    def requer_revisao(self) -> List[str]:
        return [s for s in SECOES_BINARIO if self.estado(s) == ESTADO_REVISAO]

    @property
    def completo(self) -> bool:
        return not self.pendentes

    def registrar(self, secao: str, estado: str) -> None:
        self._validar(secao, estado)
        if estado == ESTADO_REVISAO:
            raise ValueError("requer-revisao não é uma confirmação do profissional")
        self._itens[secao] = {"estado": estado}

    def derivar(self, secao: str, anterior: Optional[str], tem_registro_ativo: bool) -> bool:
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
        if (
            not self.conferida(secao)
            or self.estado(secao) == "preenchido"
            or not tem_registro_ativo
        ):
            return False
        self._itens[secao]["estado"] = "preenchido"
        self._itens[secao]["reconciliado"] = True
        return True

    def para_json(self) -> dict:
        saida = {"v": VERSAO}
        for secao in SECOES_BINARIO:
            if secao in self._itens:
                saida[secao] = dict(self._itens[secao])
        return saida

    def to_dict(self, secao: str) -> dict:
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
