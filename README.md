# Bion API

API REST (JSON-only) para gestão hospitalar multi-tenant: pacientes, atendimentos,
triagem (Manchester/NEWS2), protocolos clínicos e suporte à decisão por IA.
## Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # preencha SECRET_KEY, DATABASE_URL, AES_KEY, HMAC_KEY

# gerar uma AES_KEY válida (32 bytes em base64):
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"

flask --app app db upgrade      # aplica migrations (após configurar Flask-Migrate)
flask --app app run             # http://localhost:5000
```

## Rodando os testes

```bash
pip install -r requirements.txt
pytest tests/ -v
```

A suíte cobre: motor de protocolos (unitário), segurança/criptografia (unitário),
autenticação e fluxo clínico completo (integração, via `test_client()` do Flask).

## Estrutura de pastas

```
src/
├── config/database.py       # configuração (banco, sessão, segredos via .env)
├── database/                 # modelos SQLAlchemy, um arquivo por domínio
│   ├── corp.py                (Empresa, RegiaoGeografica)
│   ├── usuarios.py             (Usuario, Configuracao)
│   ├── paciente.py             (Paciente, PacientePessoal, Alergia, ...)
│   ├── catalogo.py             (CatalogoExames, CatalogoMedicamentos, ...)
│   ├── protocolos.py           (ProtocoloCatalogo, OutputBion, ...)
│   ├── clinico.py              (Consulta, Atendimento, SinalVital, ...)
│   └── auditoria.py            (LogAcesso, LogAlteracao)
├── core/                     # segurança e infraestrutura transversal
│   ├── security.py             (Argon2id, AES-256-GCM, HMAC-SHA256)
│   ├── session.py              (decorators de autenticação/autorização)
│   ├── exceptions.py
│   ├── interfaces.py
│   └── responses.py
├── domains/                  # domínios de negócio (repository/service/controller)
│   ├── auth/                   (login/logout, sessão)
│   ├── usuario/
│   ├── empresa/
│   ├── regiao/
│   ├── configuracao/
│   ├── paciente/                (repositories.py, services.py, controllers/)
│   ├── catalogo/                (exames + medicamentos)
│   ├── atendimento/              (Consulta, Atendimento, Prescrição)
│   ├── protocolos_ia/           (ProtocoloCatalogo, OutputBion, motor/)
│   │   └── motor/                (Strategy: MTS, NEWS2, Personalizado + LLM)
│   └── auditoria/
└── main.py                   # app factory (registra blueprints e error handlers)

app.py                        # ponto de entrada WSGI
tests/
├── conftest.py                # fixtures compartilhadas
├── unit/                      # motor de protocolos, segurança
└── integration/               # autenticação, fluxo clínico completo
```

## Correções aplicadas em relação ao bion.zip original

Durante a reestruturação, os seguintes bugs (presentes no código original e
confirmados por teste) foram corrigidos:

1. **Sessão de login inconsistente**: o login gravava `session["usuario_uuid"]`,
   mas os decorators de autorização liam `session.get("usuario_id")` — nenhuma
   rota protegida reconhecia o usuário como autenticado. Corrigido em
   `src/core/session.py` e `src/domains/auth/controllers.py`.

2. **Motor MTS quebrava em runtime**: `ResultadoTriagem` não tinha os campos
   `discriminadores_avaliados`/`discriminante_determinante` que `mts.py` já
   tentava preencher. Corrigido em `src/domains/protocolos_ia/motor/base.py`.

3. **Motor NEWS2 quebrava em runtime**: mesmo problema, com campos diferentes
   (`nivel_risco_news2`, `score_news2`, `subscores_news2`), além de `InputTriagem`/
   `InputConsulta` não terem o atributo `sinais_vitais` que o motor lia.

4. **`OutputBionService.buscar_output_triagem` não existia**: a rota
   `/api/ia/output-triagem/<consulta_uuid>` quebrava com `AttributeError`.
   Implementado com navegação real Consulta → Atendimento → ColetaClinica →
   InputProtocolo → OutputBion.

5. **Busca por CPF cifrado nunca encontrava o registro**: como AES-256-GCM usa
   nonce aleatório, `aes_encrypt(mesmo_cpf)` nunca repete o mesmo ciphertext —
   a checagem de duplicidade de CPF (`unique=True` sobre o valor cifrado) e a
   busca por CPF eram inoperantes por design. Corrigido com um índice
   determinístico separado (`cpf_hash`, HMAC-SHA256) usado apenas para busca/
   unicidade; o valor exibível continua cifrado com AES-256-GCM em `cpf`.
   **Esse bug foi encontrado pela própria suíte de testes** (`test_cpf_duplicado_gera_conflito`).

6. **`ProtocoloCatalogo` e `OutputBion` eram stubs incompletos**: `ProtocoloFactory`
   já acessava `catalogo.sigla`, e `ia/controller.py` já acessava
   `output.output_ia_json`, mas nenhum dos dois campos existia nos models
   originais. Completados com todo o schema (ver `src/database/protocolos.py`).

7. **`SESSION_COOKIE_SECURE = False` em produção**: anulava a proteção do
   cookie de sessão mesmo em conexões HTTPS. Corrigido para `True` em
   `src/config/database.py`.

8. **Parsing de markdown fences quebrado no motor LLM**: `raw.lstrip("```json")`
   remove caracteres do conjunto `{`,`j`,`s`,`o`,`n}`, não o prefixo literal.
   Corrigido em `src/domains/protocolos_ia/motor/llm_motor.py`.

Módulos que eram apenas stubs no projeto original (`empresa`, `regiao`,
`configuracao`, `consentimento`, `dados_clinicos`, `medicamento`, `exame`,
`prescricao`, `catalogo_modulos`, `catalogo_mts`) foram completados com
model, repository, service e rotas funcionais.

## Autenticação

```
POST /api/auth/login   {"login": "...", "senha": "..."}
GET  /api/auth/me
POST /api/auth/logout
```

Sessão via cookie httpOnly (`SESSION_COOKIE_SAMESITE=Lax`), válida por 8h
(`PERMANENT_SESSION_LIFETIME`). Perfis: `admin`, `medico`, `enfermeiro`
(ver decorators em `src/core/session.py`).
