import argparse, json, sys
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.core.config import settings
from pipeline.director.timeline import plan_timeline, presenter_percentage
from pipeline.render.graph import render_mock_project

def main():
    p=argparse.ArgumentParser(); p.add_argument("--duration",type=float,default=60); p.add_argument("--project-id",default=None); args=p.parse_args()
    project_id=args.project_id or f"proof-{uuid4().hex[:8]}"
    script=("Aivatar creates a timed master narration first. The director assigns presenter scenes to the hook and key explanations. "
            "Most documentary coverage uses generated still imagery with inexpensive local motion. LTX is reserved for shots where genuine motion matters. "
            "Every scene is rendered independently so a failure can resume without rebuilding completed work. FFmpeg assembles the final timeline with one authoritative audio clock.")
    scenes=plan_timeline(script,args.duration,0.30)
    print(f"Rendering {args.duration:.0f}s mock project {project_id}; presenter visibility {presenter_percentage(scenes):.1%}")
    manifest=render_mock_project(settings.aivatar_workspace,project_id,script,scenes,args.duration)
    print(json.dumps(manifest["qc"],indent=2)); print(manifest["final"])
if __name__=="__main__": main()
