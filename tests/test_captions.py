from src.rendering.captions import ass_color, srt_timestamp


def test_srt_timestamp_rounding() -> None:
    assert srt_timestamp(65.4321) == "00:01:05,432"


def test_caption_color_is_converted_to_ass_order() -> None:
    assert ass_color("#123456") == "&H00563412"
