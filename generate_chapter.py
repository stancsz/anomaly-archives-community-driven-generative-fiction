import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

BASE_DIR = Path(__file__).parent
WRITER_DIR = BASE_DIR / ".writer"
AGENT_FILE = WRITER_DIR / "AGENT.md"
SEASON1_TEMPLATE_FILE = WRITER_DIR / "SEASON1.md"

AUTHOR = "Anomaly Archives Agent"
MODEL = "gpt-5-mini"
MAX_CHAPTERS_PER_SEASON = 30


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def find_latest_season(base: Path) -> int:
    max_n = 0
    for item in base.iterdir():
        if item.is_dir():
            match = re.fullmatch(r"season-(\d+)", item.name)
            if match:
                max_n = max(max_n, int(match.group(1)))
    return max_n


def find_latest_chapter(season_dir: Path) -> int:
    if not season_dir.exists():
        return 0
    max_n = 0
    for item in season_dir.iterdir():
        if item.is_dir():
            match = re.fullmatch(r"chapter-(\d+)", item.name)
            if match:
                max_n = max(max_n, int(match.group(1)))
    return max_n


def get_season_file(season_number: int) -> Path:
    season_dir = BASE_DIR / f"season-{season_number}"
    return season_dir / f"SEASON{season_number}.md"


def load_previous_chapter(season_number: int, chapter_number: int) -> str:
    if chapter_number <= 1:
        return ""
    prev_n = chapter_number - 1
    prev_dir = BASE_DIR / f"season-{season_number}" / f"chapter-{prev_n}"
    prev_file = prev_dir / f"CHAPTER{prev_n}.md"
    return read_text(prev_file)


def build_prompt(
    agent_md: str,
    season_template_md: str,
    season_number: int,
    chapter_number: int,
    previous_chapter_md: str,
    season_file_md: str,
) -> list:
    system_instructions = f"""
You are a Horror Narrative Specialist writing for the serialized project "Anomaly Archives".

Follow these project rules strictly:
- Use oppressive, atmospheric horror with psychological and existential dread.
- Follow the project structure and formatting rules from AGENT.md.
- This is Season {season_number}, Chapter {chapter_number}.
- Each chapter must be a self-contained, novel-like episode that advances an ongoing season narrative.
- Use Markdown, with sections: "Metadata", "Synopsis", "Structure", "Notes".
- Every CHAPTER file must start with a Metadata block listing: Season, Chapter, Title, Author, Synopsis (short).

Do NOT include explanations of your process. Output only the chapter markdown.
"""

    season_context = f"""
Existing Season File (if any):

{season_file_md}
""".strip()

    if previous_chapter_md:
        prev_chapter_context = (
            f"Previous Chapter (for continuity):\n\n{previous_chapter_md}"
        )
    else:
        prev_chapter_context = (
            "No previous chapter exists. This is the first chapter of the season."
        )

    user_request = f"""
Using the AGENT instructions and the Anomaly Archives Season 1 template, write Season {season_number}, Chapter {chapter_number}.

Requirements:
- Infer or select a strong, thematically consistent Season title if not already defined.
- Determine a compelling Chapter title that fits the ongoing Anomaly Archives tone.
- Maintain continuity with previous chapters if they exist, but keep this chapter readable on its own.
- The narrative should be structured like a fiction episode/chapter of a novel:
  - Clear opening hook.
  - Rising tension ("ratchet") with investigative beats.
  - Climax that pays off the horror mechanics.
  - Lingering, unsettling resolution.
- Keep the focus on atmospheric dread, psychological horror, and anomalous investigative structure.

Output:
- A complete Markdown chapter file following the project structure and naming conventions.
- Start with the Metadata block.
"""

    return [
        {
            "role": "system",
            "content": [
                {"type": "text", "text": system_instructions},
                {"type": "text", "text": "AGENT INSTRUCTIONS:\n\n" + agent_md},
                {
                    "type": "text",
                    "text": "SEASON 1 TEMPLATE / SERIES PREMISE:\n\n"
                    + season_template_md,
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": season_context},
                {"type": "text", "text": prev_chapter_context},
                {"type": "text", "text": user_request},
            ],
        },
    ]


def generate_chapter() -> None:
    latest_season = find_latest_season(BASE_DIR)

    if latest_season == 0:
        season_number = 1
        chapter_number = 1
    else:
        current_season_dir = BASE_DIR / f"season-{latest_season}"
        latest_chapter = find_latest_chapter(current_season_dir)

        if latest_chapter >= MAX_CHAPTERS_PER_SEASON:
            season_number = latest_season + 1
            chapter_number = 1
        else:
            season_number = latest_season
            chapter_number = latest_chapter + 1

    season_dir = BASE_DIR / f"season-{season_number}"
    season_dir.mkdir(exist_ok=True)

    chapter_dir = season_dir / f"chapter-{chapter_number}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    season_file = get_season_file(season_number)
    season_file_md = read_text(season_file)
    prev_chapter_md = load_previous_chapter(season_number, chapter_number)

    agent_md = read_text(AGENT_FILE)
    season_template_md = read_text(SEASON1_TEMPLATE_FILE)

    messages = build_prompt(
        agent_md=agent_md,
        season_template_md=season_template_md,
        season_number=season_number,
        chapter_number=chapter_number,
        previous_chapter_md=prev_chapter_md,
        season_file_md=season_file_md,
    )

    client = OpenAI()

    response = client.responses.create(
        model=MODEL,
        input=messages,
        text={"format": {"type": "text"}, "verbosity": "medium"},
        reasoning={"effort": "medium", "summary": "auto"},
        tools=[],
        store=True,
        include=["reasoning.encrypted_content", "web_search_call.action.sources"],
    )

    output_text = ""
    for item in response.output:
        if item.type == "message":
            for content in item.message.content:
                if content.type == "output_text":
                    output_text += content.output_text.text

    if not output_text.strip():
        raise RuntimeError("No chapter text returned from model.")

    if not season_file_md.strip():
        season_file.write_text(
            f"# SEASON {season_number}\n\n"
            "_(Auto-generated season file. You can edit this to refine the season overview.)_\n",
            encoding="utf-8",
        )

    chapter_file = chapter_dir / f"CHAPTER{chapter_number}.md"
    chapter_file.write_text(output_text, encoding="utf-8")

    print(f"Generated Season {season_number}, Chapter {chapter_number}: {chapter_file}")


if __name__ == "__main__":
    generate_chapter()

