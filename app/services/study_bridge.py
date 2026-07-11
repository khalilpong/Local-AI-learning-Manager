from __future__ import annotations

from dataclasses import dataclass, field

from app.services.memory import MemoryService


@dataclass
class ResultSection:
    kind: str
    fields: dict[str, str] = field(default_factory=dict)
    body: list[str] = field(default_factory=list)
    body_heading_seen: bool = False


class StudyBridgeService:
    def __init__(self, memory: MemoryService):
        self.memory = memory
        self.db = memory.db

    def export_pack(self, course_id: int) -> str:
        course = self.db.get_course(course_id)
        notes = [
            note
            for note in self.db.list_notes(limit=100000)
            if note.get("course_id") == course_id
        ]
        documents = self.db.list_source_documents(course_id)
        cards = self.db.list_study_cards(course_id=course_id, limit=1000)

        lines = [
            "# Local Memory Study Pack",
            "",
            f"Course: {course['name']}",
            f"Code: {course['code'] or 'N/A'}",
            f"Term: {course['term'] or 'N/A'}",
            "",
            "## ChatGPT Project Instructions",
            "",
            "- Use only the supplied local material when answering.",
            "- Do not invent facts, citations, or source locations.",
            "- Explain uncertain or missing evidence explicitly.",
            "- Return reviewed outputs using the Study Result template below.",
            "- Keep every card candidate atomic and answerable from one cited source.",
            "",
            "## Local Notes",
            "",
        ]
        if not notes:
            lines.extend(["No course notes.", ""])
        for note in reversed(notes):
            lines.extend(
                [
                    f"### {note['title']}",
                    f"Source: {note['source'] or 'manual note'}",
                    f"Tags: {', '.join(note['tags']) or 'none'}",
                    "",
                    note["content"],
                    "",
                ]
            )

        lines.extend(["## Source Documents", ""])
        if not documents:
            lines.extend(["No course documents.", ""])
        for document in reversed(documents):
            lines.extend([f"### {document['title']}", ""])
            chunks = self.db.list_document_chunks(document["id"])
            for chunk in chunks:
                citation = chunk["location_label"] or "document"
                lines.extend(
                    [
                        f"#### Citation: {document['title']} · {citation}",
                        "",
                        chunk["content"],
                        "",
                    ]
                )

        lines.extend(["## Existing Review Cards", ""])
        if not cards:
            lines.extend(["No review cards.", ""])
        for card in reversed(cards):
            lines.extend(
                [
                    f"### {card['prompt']}",
                    f"State: {card['state']}",
                    f"Source: {card['source_label'] or 'Local Memory'}",
                    "",
                    card["answer"],
                    "",
                ]
            )

        lines.extend(
            [
                "## Study Result Template",
                "",
                "```markdown",
                "# Local Memory Study Result",
                "## Reviewed Note",
                "Title: <title>",
                "Source: <citation>",
                "### Content",
                "<reviewed note>",
                "## Card Candidate",
                "Prompt: <question>",
                "Source: <citation>",
                "### Answer",
                "<answer>",
                "```",
                "",
            ]
        )
        return "\n".join(lines)

    def import_result(self, course_id: int, markdown: str) -> dict:
        self.db.get_course(course_id)
        sections = self._parse_sections(markdown)
        notes = [section for section in sections if section.kind == "note"]
        cards = [section for section in sections if section.kind == "card"]
        for section in notes:
            self.memory.create_note(
                title=section.fields["title"],
                content="\n".join(section.body).strip(),
                source=section.fields.get("source", "ChatGPT study result"),
                course_id=course_id,
            )
        for section in cards:
            self.memory.study.create_candidate(
                prompt=section.fields["prompt"],
                answer="\n".join(section.body).strip(),
                source_label=section.fields.get("source", "ChatGPT study result"),
                course_id=course_id,
            )
        return {"notes": len(notes), "card_candidates": len(cards)}

    def _parse_sections(self, markdown: str) -> list[ResultSection]:
        sections: list[ResultSection] = []
        current: ResultSection | None = None

        def finish() -> None:
            nonlocal current
            if current is None:
                return
            body = "\n".join(current.body).strip()
            required_field = "title" if current.kind == "note" else "prompt"
            if (
                not current.fields.get(required_field, "").strip()
                or not current.body_heading_seen
                or not body
            ):
                raise ValueError(f"Malformed {current.kind} section")
            current.body = body.splitlines()
            sections.append(current)
            current = None

        for raw_line in markdown.replace("\r\n", "\n").split("\n"):
            line = raw_line.rstrip()
            if line == "## Reviewed Note":
                finish()
                current = ResultSection(kind="note")
                continue
            if line == "## Card Candidate":
                finish()
                current = ResultSection(kind="card")
                continue
            if current is None:
                continue
            expected_body_heading = (
                "### Content" if current.kind == "note" else "### Answer"
            )
            if line == expected_body_heading:
                current.body_heading_seen = True
                continue
            if not current.body_heading_seen:
                field_name, separator, value = line.partition(":")
                key = field_name.strip().lower()
                allowed = {"title", "source"} if current.kind == "note" else {
                    "prompt",
                    "source",
                }
                if separator and key in allowed:
                    current.fields[key] = value.strip()
                elif line.strip():
                    raise ValueError(f"Unexpected field in {current.kind} section")
            else:
                current.body.append(line)
        finish()
        if not sections:
            raise ValueError("No structured study result sections found")
        return sections
