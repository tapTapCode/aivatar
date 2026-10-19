from pipeline.alignment.timestamps import align_script_heuristic, caption_segments, normalize_provider_timestamps


def test_heuristic_alignment_covers_master_duration():
    words = align_script_heuristic("One short sentence. Another sentence with more words!", 12.5)
    assert words[0].start == 0.0
    assert words[-1].end == 12.5
    assert all(item.end > item.start for item in words)
    captions = caption_segments(words, max_words=4)
    assert captions[0].start == 0.0
    assert captions[-1].end == 12.5


def test_provider_millisecond_timestamps_are_normalized():
    words = normalize_provider_timestamps([
        {"word": "Hello", "start": 0, "end": 500},
        {"word": "world", "start": 500, "end": 1200},
    ], duration=1.2)
    assert words[0].end == 0.5
    assert words[-1].end == 1.2
