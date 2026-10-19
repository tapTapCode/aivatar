from pipeline.director.timeline import PlannedScene
from pipeline.director.visual_strategy import choose_visual_strategies, motion_score, strategy_summary


def test_motion_heavy_short_scene_gets_selective_ltx_when_budget_allows():
    scenes = [
        PlannedScene(1, 0, 6, "FULL_VISUAL", "Ocean waves crash while the camera tracks a runner through a storm", "static"),
        PlannedScene(2, 6, 16, "FULL_VISUAL", "Historical document and map with an important quote", "slow_push_in"),
    ]
    decisions = choose_visual_strategies(scenes, total_budget_usd=5.0, max_ltx_scenes=1)
    assert decisions[0].strategy == "ltx_video"
    assert decisions[1].strategy in {"motion_graphic", "flux_motion"}
    assert strategy_summary(decisions)["ltx_scenes"] == [1]


def test_budget_blocks_ltx_and_falls_back_to_flux_motion():
    scene = PlannedScene(1, 0, 8, "FULL_VISUAL", "Fast traffic moving through rain as the camera orbits the city", "pan_right")
    decision = choose_visual_strategies([scene], total_budget_usd=0.1, max_ltx_scenes=3)[0]
    assert motion_score(scene.visual_prompt, scene.duration) >= 0.64
    assert decision.strategy == "flux_motion"
    assert "budget" in decision.reason.lower()


def test_presenter_and_graphic_decisions_are_cheap():
    scenes = [
        PlannedScene(1, 0, 5, "PRESENTER", "Opening presenter", "static"),
        PlannedScene(2, 5, 10, "FULL_VISUAL", "Section title: Why this matters", "static"),
    ]
    decisions = choose_visual_strategies(scenes, total_budget_usd=5.0)
    assert decisions[0].strategy == "presenter_only"
    assert decisions[0].estimated_cost_usd == 0
    assert decisions[1].strategy == "motion_graphic"
    assert decisions[1].template == "section_header"
