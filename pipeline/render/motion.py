from __future__ import annotations


def image_motion_filter(motion: str, width: int, height: int, fps: int, duration: float) -> str:
    """Return a deterministic FFmpeg filter chain for a still image.

    zoompan needs a larger working canvas to allow movement without exposing empty borders.
    """
    frames = max(1, int(round(duration * fps)))
    base = f"scale={int(width * 1.12)}:{int(height * 1.12)}:force_original_aspect_ratio=increase,crop={int(width * 1.12)}:{int(height * 1.12)}"
    effects = {
        "slow_push_in": f"zoompan=z='min(zoom+0.0009,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}",
        "slow_pull_out": f"zoompan=z='if(eq(on,0),1.10,max(1.0,zoom-0.0009))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}",
        "subtle_zoom": f"zoompan=z='1.0+0.025*sin(on/{max(1,frames)}*PI)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}",
        "pan_left": f"zoompan=z='1.08':x='(iw-iw/zoom)*(1-on/{frames})':y='(ih-ih/zoom)/2':d={frames}:s={width}x{height}:fps={fps}",
        "pan_right": f"zoompan=z='1.08':x='(iw-iw/zoom)*(on/{frames})':y='(ih-ih/zoom)/2':d={frames}:s={width}x{height}:fps={fps}",
        "pan_up": f"zoompan=z='1.08':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*(1-on/{frames})':d={frames}:s={width}x{height}:fps={fps}",
        "pan_down": f"zoompan=z='1.08':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*(on/{frames})':d={frames}:s={width}x{height}:fps={fps}",
        "document_focus": f"zoompan=z='min(zoom+0.0012,1.12)':x='iw*0.46-(iw/zoom/2)':y='ih*0.42-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}",
        "static": f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps}",
    }
    effect = effects.get(motion, effects["static"])
    if motion == "static":
        return effect
    return f"{base},{effect},format=yuv420p"
