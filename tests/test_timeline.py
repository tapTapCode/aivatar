import pytest
from pipeline.director.timeline import PlannedScene, plan_timeline, presenter_percentage, validate_timeline

def test_timeline_complete_and_presenter_target():
    scenes=plan_timeline("One. Two. Three. Four. Five. Six.",60,0.30)
    validate_timeline(scenes,60)
    assert len(scenes)==6
    assert presenter_percentage(scenes)==pytest.approx(0.30,abs=0.01)

def test_gap_rejected():
    with pytest.raises(ValueError,match="gap"):
        validate_timeline([PlannedScene(1,0,5,"PRESENTER","a"),PlannedScene(2,6,10,"FULL_VISUAL","b")],10)

def test_overlap_rejected():
    with pytest.raises(ValueError,match="overlap"):
        validate_timeline([PlannedScene(1,0,6,"PRESENTER","a"),PlannedScene(2,5,10,"FULL_VISUAL","b")],10)
