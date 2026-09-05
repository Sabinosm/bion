CREATE DATABASE `bion_testes` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */;

USE  `bion_testes` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */;

SET FOREIGN_KEY_CHECKS = 0;

-- bion_testes.catalogo_exames definition

CREATE TABLE `catalogo_exames` (
  `id_catalogo_exame` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_catalogo_exame` char(36) NOT NULL,
  `codigo_tuss` varchar(20) DEFAULT NULL,
  `nome_exame` varchar(255) NOT NULL,
  `tipo` enum('laboratorial','imagem','funcional','outro') DEFAULT NULL,
  `material` varchar(100) DEFAULT NULL,
  `jejum_horas` smallint(6) DEFAULT NULL,
  `observacoes` text DEFAULT NULL,
  `ativo` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id_catalogo_exame`),
  UNIQUE KEY `uuid_catalogo_exame` (`uuid_catalogo_exame`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.catalogo_fluxogramas_mts definition

CREATE TABLE `catalogo_fluxogramas_mts` (
  `id_fluxo_mts` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_fluxo_mts` char(36) NOT NULL,
  `codigo_fluxograma` varchar(50) NOT NULL,
  `nome_fluxograma` varchar(255) NOT NULL,
  `estrutura_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`estrutura_json`)),
  `status` enum('ativo','descontinuado') NOT NULL,
  PRIMARY KEY (`id_fluxo_mts`),
  UNIQUE KEY `uuid_fluxo_mts` (`uuid_fluxo_mts`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.catalogo_medicamentos definition

CREATE TABLE `catalogo_medicamentos` (
  `id_catalogo_medicamentos` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_catalogo_medicamentos` char(36) NOT NULL,
  `principio_ativo` varchar(255) DEFAULT NULL,
  `classe_farmaceutica` varchar(255) DEFAULT NULL,
  `nomes_comerciais_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`nomes_comerciais_json`)),
  `fonte_origem` varchar(255) DEFAULT NULL,
  `ultima_verificacao_em` datetime DEFAULT NULL,
  PRIMARY KEY (`id_catalogo_medicamentos`),
  UNIQUE KEY `uuid_catalogo_medicamentos` (`uuid_catalogo_medicamentos`),
  KEY `idx_catalogo_principio_ativo` (`principio_ativo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.catalogo_modulos definition

CREATE TABLE `catalogo_modulos` (
  `id_modulo` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_modulo` char(36) NOT NULL,
  `nome_modulo` varchar(255) NOT NULL,
  `descricao` text DEFAULT NULL,
  `tipo_modulo` enum('epidemiologico','comorbidade','faixa-etaria','institucional') NOT NULL,
  `campos_adicionados_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`campos_adicionados_json`)),
  `status` enum('ativo','inativo') NOT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_modulo`),
  UNIQUE KEY `uuid_modulo` (`uuid_modulo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.contraindicacoes definition

CREATE TABLE `contraindicacoes` (
  `id_contraindicacao` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_contraindicacao` varchar(36) NOT NULL,
  `nome` varchar(255) NOT NULL,
  `descricao` text DEFAULT NULL,
  PRIMARY KEY (`id_contraindicacao`),
  UNIQUE KEY `uq_contraindicacao_uuid` (`uuid_contraindicacao`),
  UNIQUE KEY `uq_contraindicacao_nome` (`nome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.indicacoes_terapeuticas definition

CREATE TABLE `indicacoes_terapeuticas` (
  `id_indicacao` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_indicacao` varchar(36) NOT NULL,
  `nome` varchar(255) NOT NULL,
  `sinonimos_busca_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`sinonimos_busca_json`)),
  PRIMARY KEY (`id_indicacao`),
  UNIQUE KEY `uq_indicacao_uuid` (`uuid_indicacao`),
  UNIQUE KEY `uq_indicacao_nome` (`nome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.loinc_sinal_vital definition

CREATE TABLE `loinc_sinal_vital` (
  `tipo_parametro` varchar(40) NOT NULL,
  `codigo_loinc` varchar(20) NOT NULL,
  `display_loinc` varchar(150) NOT NULL,
  `unidade_ucum` varchar(20) NOT NULL,
  PRIMARY KEY (`tipo_parametro`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.tipo_jurisdicao definition

CREATE TABLE `tipo_jurisdicao` (
  `id_tipo_jurisdicao` tinyint(4) NOT NULL,
  `codigo` varchar(30) NOT NULL,
  `display` varchar(100) NOT NULL,
  `fhir_jurisdiction_level` varchar(30) NOT NULL,
  PRIMARY KEY (`id_tipo_jurisdicao`),
  UNIQUE KEY `uq_codigo` (`codigo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.catalogo_medicamentos_contraindicacoes definition

CREATE TABLE `catalogo_medicamentos_contraindicacoes` (
  `id_catalogo` bigint(20) NOT NULL,
  `id_contraindicacao` bigint(20) NOT NULL,
  PRIMARY KEY (`id_catalogo`,`id_contraindicacao`),
  KEY `idx_cmc_contraindicacao` (`id_contraindicacao`),
  CONSTRAINT `fk_cmc_catalogo` FOREIGN KEY (`id_catalogo`) REFERENCES `catalogo_medicamentos` (`id_catalogo_medicamentos`),
  CONSTRAINT `fk_cmc_contraindicacao` FOREIGN KEY (`id_contraindicacao`) REFERENCES `contraindicacoes` (`id_contraindicacao`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.catalogo_medicamentos_indicacoes definition

CREATE TABLE `catalogo_medicamentos_indicacoes` (
  `id_catalogo` bigint(20) NOT NULL,
  `id_indicacao` bigint(20) NOT NULL,
  PRIMARY KEY (`id_catalogo`,`id_indicacao`),
  KEY `idx_cmi_indicacao` (`id_indicacao`),
  CONSTRAINT `fk_cmi_catalogo` FOREIGN KEY (`id_catalogo`) REFERENCES `catalogo_medicamentos` (`id_catalogo_medicamentos`),
  CONSTRAINT `fk_cmi_indicacao` FOREIGN KEY (`id_indicacao`) REFERENCES `indicacoes_terapeuticas` (`id_indicacao`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.interacoes_medicamentos definition

CREATE TABLE `interacoes_medicamentos` (
  `id_interacao` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_interacao` char(36) NOT NULL,
  `id_medicamento_A` bigint(20) DEFAULT NULL,
  `id_medicamento_B` bigint(20) DEFAULT NULL,
  `gravidade` varchar(50) DEFAULT NULL,
  `mecanismo_efeito` text DEFAULT NULL,
  `recomendacao` text DEFAULT NULL,
  PRIMARY KEY (`id_interacao`),
  UNIQUE KEY `uuid_interacao` (`uuid_interacao`),
  UNIQUE KEY `uq_interacao_par` (`id_medicamento_A`,`id_medicamento_B`),
  KEY `id_medicamento_A` (`id_medicamento_A`),
  KEY `id_medicamento_B` (`id_medicamento_B`),
  KEY `idx_interacao_medicamento_a` (`id_medicamento_A`),
  KEY `idx_interacao_medicamento_b` (`id_medicamento_B`),
  CONSTRAINT `interacoes_medicamentos_ibfk_1` FOREIGN KEY (`id_medicamento_A`) REFERENCES `catalogo_medicamentos` (`id_catalogo_medicamentos`),
  CONSTRAINT `interacoes_medicamentos_ibfk_2` FOREIGN KEY (`id_medicamento_B`) REFERENCES `catalogo_medicamentos` (`id_catalogo_medicamentos`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.regiao_geografica definition

CREATE TABLE `regiao_geografica` (
  `id_regiao_geografica` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_regiao_geografica` char(36) NOT NULL,
  `nome_regiao` varchar(255) NOT NULL,
  `codigo_ibge` varchar(20) DEFAULT NULL,
  `uf` char(2) DEFAULT NULL,
  `latitude_centroide` decimal(10,8) DEFAULT NULL,
  `longitude_centroide` decimal(11,8) DEFAULT NULL,
  `populacao_estimada` int(11) DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `id_tipo_jurisdicao` tinyint(4) NOT NULL,
  PRIMARY KEY (`id_regiao_geografica`),
  UNIQUE KEY `uuid_regiao_geografica` (`uuid_regiao_geografica`),
  UNIQUE KEY `codigo_ibge` (`codigo_ibge`),
  KEY `fk_regiao_tipo_jurisdicao` (`id_tipo_jurisdicao`),
  CONSTRAINT `fk_regiao_tipo_jurisdicao` FOREIGN KEY (`id_tipo_jurisdicao`) REFERENCES `tipo_jurisdicao` (`id_tipo_jurisdicao`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.empresas definition

CREATE TABLE `empresas` (
  `id_empresa` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_empresa` char(36) NOT NULL,
  `nome_fantasia` varchar(255) NOT NULL,
  `numero` varchar(50) DEFAULT NULL,
  `bairro` varchar(100) DEFAULT NULL,
  `complemento` varchar(150) DEFAULT NULL,
  `cep` varchar(20) DEFAULT NULL,
  `id_regiao_geografica` bigint(20) DEFAULT NULL,
  `razao_social` varchar(255) DEFAULT NULL,
  `status_plano` varchar(50) DEFAULT NULL,
  `plano` varchar(100) DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_empresa`),
  UNIQUE KEY `uuid_empresa` (`uuid_empresa`),
  KEY `id_regiao_geografica` (`id_regiao_geografica`),
  CONSTRAINT `empresas_ibfk_1` FOREIGN KEY (`id_regiao_geografica`) REFERENCES `regiao_geografica` (`id_regiao_geografica`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.usuarios definition

CREATE TABLE `usuarios` (
  `id_usuario` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_usuario` char(36) NOT NULL,
  `id_empresa` bigint(20) NOT NULL,
  `nome_completo` varchar(255) NOT NULL,
  `cpf` varchar(64) NOT NULL,
  `email` varchar(255) NOT NULL,
  `telefone` varchar(50) DEFAULT NULL,
  `user_login` varchar(100) DEFAULT NULL,
  `status` enum('ativo','inativo','pendente') NOT NULL,
  `hash_senha` varchar(255) DEFAULT NULL,
  `ultimo_acesso` timestamp NULL DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `google_sub` varchar(255) DEFAULT NULL,
  `onboarding_pendente` tinyint(1) DEFAULT 1,
  `cpf_hash` varchar(255) NOT NULL,
  `is_admin` tinyint(1) NOT NULL DEFAULT 0,
  `is_super_admin` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id_usuario`),
  UNIQUE KEY `uuid_usuario` (`uuid_usuario`),
  UNIQUE KEY `cpf` (`cpf`),
  UNIQUE KEY `email` (`email`),
  KEY `id_empresa` (`id_empresa`),
  CONSTRAINT `usuarios_ibfk_1` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.configuracao definition

CREATE TABLE `configuracao` (
  `id_configuracao` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_configuracao` char(36) NOT NULL,
  `id_usuario` bigint(20) DEFAULT NULL,
  `configuracoes_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`configuracoes_json`)),
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_configuracao`),
  UNIQUE KEY `uuid_configuracao` (`uuid_configuracao`),
  UNIQUE KEY `id_usuario` (`id_usuario`),
  CONSTRAINT `configuracao_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.credencial_webauthn definition

CREATE TABLE `credencial_webauthn` (
  `id_credencial` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_usuario` bigint(20) NOT NULL,
  `credential_id` varchar(255) NOT NULL,
  `public_key` longblob NOT NULL,
  `sign_count` bigint(20) NOT NULL DEFAULT 0,
  `apelido_dispositivo` varchar(120) DEFAULT NULL,
  `criado_em` datetime DEFAULT current_timestamp(),
  `tipo_dispositivo` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id_credencial`),
  UNIQUE KEY `uq_credential_id` (`credential_id`),
  KEY `idx_credencial_webauthn_id_usuario` (`id_usuario`),
  CONSTRAINT `fk_credencial_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.empresa_identificador definition

CREATE TABLE `empresa_identificador` (
  `id_empresa_identificador` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_empresa` bigint(20) NOT NULL,
  `tipo_identificador` enum('cnpj','cnes') NOT NULL,
  `valor` varchar(50) NOT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_empresa_identificador`),
  UNIQUE KEY `uq_empresa_tipo` (`id_empresa`,`tipo_identificador`),
  KEY `idx_id_empresa` (`id_empresa`),
  KEY `idx_valor` (`valor`),
  CONSTRAINT `fk_empresa_identificador` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.log_acesso definition

CREATE TABLE `log_acesso` (
  `id_log` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_empresa` bigint(20) NOT NULL,
  `uuid_log` char(36) NOT NULL,
  `id_usuario` bigint(20) NOT NULL,
  `uuid_paciente` char(36) DEFAULT NULL,
  `recurso_acessado` varchar(255) NOT NULL,
  `operacao` enum('leitura','escrita','exclusao-logica','exportacao') NOT NULL,
  `data_hora` timestamp NOT NULL,
  `ip_origem` varchar(255) NOT NULL,
  `resultado` enum('sucesso','falha-autenticacao','acesso-negado','timeout') NOT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_log`),
  UNIQUE KEY `uuid_log` (`uuid_log`),
  KEY `id_usuario` (`id_usuario`),
  KEY `fk_log_acesso_empresa` (`id_empresa`),
  CONSTRAINT `fk_log_acesso_empresa` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`),
  CONSTRAINT `log_acesso_ibfk_1` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.log_alteracao definition

CREATE TABLE `log_alteracao` (
  `id_alteracao` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_empresa` bigint(20) DEFAULT NULL,
  `uuid_alteracao` char(36) NOT NULL,
  `tabela_origem` varchar(100) NOT NULL,
  `id_registro` bigint(20) NOT NULL,
  `uuid_registro` char(36) NOT NULL,
  `operacao` enum('INSERT','UPDATE','DELETE') NOT NULL,
  `campo_alterado` varchar(100) DEFAULT NULL,
  `valor_anterior` text DEFAULT NULL,
  `valor_novo` text DEFAULT NULL,
  `alterado_por` bigint(20) DEFAULT NULL,
  `alterado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `ip_origem` varchar(45) DEFAULT NULL,
  `justificativa` text DEFAULT NULL,
  `acao` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id_alteracao`),
  UNIQUE KEY `uuid_alteracao` (`uuid_alteracao`),
  KEY `alterado_por` (`alterado_por`),
  KEY `ix_log_alteracao_empresa_data` (`id_empresa`,`alterado_em`),
  KEY `ix_log_alteracao_usuario_data` (`alterado_por`,`alterado_em`),
  KEY `ix_log_alteracao_registro_data` (`uuid_registro`,`alterado_em`),
  KEY `ix_log_alteracao_empresa_acao` (`id_empresa`,`acao`),
  CONSTRAINT `fk_log_alteracao_empresa` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`),
  CONSTRAINT `log_alteracao_ibfk_1` FOREIGN KEY (`alterado_por`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.paciente definition

CREATE TABLE `paciente` (
  `id_paciente` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_paciente` char(36) NOT NULL,
  `identificacao_anonima` varchar(255) DEFAULT NULL,
  `sexo_biologico` enum('M','F','I') NOT NULL,
  `data_nascimento` date DEFAULT NULL,
  `id_regiao_geografica` bigint(20) DEFAULT NULL,
  `data_primeiro_atendimento` date NOT NULL,
  `status` enum('ativo','inativo','obito') NOT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `cadastrado_por` bigint(20) DEFAULT NULL,
  `falecido` tinyint(1) NOT NULL DEFAULT 0,
  `data_obito` date DEFAULT NULL,
  `bairro` varchar(100) DEFAULT NULL,
  `id_empresa` bigint(20) NOT NULL,
  PRIMARY KEY (`id_paciente`),
  UNIQUE KEY `uuid_paciente` (`uuid_paciente`),
  KEY `id_regiao_geografica` (`id_regiao_geografica`),
  KEY `cadastrado_por` (`cadastrado_por`),
  KEY `ix_paciente_id_empresa` (`id_empresa`),
  CONSTRAINT `fk_paciente_empresa` FOREIGN KEY (`id_empresa`) REFERENCES `empresas` (`id_empresa`),
  CONSTRAINT `paciente_ibfk_1` FOREIGN KEY (`id_regiao_geografica`) REFERENCES `regiao_geografica` (`id_regiao_geografica`),
  CONSTRAINT `paciente_ibfk_2` FOREIGN KEY (`cadastrado_por`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.paciente_dados_pessoais definition

CREATE TABLE `paciente_dados_pessoais` (
  `id_paciente_p` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_paciente_p` char(36) NOT NULL,
  `id_paciente` bigint(20) NOT NULL,
  `nome_completo` varchar(255) NOT NULL,
  `cpf` varchar(255) DEFAULT NULL,
  `cpf_hash` varchar(255) NOT NULL,
  `rg` varchar(100) DEFAULT NULL,
  `telefone` varchar(150) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `logradouro` varchar(255) DEFAULT NULL,
  `numero_residencia` varchar(50) DEFAULT NULL,
  `cep` varchar(50) DEFAULT NULL,
  `contato_emergencia_nome` varchar(255) DEFAULT NULL,
  `contato_emergencia_telefone` varchar(150) DEFAULT NULL,
  PRIMARY KEY (`id_paciente_p`),
  UNIQUE KEY `uuid_paciente_p` (`uuid_paciente_p`),
  UNIQUE KEY `id_paciente` (`id_paciente`),
  UNIQUE KEY `uq_paciente_dados_pessoais_cpf_hash` (`cpf_hash`),
  UNIQUE KEY `cpf` (`cpf`),
  CONSTRAINT `paciente_dados_pessoais_ibfk_1` FOREIGN KEY (`id_paciente`) REFERENCES `paciente` (`id_paciente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.papel_profissional definition

CREATE TABLE `papel_profissional` (
  `id_papel_profissional` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_papel_profissional` char(36) NOT NULL,
  `id_usuario` bigint(20) NOT NULL,
  `tipo_papel` enum('medico','enfermeiro') NOT NULL,
  `numero_conselho` varchar(20) NOT NULL,
  `uf_conselho` char(2) NOT NULL,
  `especialidade` varchar(100) DEFAULT NULL,
  `ativo` tinyint(1) NOT NULL DEFAULT 1,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `rqe` varchar(20) DEFAULT NULL,
  PRIMARY KEY (`id_papel_profissional`),
  UNIQUE KEY `uuid_papel_profissional` (`uuid_papel_profissional`),
  UNIQUE KEY `uq_usuario_tipo` (`id_usuario`,`tipo_papel`),
  KEY `idx_id_usuario` (`id_usuario`),
  KEY `idx_numero_conselho` (`numero_conselho`),
  KEY `ix_papel_usuario_tipo_ativo` (`id_usuario`,`tipo_papel`,`ativo`),
  CONSTRAINT `fk_papel_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.stepup_reautenticacao definition

CREATE TABLE `stepup_reautenticacao` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_usuario` bigint(20) NOT NULL,
  `acao` varchar(100) NOT NULL,
  `senha_confirmada` tinyint(1) NOT NULL DEFAULT 0,
  `state` varchar(64) NOT NULL,
  `expira_em` datetime NOT NULL,
  `criado_em` datetime NOT NULL DEFAULT current_timestamp(),
  `nonce` varchar(64) NOT NULL,
  `is_super_admin` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `state` (`state`),
  KEY `ix_stepup_reautenticacao_id_usuario` (`id_usuario`),
  CONSTRAINT `fk_stepup_reautenticacao_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.stepup_token definition

CREATE TABLE `stepup_token` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_usuario` bigint(20) NOT NULL,
  `acao` varchar(100) NOT NULL,
  `token` varchar(64) NOT NULL,
  `expira_em` datetime(6) NOT NULL,
  `criado_em` datetime(6) NOT NULL DEFAULT current_timestamp(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_stepup_token_token` (`token`),
  KEY `idx_stepup_token_usuario_acao` (`id_usuario`,`acao`),
  KEY `idx_stepup_token_expira_em` (`expira_em`),
  CONSTRAINT `fk_stepup_token_usuario` FOREIGN KEY (`id_usuario`) REFERENCES `usuarios` (`id_usuario`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.alergia definition

CREATE TABLE `alergia` (
  `id_alergia` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_alergia` char(36) NOT NULL,
  `id_paciente` bigint(20) NOT NULL,
  `substancia` varchar(255) NOT NULL,
  `codigo_substancia` varchar(100) DEFAULT NULL,
  `flag_confirmado` tinyint(1) NOT NULL DEFAULT 0,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `sistema_codigo_substancia` varchar(50) DEFAULT 'http://snomed.info/sct',
  `deletado` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete -- FALSE = visível/ativo, TRUE = removido. Independente de flag_confirmado.',
  `deletado_em` datetime DEFAULT NULL COMMENT 'Quando o soft delete ocorreu. NULL enquanto deletado = FALSE.',
  `motivo_delete` enum('erro-digitacao','registro-duplicado','diagnostico-incorreto','solicitacao-paciente','outro') DEFAULT NULL COMMENT 'Motivo estruturado do soft delete. NULL enquanto deletado = FALSE.',
  `observacoes_delete` text DEFAULT NULL COMMENT 'Detalhe em texto livre do delete -- obrigatório na aplicação quando motivo_delete = outro.',
  PRIMARY KEY (`id_alergia`),
  UNIQUE KEY `uuid_alergia` (`uuid_alergia`),
  KEY `id_paciente` (`id_paciente`),
  KEY `idx_alergia_deletado` (`deletado`),
  KEY `idx_alergia_paciente_deletado` (`id_paciente`,`deletado`),
  CONSTRAINT `alergia_ibfk_1` FOREIGN KEY (`id_paciente`) REFERENCES `paciente` (`id_paciente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.consentimento_lgpd definition

CREATE TABLE `consentimento_lgpd` (
  `id_consentimento` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_consentimento` char(36) NOT NULL,
  `id_paciente` bigint(20) NOT NULL,
  `versao_termo` varchar(50) NOT NULL,
  `data_consentimento` timestamp NOT NULL,
  `canal_coleta` enum('presencial-papel','presencial-digital','portal-online','totem','dispensa-emergencia') NOT NULL,
  `coletado_por` bigint(20) DEFAULT NULL,
  `escopo_consentimento_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`escopo_consentimento_json`)),
  `status` enum('ativo','revogado','expirado','dispensado_emergencia') NOT NULL DEFAULT 'ativo',
  `data_revogacao` timestamp NULL DEFAULT NULL,
  `observacao` text DEFAULT NULL,
  `hash_documento` char(64) DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_consentimento`),
  UNIQUE KEY `uuid_consentimento` (`uuid_consentimento`),
  KEY `id_paciente` (`id_paciente`),
  KEY `coletado_por` (`coletado_por`),
  CONSTRAINT `consentimento_lgpd_ibfk_1` FOREIGN KEY (`id_paciente`) REFERENCES `paciente` (`id_paciente`),
  CONSTRAINT `consentimento_lgpd_ibfk_2` FOREIGN KEY (`coletado_por`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.consulta definition

CREATE TABLE `consulta` (
  `id_consulta` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_consulta` char(36) NOT NULL,
  `iniciada_por` bigint(20) DEFAULT NULL,
  `id_paciente` bigint(20) NOT NULL,
  `tipo_consulta` enum('triagem','consulta-medica') NOT NULL,
  `data_hora_inicio` timestamp NOT NULL,
  `data_hora_fim` timestamp NULL DEFAULT NULL,
  `origem_encaminhamento` enum('espontanea','SAMU','transferencia','regulacao') NOT NULL,
  `status_consulta` enum('aguardando-triagem','em-triagem','aguardando-medico','em-atendimento','em-observacao','encerrada') NOT NULL,
  `desfecho_final` enum('alta','internacao','transferencia','obito','evasao') DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `finalizada_por` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_consulta`),
  UNIQUE KEY `uuid_consulta` (`uuid_consulta`),
  KEY `iniciada_por` (`iniciada_por`),
  KEY `id_paciente` (`id_paciente`),
  KEY `finalizada_por` (`finalizada_por`),
  CONSTRAINT `consulta_ibfk_1` FOREIGN KEY (`iniciada_por`) REFERENCES `usuarios` (`id_usuario`),
  CONSTRAINT `consulta_ibfk_2` FOREIGN KEY (`id_paciente`) REFERENCES `paciente` (`id_paciente`),
  CONSTRAINT `consulta_ibfk_3` FOREIGN KEY (`finalizada_por`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.doenca_cronica definition

CREATE TABLE `doenca_cronica` (
  `id_doenca_cronica` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_doenca_cronica` char(36) NOT NULL,
  `id_paciente` bigint(20) NOT NULL,
  `codigo_cid10` varchar(10) NOT NULL,
  `descricao_cid10` varchar(255) NOT NULL,
  `desde` date NOT NULL,
  `status` enum('ativa','em-remissao') NOT NULL,
  `observacoes` text DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `deletado` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete -- FALSE = visível/ativo, TRUE = removido. Independente de status clínico.',
  `deletado_em` datetime DEFAULT NULL COMMENT 'Quando o soft delete ocorreu. NULL enquanto deletado = FALSE.',
  `motivo_delete` enum('erro-digitacao','registro-duplicado','diagnostico-incorreto','solicitacao-paciente','outro') DEFAULT NULL COMMENT 'Motivo estruturado do soft delete. NULL enquanto deletado = FALSE.',
  `observacoes_delete` text DEFAULT NULL COMMENT 'Detalhe em texto livre do delete -- obrigatório na aplicação quando motivo_delete = outro.',
  PRIMARY KEY (`id_doenca_cronica`),
  UNIQUE KEY `uuid_doenca_cronica` (`uuid_doenca_cronica`),
  KEY `id_paciente` (`id_paciente`),
  KEY `idx_doenca_cronica_deletado` (`deletado`),
  KEY `idx_doenca_cronica_paciente_deletado` (`id_paciente`,`deletado`),
  CONSTRAINT `doenca_cronica_ibfk_1` FOREIGN KEY (`id_paciente`) REFERENCES `paciente` (`id_paciente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.medicamentos_em_uso definition

CREATE TABLE `medicamentos_em_uso` (
  `id_medicamentos_uso` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_medicamentos_uso` char(36) NOT NULL,
  `id_catalogo` bigint(20) DEFAULT NULL,
  `id_paciente` bigint(20) DEFAULT NULL,
  `desde` date DEFAULT NULL,
  `descricao` text DEFAULT NULL,
  `frequencia` varchar(100) DEFAULT NULL,
  `dose` varchar(100) DEFAULT NULL,
  `flag_em_uso` tinyint(1) DEFAULT 1,
  `status_uso` enum('ativo','interrompido','concluido') DEFAULT NULL,
  `deletado` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'Soft delete -- FALSE = visível/ativo, TRUE = removido. Independente de status_uso/flag_em_uso.',
  `deletado_em` datetime DEFAULT NULL COMMENT 'Quando o soft delete ocorreu. NULL enquanto deletado = FALSE.',
  `motivo_delete` enum('erro-digitacao','registro-duplicado','diagnostico-incorreto','solicitacao-paciente','outro') DEFAULT NULL COMMENT 'Motivo estruturado do soft delete. NULL enquanto deletado = FALSE.',
  `observacoes_delete` text DEFAULT NULL COMMENT 'Detalhe em texto livre do delete -- obrigatório na aplicação quando motivo_delete = outro.',
  PRIMARY KEY (`id_medicamentos_uso`),
  UNIQUE KEY `uuid_medicamentos_uso` (`uuid_medicamentos_uso`),
  KEY `id_catalogo` (`id_catalogo`),
  KEY `id_paciente` (`id_paciente`),
  KEY `idx_medicamento_em_uso_deletado` (`deletado`),
  KEY `idx_medicamento_em_uso_paciente_deletado` (`id_paciente`,`deletado`),
  CONSTRAINT `medicamentos_em_uso_ibfk_1` FOREIGN KEY (`id_catalogo`) REFERENCES `catalogo_medicamentos` (`id_catalogo_medicamentos`),
  CONSTRAINT `medicamentos_em_uso_ibfk_2` FOREIGN KEY (`id_paciente`) REFERENCES `paciente` (`id_paciente`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.observacao_tipo_sanguineo definition

CREATE TABLE `observacao_tipo_sanguineo` (
  `id_observacao` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_observacao` char(36) NOT NULL,
  `id_paciente` bigint(20) NOT NULL,
  `tipo_sanguineo` enum('A+','A-','B+','B-','AB+','AB-','O+','O-','desconhecido') NOT NULL,
  `registrado_por` bigint(20) DEFAULT NULL,
  `data_registro` timestamp NOT NULL DEFAULT current_timestamp(),
  `codigo_loinc` varchar(20) DEFAULT '882-1',
  PRIMARY KEY (`id_observacao`),
  UNIQUE KEY `uuid_observacao` (`uuid_observacao`),
  KEY `idx_id_paciente` (`id_paciente`),
  KEY `fk_obs_sanguineo_usuario` (`registrado_por`),
  CONSTRAINT `fk_obs_sanguineo_paciente` FOREIGN KEY (`id_paciente`) REFERENCES `paciente` (`id_paciente`),
  CONSTRAINT `fk_obs_sanguineo_usuario` FOREIGN KEY (`registrado_por`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.reacao_alergia definition

CREATE TABLE `reacao_alergia` (
  `id_reacao` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_reacao` char(36) NOT NULL,
  `id_alergia` bigint(20) NOT NULL,
  `manifestacao` enum('cutanea','respiratoria','anafilaxia','gastrointestinal','cardiovascular','sistemica') NOT NULL,
  `gravidade` enum('leve','moderada','grave') NOT NULL,
  `descricao` text DEFAULT NULL,
  `data_ocorrencia` date DEFAULT NULL,
  PRIMARY KEY (`id_reacao`),
  UNIQUE KEY `uuid_reacao` (`uuid_reacao`),
  KEY `idx_id_alergia` (`id_alergia`),
  CONSTRAINT `fk_reacao_alergia` FOREIGN KEY (`id_alergia`) REFERENCES `alergia` (`id_alergia`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.atendimento definition

CREATE TABLE `atendimento` (
  `id_atendimento` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_atendimento` char(36) NOT NULL,
  `id_consulta` bigint(20) NOT NULL,
  `tipo_atendimento` enum('triagem','avaliacao-medica','reavaliacao','alta','procedimento') NOT NULL,
  `realizado_por` bigint(20) NOT NULL,
  `data_hora_inicio` timestamp NOT NULL,
  `data_hora_fim` timestamp NULL DEFAULT NULL,
  `status` enum('em-andamento','finalizado','cancelado') NOT NULL,
  `habitos_atendimento_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`habitos_atendimento_json`)),
  `observacoes_profissional` text DEFAULT NULL,
  PRIMARY KEY (`id_atendimento`),
  UNIQUE KEY `uuid_atendimento` (`uuid_atendimento`),
  KEY `id_consulta` (`id_consulta`),
  KEY `realizado_por` (`realizado_por`),
  KEY `ix_atendimento_realizado_por_status_data` (`realizado_por`,`status`,`data_hora_inicio`),
  CONSTRAINT `atendimento_ibfk_1` FOREIGN KEY (`id_consulta`) REFERENCES `consulta` (`id_consulta`),
  CONSTRAINT `atendimento_ibfk_2` FOREIGN KEY (`realizado_por`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.coleta_clinica definition

CREATE TABLE `coleta_clinica` (
  `id_coleta` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_coleta` char(36) NOT NULL,
  `id_atendimento` bigint(20) NOT NULL,
  `desde_quando_sintomas` smallint(6) DEFAULT NULL,
  PRIMARY KEY (`id_coleta`),
  UNIQUE KEY `uuid_coleta` (`uuid_coleta`),
  KEY `id_atendimento` (`id_atendimento`),
  CONSTRAINT `coleta_clinica_ibfk_1` FOREIGN KEY (`id_atendimento`) REFERENCES `atendimento` (`id_atendimento`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.sinal_vital definition

CREATE TABLE `sinal_vital` (
  `id_sinal_vital` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_sinal_vital` char(36) NOT NULL,
  `id_atendimento` bigint(20) NOT NULL,
  `tipo_parametro` varchar(40) NOT NULL,
  `valor_numerico` decimal(10,2) NOT NULL,
  `unidade` enum('irpm','%','mmHg','bpm','°C','mg-dL') NOT NULL,
  `sitio_medicao` enum('axilar','oral','retal','timpanico','oximetria-digital','manguito-braco-direito','manguito-braco-esquerdo') DEFAULT NULL,
  `data_hora_medicao` timestamp NOT NULL,
  `coletado_por` bigint(20) NOT NULL,
  `flag_validacao_faixa` enum('dentro-do-limite','fora-limite-alertado','fora-limite-rejeitado') NOT NULL,
  `flag_escala_dpoc` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id_sinal_vital`),
  UNIQUE KEY `uuid_sinal_vital` (`uuid_sinal_vital`),
  KEY `id_atendimento` (`id_atendimento`),
  KEY `coletado_por` (`coletado_por`),
  KEY `fk_sinal_vital_loinc` (`tipo_parametro`),
  CONSTRAINT `fk_sinal_vital_loinc` FOREIGN KEY (`tipo_parametro`) REFERENCES `loinc_sinal_vital` (`tipo_parametro`),
  CONSTRAINT `sinal_vital_ibfk_1` FOREIGN KEY (`id_atendimento`) REFERENCES `atendimento` (`id_atendimento`),
  CONSTRAINT `sinal_vital_ibfk_2` FOREIGN KEY (`coletado_por`) REFERENCES `usuarios` (`id_usuario`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.configuracao_protocolo definition

CREATE TABLE `configuracao_protocolo` (
  `id_configuracao_protocolo` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_configuracao` bigint(20) DEFAULT NULL,
  `id_protocolo` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_configuracao_protocolo`),
  KEY `id_configuracao` (`id_configuracao`),
  KEY `fk_configuracao_protocolo_protocolo` (`id_protocolo`),
  CONSTRAINT `configuracao_protocolo_ibfk_1` FOREIGN KEY (`id_configuracao`) REFERENCES `configuracao` (`id_configuracao`),
  CONSTRAINT `fk_configuracao_protocolo_protocolo` FOREIGN KEY (`id_protocolo`) REFERENCES `protocolo_catalogo` (`id_protocolo_catalogo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.input_protocolo definition

CREATE TABLE `input_protocolo` (
  `id_input` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_input` char(36) NOT NULL,
  `id_coleta_clinica` bigint(20) DEFAULT NULL,
  `input_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`input_json`)),
  `queixa_principal` text DEFAULT NULL,
  `valor_avpu` varchar(20) DEFAULT NULL,
  `dados_criticos_ausentes_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`dados_criticos_ausentes_json`)),
  `tipo_input` enum('triagem','consulta') DEFAULT NULL,
  `id_protocolo_execucao` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_input`),
  UNIQUE KEY `uuid_input` (`uuid_input`),
  KEY `id_coleta_clinica` (`id_coleta_clinica`),
  KEY `fk_input_protocolo_execucao` (`id_protocolo_execucao`),
  CONSTRAINT `fk_input_protocolo_execucao` FOREIGN KEY (`id_protocolo_execucao`) REFERENCES `input_protocolo_execucao` (`id_input_execucao`),
  CONSTRAINT `input_protocolo_ibfk_1` FOREIGN KEY (`id_coleta_clinica`) REFERENCES `coleta_clinica` (`id_coleta`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.input_protocolo_execucao definition

CREATE TABLE `input_protocolo_execucao` (
  `id_input_execucao` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_input` bigint(20) DEFAULT NULL,
  `id_protocolo_catalogo` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_input_execucao`),
  UNIQUE KEY `uq_input_protocolo` (`id_input`,`id_protocolo_catalogo`),
  KEY `id_protocolo_catalogo` (`id_protocolo_catalogo`),
  CONSTRAINT `input_protocolo_execucao_ibfk_1` FOREIGN KEY (`id_protocolo_catalogo`) REFERENCES `protocolo_catalogo` (`id_protocolo_catalogo`),
  CONSTRAINT `input_protocolo_execucao_ibfk_2` FOREIGN KEY (`id_input`) REFERENCES `input_protocolo` (`id_input`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.output_bion definition

CREATE TABLE `output_bion` (
  `id_output` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_output` char(36) NOT NULL,
  `output_ia_json` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`output_ia_json`)),
  `versao_modelo_ia` varchar(50) DEFAULT NULL,
  `id_input` bigint(20) DEFAULT NULL,
  `indice_completude` decimal(5,2) DEFAULT NULL,
  `indice_confianca` decimal(5,2) DEFAULT NULL,
  `criado_em` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_output`),
  UNIQUE KEY `uuid_output` (`uuid_output`),
  KEY `fk_output_input` (`id_input`),
  KEY `ix_output_bion_criado_input` (`criado_em`,`id_input`),
  CONSTRAINT `fk_output_input` FOREIGN KEY (`id_input`) REFERENCES `input_protocolo` (`id_input`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.prescricao definition

CREATE TABLE `prescricao` (
  `id_prescricao` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_resultado_prescricao` bigint(20) DEFAULT NULL,
  `id_catalogo` bigint(20) DEFAULT NULL,
  `dose` varchar(100) DEFAULT NULL,
  `frequencia` varchar(100) DEFAULT NULL,
  `duracao` varchar(100) DEFAULT NULL,
  `orientacoes` text DEFAULT NULL,
  `id_resultado` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_prescricao`),
  KEY `id_resultado_prescricao` (`id_resultado_prescricao`),
  KEY `id_catalogo` (`id_catalogo`),
  KEY `fk_prescricao_resultado` (`id_resultado`),
  KEY `idx_prescricao_catalogo` (`id_catalogo`),
  KEY `idx_prescricao_resultado` (`id_resultado_prescricao`),
  CONSTRAINT `fk_prescricao_resultado` FOREIGN KEY (`id_resultado`) REFERENCES `resultado_prescricao` (`id_resultado`),
  CONSTRAINT `prescricao_ibfk_1` FOREIGN KEY (`id_resultado_prescricao`) REFERENCES `resultado_prescricao` (`id_resultado`),
  CONSTRAINT `prescricao_ibfk_2` FOREIGN KEY (`id_catalogo`) REFERENCES `catalogo_medicamentos` (`id_catalogo_medicamentos`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.prescricao_exame definition

CREATE TABLE `prescricao_exame` (
  `id_prescricao_exame` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_prescricao_exame` char(36) NOT NULL,
  `id_resultado` bigint(20) DEFAULT NULL,
  `id_exame` bigint(20) DEFAULT NULL,
  `urgencia` enum('rotina','urgente','emergencia') DEFAULT NULL,
  `justificativa` text DEFAULT NULL,
  `origem_sugestao` enum('medico','bion_ia','protocolo') DEFAULT NULL,
  `id_output_origem` bigint(20) DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id_prescricao_exame`),
  UNIQUE KEY `uuid_prescricao_exame` (`uuid_prescricao_exame`),
  KEY `id_resultado` (`id_resultado`),
  KEY `id_exame` (`id_exame`),
  KEY `id_output_origem` (`id_output_origem`),
  CONSTRAINT `prescricao_exame_ibfk_1` FOREIGN KEY (`id_resultado`) REFERENCES `resultado_prescricao` (`id_resultado`),
  CONSTRAINT `prescricao_exame_ibfk_2` FOREIGN KEY (`id_exame`) REFERENCES `catalogo_exames` (`id_catalogo_exame`),
  CONSTRAINT `prescricao_exame_ibfk_3` FOREIGN KEY (`id_output_origem`) REFERENCES `output_bion` (`id_output`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.protocolo_catalogo definition

CREATE TABLE `protocolo_catalogo` (
  `id_protocolo_catalogo` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_protocolo_catalogo` char(36) NOT NULL,
  `nome_protocolo` varchar(255) NOT NULL,
  `sigla` varchar(50) NOT NULL,
  `tipo_resultado` enum('score-numerico','categoria-cor','nivel-risco','binario') NOT NULL,
  `escopo_populacao` enum('adulto','pediatrico','obstetrico','neonatal','universal') NOT NULL,
  `versao_vigente` varchar(50) NOT NULL,
  `data_vigencia` date NOT NULL,
  `data_vigencia_fim` date DEFAULT NULL,
  `referencia_bibliografica` text DEFAULT NULL,
  `orgao_emissor` varchar(255) DEFAULT NULL,
  `status` enum('ativo','descontinuado','em-revisao') NOT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `flag_personalizado` tinyint(1) DEFAULT NULL,
  `tipo_protocolo` varchar(100) DEFAULT NULL,
  `escopoUso` enum('triagem','consulta','ambos') DEFAULT NULL,
  `id_protocolo_execucao` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_protocolo_catalogo`),
  UNIQUE KEY `uuid_protocolo_catalogo` (`uuid_protocolo_catalogo`),
  UNIQUE KEY `sigla` (`sigla`),
  KEY `fk_protocolo_catalogo_execucao` (`id_protocolo_execucao`),
  CONSTRAINT `fk_protocolo_catalogo_execucao` FOREIGN KEY (`id_protocolo_execucao`) REFERENCES `input_protocolo_execucao` (`id_input_execucao`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.protocolo_mts definition

CREATE TABLE `protocolo_mts` (
  `id_protocolo_mts` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_fluxo_mts` bigint(20) DEFAULT NULL,
  `id_protocolo_catalogo` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_protocolo_mts`),
  KEY `id_fluxo_mts` (`id_fluxo_mts`),
  KEY `id_protocolo_catalogo` (`id_protocolo_catalogo`),
  CONSTRAINT `protocolo_mts_ibfk_1` FOREIGN KEY (`id_fluxo_mts`) REFERENCES `catalogo_fluxogramas_mts` (`id_fluxo_mts`),
  CONSTRAINT `protocolo_mts_ibfk_2` FOREIGN KEY (`id_protocolo_catalogo`) REFERENCES `protocolo_catalogo` (`id_protocolo_catalogo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.protocolo_personalizado definition

CREATE TABLE `protocolo_personalizado` (
  `id_protocolo_personalizado` bigint(20) NOT NULL AUTO_INCREMENT,
  `id_modulo` bigint(20) DEFAULT NULL,
  `id_protocolo_catalogo` bigint(20) DEFAULT NULL,
  `codigo_protocolo` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id_protocolo_personalizado`),
  KEY `id_modulo` (`id_modulo`),
  KEY `id_protocolo_catalogo` (`id_protocolo_catalogo`),
  CONSTRAINT `protocolo_personalizado_ibfk_1` FOREIGN KEY (`id_modulo`) REFERENCES `catalogo_modulos` (`id_modulo`),
  CONSTRAINT `protocolo_personalizado_ibfk_2` FOREIGN KEY (`id_protocolo_catalogo`) REFERENCES `protocolo_catalogo` (`id_protocolo_catalogo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- bion_testes.resultado_prescricao definition

CREATE TABLE `resultado_prescricao` (
  `id_resultado` bigint(20) NOT NULL AUTO_INCREMENT,
  `uuid_resultado` char(36) NOT NULL,
  `id_atendimento` bigint(20) NOT NULL,
  `codigo_cid10_principal` varchar(10) NOT NULL,
  `descricao_cid10_principal` varchar(255) NOT NULL,
  `certeza_diagnostica` enum('suspeito','provavel','confirmado','descartado') NOT NULL,
  `formulado_por` bigint(20) NOT NULL,
  `data_hora_formulacao` timestamp NOT NULL,
  `tipo_prescricao` enum('farmacologica','nao-farmacologica','encaminhamento','internacao','alta') DEFAULT NULL,
  `consistente_com_classificacao` tinyint(1) DEFAULT NULL,
  `criado_em` timestamp NOT NULL DEFAULT current_timestamp(),
  `id_output` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id_resultado`),
  UNIQUE KEY `uuid_resultado` (`uuid_resultado`),
  KEY `id_atendimento` (`id_atendimento`),
  KEY `formulado_por` (`formulado_por`),
  KEY `id_output` (`id_output`),
  CONSTRAINT `resultado_prescricao_ibfk_1` FOREIGN KEY (`id_atendimento`) REFERENCES `atendimento` (`id_atendimento`),
  CONSTRAINT `resultado_prescricao_ibfk_2` FOREIGN KEY (`formulado_por`) REFERENCES `usuarios` (`id_usuario`),
  CONSTRAINT `resultado_prescricao_ibfk_3` FOREIGN KEY (`id_output`) REFERENCES `output_bion` (`id_output`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;




SET FOREIGN_KEY_CHECKS = 1;