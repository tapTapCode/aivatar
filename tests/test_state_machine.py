import pytest
from pipeline.core.enums import ProjectState
from pipeline.core.state_machine import can_transition, require_transition

def test_valid_transition(): assert can_transition(ProjectState.CREATED,ProjectState.SCRIPT_READY)
def test_invalid_transition():
    with pytest.raises(ValueError): require_transition(ProjectState.CREATED,ProjectState.COMPLETED)
