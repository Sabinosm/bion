"""
Blueprint principal do domínio FHIR — agrega as rotas de cada Resource.

Esta é a camada de INTEROPERABILIDADE EXTERNA, separada da API interna
que o front consome. Rotas aqui seguem convenção REST do FHIR
(GET /fhir/Patient/{id}, etc), não o formato de resposta enxuto que o
resto da aplicação usa.

Autenticação/autorização dessas rotas merece atenção própria (ver nota
em routes/patient_routes.py) -- por ora usa a mesma sessão da aplicação,
mas se este domínio for consumido por sistemas externos de verdade
(RNDS, outro hospital), o caminho correto é migrar para SMART on FHIR
(OAuth2 com escopos de saúde), não a sessão de cookie atual.
"""

from flask import Blueprint

from .routes.patient_routes import bp as bp_patient
from .routes.practitioner_routes import bp as bp_practitioner
from .routes.organization_routes import bp as bp_organization
from .routes.observation_routes import bp as bp_observation
from .routes.allergyintolerance_routes import bp as bp_allergy

bp_fhir = Blueprint("fhir", __name__)

bp_fhir.register_blueprint(bp_patient)
bp_fhir.register_blueprint(bp_practitioner)
bp_fhir.register_blueprint(bp_organization)
bp_fhir.register_blueprint(bp_observation)
bp_fhir.register_blueprint(bp_allergy)