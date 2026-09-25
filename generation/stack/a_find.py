import re
import xml.etree.ElementTree as ET
from itertools import islice
from pathlib import Path
from typing import Iterable, Literal, Optional

from jsonargparse import ArgumentParser
from pydantic import BaseModel, Field
from tqdm import tqdm

from experiments.inference.settings import Settings
from experiments.paths import paths

dump_file = paths.posts
output_file = Settings.data / "a_find" / "posts.jsonl"
status_file = Settings.data / "a_find" / "status.json"


keywords = ["jq", "jslt", "josson", "jolt", "jmespath", "jsonata", "jsonpatch", "pyjq"]
keyword_regex = r"\b(" + "|".join(keywords) + r")\b"


class Post(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    score: Optional[int] = None


class Question(BaseModel):
    id: int
    post: Post
    tags: list[str] = Field(default_factory=list)
    answers: dict[int, Post] = Field(default_factory=dict)
    accepted: Optional[int] = None


class Match(BaseModel):
    type: Literal["Question", "Answer"]
    id: int
    parent: Optional[int] = None
    tags: set[str] = None
    keywords: set[str] = None


class Status(BaseModel):
    done: int = 0

    # count the number of keywords and keywords found
    found: dict[str, int] = Field(
        default_factory=lambda: {keyword: 0 for keyword in keywords}
    )

    # store the matched posts
    matches: list[Match] = Field(default_factory=list)


def get_match(post: dict) -> Optional[Match]:
    match_type = {"1": "Question", "2": "Answer"}.get(post["PostTypeId"], None)
    if match_type is None:
        return None
    tags = post.get("Tags", "").strip("<>").split("><")
    text = f"{post.get('Title', '').lower()}\n{post.get('Body', '').lower()}"
    if match_type == "Question":
        if matched_tags := {keyword for keyword in keywords if keyword in tags}:
            return Match(id=int(post["Id"]), type=match_type, tags=matched_tags)
        if ("json" not in tags) or ("json" not in text) or ("jquery" in tags):
            return None
        if matched_keywords := re.findall(keyword_regex, text):
            return Match(
                id=int(post["Id"]), type=match_type, keywords=set(matched_keywords)
            )
    if match_type == "Answer":
        if "json" not in text:
            return None
        matched_keywords = re.findall(keyword_regex, text)
        if matched_keywords:
            if "jq" in matched_keywords and "jquery" in text:
                return None
            return Match(
                id=int(post["Id"]),
                parent=int(post["ParentId"]),
                type=match_type,
                keywords=set(matched_keywords),
            )
    return None


def get_post(post: dict) -> Post:
    if (body := post.get("Body")) is None:
        return None
    title = post.get("Title", "")
    if (id_ := post.get("Id")) is not None:
        id_ = int(id_)
    if (accept := post.get("AcceptedAnswerId")) is not None:
        accept = int(accept)
    if (score := post.get("Score")) is not None:
        score = int(score)
    if (parent := post.get("ParentId")) is not None:
        parent = int(parent)
    if (tags := post.get("Tags", list())) != list():
        tags = tags.strip("<>").split("><")
    return Post(
        id=id_,
        title=title,
        body=body,
        score=score,
        tags=tags,
        accept=accept,
        parent=parent,
    )


def get_posts(path: Path | str = dump_file) -> Iterable[dict]:
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag == "row":
            attr = elem.attrib
            elem.clear()
            yield attr


def cmd_extract():
    if status_file.exists():
        status = Status.model_validate_json(status_file.read_text())
    else:
        status = Status()
        status_file.parent.mkdir(parents=True, exist_ok=True)
    processed = status.done

    def save():
        status.done = processed
        status_file.write_text(status.model_dump_json(indent=2, exclude_none=True))

    pbar = tqdm(initial=processed)
    curr = 0
    for post in islice(get_posts(), status.done, None):
        post_match = get_match(post)
        processed += 1
        if post_match is not None:
            curr += 1
            status.matches.append(post_match)
            for keyword in post_match.keywords or list():
                status.found[keyword] += 1
            for tag in post_match.tags or list():
                status.found[tag] += 1
        pbar.update(1)
        if processed % 16e3 == 0:
            pbar.set_postfix(matched=len(status.matches), status=status.found)
        if curr == 128:
            curr = 0
            save()
    save()


def cmd_combine():
    if not status_file.exists():
        print(f"⚠️  Status file {status_file} does not exist")
        return
    status = Status.model_validate_json(status_file.read_text())
    questions: dict[int, Question] = dict()
    for match in status.matches:
        if match.type == "Question":
            questions[match.id] = Question(
                id=match.id, post=Post(), tags=list(match.tags or list())
            )
        if match.type == "Answer":
            if match.parent not in questions:
                questions[match.parent] = Question(
                    id=match.parent, post=Post(), tags=list()
                )
            questions[match.parent].answers[match.id] = Post()
    pbar = tqdm()
    for post in get_posts():
        post_type = {"1": "Question", "2": "Answer"}.get(post["PostTypeId"], None)
        if post_type is None:
            pbar.update(1)
            continue
        post_id = int(post["Id"])
        if post_type == "Question":
            if (question := questions.get(post_id)) is not None:
                question.post.body = post.get("Body", "")
                question.post.title = post.get("Title", "")
                question.post.score = int(post.get("Score", 0))
                question.accepted = (
                    int(post.get("AcceptedAnswerId"))
                    if post.get("AcceptedAnswerId") is not None
                    else None
                )
        if post_type == "Answer":
            if "ParentId" not in post:
                pbar.update(1)
                continue
            parent_id = int(post["ParentId"])
            if (question := questions.get(parent_id)) is not None:
                answer = question.answers.get(post_id)
                if answer is None:
                    answer = Post()
                    question.answers[post_id] = answer
                answer.body = post.get("Body", "")
                answer.score = int(post.get("Score", 0))
        pbar.update(1)
    with open(output_file, "w", encoding="utf-8") as f:
        for question in sorted(questions.values(), key=lambda q: q.id):
            f.write(question.model_dump_json(exclude_none=True) + "\n")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser_sub = parser.add_subcommands()

    parser_extract = ArgumentParser()
    parser_sub.add_subcommand("extract", parser_extract)

    parser_combine = ArgumentParser()
    parser_sub.add_subcommand("combine", parser_combine)

    args = parser.parse_args()

    if args.subcommand == "extract":
        cmd_extract()
    if args.subcommand == "combine":
        cmd_combine()
