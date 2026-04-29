import subprocess
import sys
from pathlib import Path


# Cada item: str (script só) ou tuple (script, [args])
SCRIPTS = [
    "01_extract_chatgpt_dataset.py",
    "02_dataset_filter.py",
    "03_detect_question_boundaries.py",
    "04_quality_scoring.py",
    # escolha um:
    ("05_tag_conversations.py", ["--no-llm"]),  # Sem LLM (tags padrão)
    # ("05_tag_conversations.py", ["--resume"]),  # Com LLM + resume (continuar de onde parou; requer API key)
    "06_format_for_training.py",
]


def run_script(script_spec):
    if isinstance(script_spec, tuple):
        script, args = script_spec[0], script_spec[1]
        cmd = [sys.executable, script] + args
        display = f"{script} {' '.join(args)}"
    else:
        script = script_spec
        cmd = [sys.executable, script]
        display = script

    print("\n==============================")
    print("Running:", display)
    print("==============================\n")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print("\nERROR running:", display)
        sys.exit(1)


def main():

    for script_spec in SCRIPTS:
        script = script_spec[0] if isinstance(script_spec, tuple) else script_spec
        path = Path(script)

        if not path.exists():
            print("Script not found:", script)
            sys.exit(1)

        run_script(script_spec)

    print("\n\nPipeline complete ✅")


if __name__ == "__main__":
    main()
