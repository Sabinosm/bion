# Bion API

Documentação na pasta doc
Pasta setup e setup.py -> teste próprio do projeto, baixando o database, o .env ( simplificado e com dados aleatórios (google não funciona, nem relacionados a IA))


Funcionalidades Implementadas

Empresa

Cadastrar empresa com seu admin fundador (super admin) em transação única
Atualizar dados cadastrais da empresa (campos autogerenciáveis, DPO e região por CEP)
Verificar se um CNPJ já está cadastrado
Verificar se um CNES já está cadastrado

Liberação de protocolos
5. Listar o catálogo de protocolos cruzado com a liberação da empresa
6. Liberar ou bloquear protocolo e definir política (obrigatório/opcional), respeitando o mínimo de 2 ativos
7. Definir o protocolo padrão institucional por escopo (triagem, consulta ou ambos)

Configurações do usuário
8. Consultar configurações (aparência e idioma), com criação sob demanda
9. Atualizar tema, tamanho da fonte e idioma por merge parcial
10. Habilitar protocolo como favorito
11. Desabilitar protocolo (com proteção de obrigatórios e padrão institucional)
12. Definir protocolo padrão pessoal por escopo
13. Remover protocolo padrão pessoal
14. Resolver o protocolo padrão da consulta por cadeia de fallback (pessoal → institucional → primeiro liberado)

Regiões geográficas
15. Listar regiões com paginação e filtro por tipo de jurisdição
16. Consultar região por código IBGE com criação automática do município (IBGE, SIDRA e centroide)
17. Resolver endereço por CEP (BrasilAPI com fallback ViaCEP e cache)
18. Obter região geográfica a partir do CEP

Auditoria
19. Registrar alterações sensíveis com step-up e log de alteração (@acao_sensivel)
20. Registrar leituras sensíveis e acessos negados no log de acesso
21. Consultar log de acessos com janela máxima de 7 dias
22. Consultar log de alterações com filtros
23. Resumo de auditoria por profissional (filtros por nome, função, admin e ação)
24. Detalhe de auditoria por profissional com paginação por cursor

Sessão e acesso
25. Controle de acesso por papéis (admin, médico, enfermeiro, super admin) com revalidação no banco
26. Bloqueio de leitura sensível quando a senha mudou desde o login (@requer_senha_atualizada)

Estatísticas
27. Dashboards de equipe e consultas: efetivo ativo, engajamento, volume, taxa de conclusão, tempo médio e tendência de eficiência
28. Dashboards clínicos e epidemiológicos: doenças crônicas, alergias, interações medicamentosas, incidência por região, CIDs, queixas, qualidade da IA e medicamentos por classe