"""Model- and platform-independent API ontology, contract IR, rules, and projections."""

from loop_apidoc.domain.models import GroundedApiContract
from loop_apidoc.domain.rules import ApiDomainRulePack

__all__ = ["ApiDomainRulePack", "GroundedApiContract"]
