import json
import re
from pathlib import Path
from typing import Optional

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


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def find_latest_season(base: Path) -> int:
    max_n = 0
    for item in base.iterdir():
        if item.is_dir():
            match = re.fullmatch(r"season-(\d+)(?:-.+)?", item.name)
            if match:
                max_n = max(max_n, int(match.group(1)))
    return max_n


def get_season_dir(season_number: int) -> Path:
    for item in BASE_DIR.iterdir():
        if item.is_dir():
            match = re.fullmatch(rf"season-{season_number}(?:-.+)?", item.name)
            if match:
                return item
    return BASE_DIR / f"season-{season_number}"


def get_season_file(season_number: int) -> Path:
    season_dir = get_season_dir(season_number)
    return season_dir / f"SEASON{season_number}.md"


def find_latest_chapter(season_dir: Path) -> int:
    if not season_dir.exists():
        return 0
    max_n = 0
    for item in season_dir.iterdir():
        if item.is_file():
            match = re.fullmatch(r"chapter-(\d+)(?:-.+)?\.md", item.name)
            if match:
                max_n = max(max_n, int(match.group(1)))
    return max_n


def find_chapter_file(season_dir: Path, chapter_number: int) -> Optional[Path]:
    if not season_dir.exists():
        return None
    pattern = re.compile(rf"chapter-{chapter_number}(?:-.+)?\.md")
    for item in season_dir.iterdir():
        if item.is_file() and pattern.fullmatch(item.name):
            return item
    return None


def load_previous_chapter(season_number: int, chapter_number: int) -> str:
    if chapter_number <= 1:
        return ""
    season_dir = get_season_dir(season_number)
    prev_file = find_chapter_file(season_dir, chapter_number - 1)
    return read_text(prev_file) if prev_file else ""


