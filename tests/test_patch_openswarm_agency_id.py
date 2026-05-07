from __future__ import annotations

from types import SimpleNamespace

import agency_swarm.ui.demos.agentswarm_cli as cli

from patches.patch_openswarm_model_control import apply_openswarm_model_control_patch


def test_agency_id_prefers_registered_swarm_id():
    apply_openswarm_model_control_patch()
    agency = SimpleNamespace(name="OpenSwarm", openswarm_swarm_id="open-swarm")
    assert cli._agency_id(agency) == "open-swarm"


def test_agency_id_falls_back_to_name_without_swarm_id():
    apply_openswarm_model_control_patch()
    agency = SimpleNamespace(name="Some Other Agency")
    assert cli._agency_id(agency) == "Some_Other_Agency"
