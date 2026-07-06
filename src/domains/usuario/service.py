"""
Regras de negocio do dominio Usuario.

Mantidos `criar` e `desativar` do original, e adicionados `atualizar` e
`ativar` -- o controller original tinha uma rota GET /editar (so
renderizava o form) sem nenhum POST correspondente no service; como
service e controller foram unificados, o metodo de update precisava
existir de fato.
"""

from flask import  jsonify, session
from src.core.security import ph, aes_encrypt, hmac_sha256
from src.core.exceptions import RecursoNaoEncontradoError, ConflictoError, DadosInvalidosError
from .repository import UsuarioRepository
import json
import re



CAMPOS_ATUALIZAVEIS = {
    "nome_completo", "email", "telefone", "tipo_usuario", "atributos_profissionais_json",
}


class UsuarioService:

    def __init__(self):
        self.repo = UsuarioRepository()

    def buscar_por_uuid(self, uuid: str):
        u = self.repo.find_by_uuid(uuid)
        if not u:
            raise RecursoNaoEncontradoError(f"Usuário não encontrado: {uuid}")
        return u

    def listar(self):
        return self.repo.find_all()

    def listar_por_empresa(self, id_empresa: int):
        return self.repo.find_por_empresa(id_empresa)

    def criar(self, dados: dict):
        from src.database.usuarios import Usuario
        
        dados_tratados, atributos = self.validacao_input(dados)

        if self.repo.find_by_login(dados_tratados["user_login"]):
            raise ConflictoError("Login já em uso.")
        if self.repo.find_by_email(dados_tratados["email"]):
            raise ConflictoError("E-mail já em uso.")
        cpf_hash = hmac_sha256(dados["cpf"])
        if self.repo.find_by_cpf_hash(cpf_hash):
            raise ConflictoError("CPF já cadastrado para outro usuário.")

    # O cpf sendo salvo em hash, nao sei ainda se vai continuar assim
        u = Usuario(
            id_empresa=dados["id_empresa"],
            nome_completo=dados["nome_completo"],
            cpf=aes_encrypt(dados["cpf"]),
            email=dados["email"],
            telefone=dados.get("telefone"),
            user_login=dados["user_login"],
            tipo_usuario=dados["tipo_usuario"],
            hash_senha=ph.hash(dados["senha"]),
            atributos_profissionais_json=atributos,
        )
        
        
        return self.repo.save(u)


    # TODO fazer 2fa aqui 
    # TODO aviso ao fazer essas ações
    
    def atualizar(self, uuid: str, dados: dict):
        u = self.buscar_por_uuid(uuid)
        for campo in CAMPOS_ATUALIZAVEIS:
            if campo in dados:
                setattr(u, campo, dados[campo])
        if "senha" in dados and dados["senha"]:
            u.hash_senha = ph.hash(dados["senha"])
        return self.repo.save(u)

    def desativar(self, uuid: str):
        u = self.buscar_por_uuid(uuid)
        u.status = "inativo"
        return self.repo.save(u)

    def ativar(self, uuid: str):
        u = self.buscar_por_uuid(uuid)
        u.status = "ativo"
        return self.repo.save(u)

    
    def validacao_input(self, dados: dict):
        if not isinstance(dados, dict):
            raise DadosInvalidosError("Os dados fornecidos devem ser um dicionário.")

        # 1. Definição dos campos obrigatórios base
        obrigatorios = ["id_empresa", "nome_completo", "cpf", "email", "user_login", "tipo_usuario", "senha"]
        
        # Valida o tipo de usuário logo no início
        tipo_usuario = str(dados.get("tipo_usuario", "")).strip().lower()
        if tipo_usuario not in ("medico", "enfermeiro", "admin"):
            raise DadosInvalidosError("Tipo de usuário inválido. Deve ser 'medico', 'enfermeiro' ou 'admin'.")

        # 2. Adiciona os campos obrigatórios específicos por profissão
        if tipo_usuario == "medico":
            obrigatorios.extend(["numero-crm", "uf-crm", "rqe"])
        elif tipo_usuario == "enfermeiro":
            obrigatorios.extend(["numero-coren", "uf-coren", "especialidade"])

        # 3. Verifica se algum campo está faltando ou veio apenas com espaços em branco
        faltando = [campo for campo in obrigatorios if not str(dados.get(campo, "")).strip()]
        if faltando:
            raise DadosInvalidosError(f"Campos obrigatórios ausentes ou vazios: {', '.join(faltando)}")

        # --- 4. VALIDAÇÕES DE CONTEÚDO (Regex e Formatos) ---

        # ID Empresa: Garante que são apenas dígitos
        id_empresa_str = str(dados.get("id_empresa")).strip()
        if not id_empresa_str.isdigit():
            raise DadosInvalidosError("O 'id_empresa' deve conter apenas números.")

        # Nome Completo: Apenas letras e espaços (aceita acentos e Ç)
        nome = str(dados.get("nome_completo")).strip()
        if not re.match(r"^[a-zA-ZáàâãéèêíïóôõöúçÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ\s]+$", nome):
            raise DadosInvalidosError("O 'nome_completo' deve conter apenas letras e espaços.")

        # CPF: Remove pontos/traços e valida se restaram exatamente 11 números
        cpf_limpo = re.sub(r"\D", "", str(dados.get("cpf")))
        if len(cpf_limpo) != 11:
            raise DadosInvalidosError("O 'cpf' deve conter exatamente 11 dígitos numéricos.")

        # Email: Validação de formato padrão de email
        email = str(dados.get("email")).strip()
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            raise DadosInvalidosError("O formato do 'email' é inválido.")

        # Validações condicionais avançadas
        if tipo_usuario == "medico":
            uf_crm = str(dados.get("uf-crm")).strip().upper()
            num_crm = str(dados.get("numero-crm")).strip()
            
            if not re.match(r"^[A-Z]{2}$", uf_crm):
                raise DadosInvalidosError("UF do CRM inválida. Deve conter 2 letras maiúsculas.")
            if not num_crm.isdigit():
                raise DadosInvalidosError("Número do CRM inválido. Deve conter apenas números.")
                
        elif tipo_usuario == "enfermeiro":
            uf_coren = str(dados.get("uf-coren")).strip().upper()
            num_coren = str(dados.get("numero-coren")).strip()
            especialidade = str(dados.get("especialidade")).strip()

            if not re.match(r"^[A-Z]{2}$", uf_coren):
                raise DadosInvalidosError("UF do COREN inválida. Deve conter 2 letras maiúsculas.")
            if not num_coren.isdigit():
                raise DadosInvalidosError("Número do COREN inválido. Deve conter apenas números.")
            if not re.match(r"^[a-zA-ZáàâãéèêíïóôõöúçÁÀÂÃÉÈÊÍÏÓÔÕÖÚÇ\s]+$", especialidade):
                raise DadosInvalidosError("A 'especialidade' deve conter apenas letras e espaços.")

        # --- 5. PROCESSAMENTO E CRIPTOGRAFIA ---
        # Agora que tudo está limpo e validado, fazemos o tratamento final com segurança
        try:
            dados_tratados = {
                "id_empresa": int(id_empresa_str),
                "nome_completo": nome,
                "cpf": aes_encrypt(cpf_limpo),  # Criptografa o CPF limpo (apenas os 11 números)
                "email": email,
                "telefone": str(dados.get("telefone", "")).strip(),
                "user_login": str(dados.get("user_login")).strip(),
                "tipo_usuario": tipo_usuario,
                "hash_senha": ph.hash(str(dados["senha"]))
            }
            
            # Insere as chaves extras dependendo do tipo
            if tipo_usuario == "medico":
                atributos= json.dumps({
                    "numero-crm": num_crm,
                    "uf-crm": uf_crm,
                    "rqe": str(dados.get("rqe", "")).strip()
                })
            elif tipo_usuario == "enfermeiro":
                atributos= json.dumps({
                    "numero-coren": num_coren,
                    "uf-coren": uf_coren,
                    "especialidade": especialidade
                })
                
            return dados_tratados, atributos

        except Exception as e:
            raise DadosInvalidosError(f"Erro interno ao processar tipos de dados: {str(e)}")
            
        except ValueError as e:
            raise DadosInvalidosError("Tipos de dados inválidos.")
    
    def reset_2fa(self, uuid):
        from src.database.usuarios import CredencialWebAuthn
        from src.database import db
        """
        Remove todas as credenciais WebAuthn do usuário. Próximo login dele
        (via senha) vai cair em mfa_pendente, mas sem credencial cadastrada —
        então precisamos tratar esse caso: sessão fica numa espécie de
        'onboarding parcial' só pra recadastrar o WebAuthn.
        """
        usuario = self.repo.find_by_uuid(uuid)
        
        if not usuario:
            return jsonify({"erro": "usuario_nao_encontrado"}), 404
    
        # Confere que o admin só reseta usuário da própria empresa
        if usuario.uuid_empresa != session.get("uuid_empresa"):
            return jsonify({"erro": "acesso_negado"}), 403
    
        CredencialWebAuthn.query.filter_by(uuid_usuario=uuid).delete()
    
        # Reaproveita o mesmo campo de onboarding: assim o próximo login força
        # a passar pela etapa de cadastro de WebAuthn novamente (senha permanece)
        usuario.onboarding_pendente = True
        db.session.commit()
    
        return jsonify({"status": "2fa_resetado", "uuid_usuario": uuid}), 200
    
    def reset_total(self,uuid):
        from src.database.usuarios import CredencialWebAuthn
        from src.database import db
        
        """
        Reset mais drástico: invalida a senha também. Usuário precisa passar
        pelo fluxo inteiro de novo (Google -> definir senha -> WebAuthn).
        Útil se há suspeita de conta comprometida, não só dispositivo perduzido.
        """
        usuario = self.repo.find_by_uuid(uuid)
        if not usuario:
            return jsonify({"erro": "usuario_nao_encontrado"}), 404
    
        if usuario.uuid_empresa != session.get("uuid_empresa"):
            return jsonify({"erro": "acesso_negado"}), 403
    
        CredencialWebAuthn.query.filter_by(uuid_usuario=uuid).delete()
        usuario.hash_senha = None
        usuario.onboarding_pendente = True
        db.session.commit()
    
        return jsonify({"status": "reset_completo", "uuid_usuario": uuid}), 200  

        