def build_prompt(
    agent_md: str,
    season_template_md: str,
    season_number: int,
    chapter_number: int,
    previous_chapter_md: str,
    season_file_md: str,
    season_title: str,
    chapter_title: str,
) -> list:
    system_instructions = f"""
You are a Horror Narrative Specialist writing for the serialized project "Anomaly Archives".

Follow these project rules strictly:
- Use oppressive, atmospheric horror with psychological and existential dread.
- Follow the project structure and formatting rules from AGENT.md.
- This is Season {season_number}, Chapter {chapter_number}.
- Season title: "{season_title}".
- Chapter title: "{chapter_title}".
- Each chapter must be a self-contained, novel-like episode that advances an ongoing season narrative.
- The output must be reader-facing, like an EPUB chapter: a single top-level title line and continuous prose.
- Do not include explicit "Metadata", "Synopsis", "Structure", or "Notes" section headings in the chapter.
- Do not include technical commentary, prompts, or explanations—only the story text itself.

Formatting:
- Begin with a single `#` heading that contains the chapter title (optionally including the chapter number, e.g., "Chapter {chapter_number} – {chapter_title}").
- After the heading, use plain paragraphs of prose. Use minimal Markdown beyond emphasis and occasional scene breaks (`***`) when needed.

Do NOT include explanations of your process. Output only the reader-ready chapter markdown.
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

Use exactly this Season Title and Chapter Title:
- Season Title: "{season_title}"
- Chapter Title: "{chapter_title}"

Requirements:
- Maintain the given Season and Chapter titles, and ensure the chapter title appears exactly in the opening `#` heading.
- Maintain continuity with previous chapters if they exist, but keep this chapter readable on its own.
- The narrative should be structured like a fiction episode/chapter of a novel:
  - Clear opening hook.
  - Rising tension ("ratchet") with investigative beats.
  - Climax that pays off the horror mechanics.
  - Lingering, unsettling resolution.
- Keep the focus on atmospheric dread, psychological horror, and anomalous investigative structure.

Output:
- A complete Markdown chapter suitable for direct inclusion in an ebook.
- Start with a single `#` heading containing the chapter title, followed only by the story text.
"""

    return [
        {
            "role": "system",
            "content": [
                {"type": "input_text", "text": system_instructions},
                {"type": "input_text", "text": "AGENT INSTRUCTIONS:\n\n" + agent_md},
                {
                    "type": "input_text",
                    "text": "SEASON 1 TEMPLATE / SERIES PREMISE:\n\n"
                    + season_template_md,
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": season_context},
                {"type": "input_text", "text": prev_chapter_context},
                {"type": "input_text", "text": user_request},
            ],
        },
    ]


def plan_titles(
    client: OpenAI,
    agent_md: str,
    season_template_md: str,
    season_number: int,
    chapter_number: int,
    previous_chapter_md: str,
    season_file_md: str,
) -> tuple[str, str]:
    system_instructions = f"""
You are planning metadata for the serialized horror project "Anomaly Archives".
Your task is to select or confirm a strong Season title and a compelling Chapter title.

Rules:
- Season title should be atmospheric and thematic for Season {season_number}.
- Chapter title should fit the tone and specific focus of Chapter {chapter_number}.
- Respond with a single JSON object only, no extra commentary.
- JSON keys: "season_title" (string), "chapter_title" (string).
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
Using the AGENT instructions and the Anomaly Archives Season 1 template, propose titles.
Return ONLY JSON with this shape:
{{
  "season_title": "<season title>",
  "chapter_title": "<chapter title>"
}}
"""

    messages = [
        {
            "role": "system",
            "content": [
                {"type": "input_text", "text": system_instructions},
                {"type": "input_text", "text": "AGENT INSTRUCTIONS:\n\n" + agent_md},
                {
                    "type": "input_text",
                    "text": "SEASON 1 TEMPLATE / SERIES PREMISE:\n\n"
                    + season_template_md,
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": season_context},
                {"type": "input_text", "text": prev_chapter_context},
                {"type": "input_text", "text": user_request},
            ],
        },
    ]

    response = client.responses.create(
        model=MODEL,
        input=messages,
        text={"format": {"type": "text"}, "verbosity": "low"},
        reasoning={"effort": "low", "summary": "detailed"},
        tools=[],
        store=False,
    )

    raw_text = ""
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    raw_text += content.text

    raw_text = raw_text.strip()
    if not raw_text:
        raise RuntimeError("No title metadata returned from model.")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse title JSON: {raw_text}") from exc

    season_title = str(data.get("season_title") or "").strip()
    chapter_title = str(data.get("chapter_title") or "").strip()

    if not season_title or not chapter_title:
        raise RuntimeError(f"Incomplete titles from model: {data!r}")

    return season_title, chapter_title


def generate_chapter() -> None:
    latest_season = find_latest_season(BASE_DIR)

    if latest_season == 0:
        season_number = 1
        chapter_number = 1
    else:
        current_season_dir = get_season_dir(latest_season)
        latest_chapter = find_latest_chapter(current_season_dir)

        if latest_chapter >= MAX_CHAPTERS_PER_SEASON:
            season_number = latest_season + 1
            chapter_number = 1
        else:
            season_number = latest_season
            chapter_number = latest_chapter + 1

    agent_md = read_text(AGENT_FILE)
    season_template_md = read_text(SEASON1_TEMPLATE_FILE)

    client = OpenAI()

    # Existing season context (if any)
    existing_season_dir = get_season_dir(season_number)
    season_file = get_season_file(season_number)
    season_file_md = read_text(season_file)
    prev_chapter_md = load_previous_chapter(season_number, chapter_number)

    # First call: plan titles (plan-act pattern)
    season_title, chapter_title = plan_titles(
        client=client,
        agent_md=agent_md,
        season_template_md=season_template_md,
        season_number=season_number,
        chapter_number=chapter_number,
        previous_chapter_md=prev_chapter_md,
        season_file_md=season_file_md,
    )

    # Create or reuse season directory using AI-generated title
    if existing_season_dir.exists():
        season_dir = existing_season_dir
    else:
        season_dir = BASE_DIR / f"season-{season_number}-{slugify(season_title)}"
        season_dir.mkdir(parents=True, exist_ok=True)

    season_file = season_dir / f"SEASON{season_number}.md"
    season_file_md = read_text(season_file)

    # Second call: generate chapter content
    messages = build_prompt(
        agent_md=agent_md,
        season_template_md=season_template_md,
        season_number=season_number,
        chapter_number=chapter_number,
        previous_chapter_md=prev_chapter_md,
        season_file_md=season_file_md,
        season_title=season_title,
        chapter_title=chapter_title,
    )

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
            for content in item.content:
                if content.type == "output_text":
                    output_text += content.text

    if not output_text.strip():
        raise RuntimeError("No chapter text returned from model.")

    if not season_file_md.strip():
        season_file.write_text(
            f"# Season {season_number}: {season_title}\n\n"
            "_(Auto-generated season file. You can edit this to refine the season overview.)_\n",
            encoding="utf-8",
        )

    chapter_slug = slugify(chapter_title)
    chapter_file = season_dir / f"chapter-{chapter_number}-{chapter_slug}.md"
    chapter_file.write_text(output_text, encoding="utf-8")

    print(
        f"Generated Season {season_number} ('{season_title}'), "
        f"Chapter {chapter_number} ('{chapter_title}'): {chapter_file}"
    )


if __name__ == "__main__":
    generate_chapter()
