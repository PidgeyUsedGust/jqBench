import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from jsonargparse import ArgumentParser
from pydantic import BaseModel, Field, JsonValue
from tqdm import tqdm

from experiments.inference.settings import Settings
from experiments.llm import (
    ChatModel,
    ChatRequest,
    JsonCache,
    Message,
    Role,
)
from experiments.paths import paths
from generation.stack.a_find import Question

data_in = Settings.data / "a_find" / "posts.jsonl"
data_out = Settings.data / "b_extract" / "extracted.json"

cache_root = (paths.reports.parent / "runs" / "caches") / "extract"


class ExtractedCandidate(BaseModel):
    original: str
    jq: str


class ExtractedData(BaseModel):
    input: JsonValue
    output: Optional[JsonValue] = None


class ExtractedTask(BaseModel):
    low: str
    high: str


class ExtractedBenchmark(BaseModel):
    identifier: Optional[int] = Field(validation_alias="id")
    context: list[str]
    task: ExtractedTask
    expressions: list[ExtractedCandidate] = Field(default_factory=list)
    data: list[ExtractedData] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


def format_question(question: Question) -> str:
    formatted = "<title>" + (question.post.title.strip() or "") + "</title>\n"
    formatted += "<question>" + (question.post.body.strip() or "") + "</question>\n"
    formatted += "<answers>\n"
    for answer_id in sorted(question.answers):
        answer = question.answers[answer_id]
        formatted += "<answer>\n"
        if answer.title:
            formatted += "<title>" + (answer.title.strip() or "") + "</title>\n"
        formatted += "<body>" + (answer.body.strip() or "") + "</body>\n"
        formatted += "</answer>\n"
    formatted += "</answers>"
    return formatted


SYSTEM = """

You are an expert in jq and JSON data transformation.
Your task is to extract a structured benchmark from a Stack Overflow discussion about querying, filtering or transforming JSON using `jq`.
The benchmark should reflect a single, well-defined, standalone problem and its solution.

# 🔄 Input

A raw Stack Overflow thread (question and answers) discussing a JSON-related problem.

# 📦 Output

Return a JSON object that conforms to the following TypeScript interface:

```typescript
interface Benchmark {
    context: string[];         // Direct quotes from the forum post and answers that capture the key problem and solution.
    task: Task;                // A task description at two levels of detail.
    expressions: Candidate[];  // Candidate `jq` expressions that solve the problem.
    data?: Data[];             // Optional: input JSON and expected output if available.
}

interface Task {
   low: string;   // A precise, unambiguous description of the JSON problem.
   high: string;  // A higher-level description of the JSON problem.
}

interface Candidate {
   original: string;      // An expression (`jq` or another scripting or querying language) that solves the problem.
   jq: string;            // The equivalent or corrected `jq` expression.
}

interface Data {
   input?: any;   // If mentioned, input data.
   output?: any;  // If mentioned, the expected result of the query.
}
```

If a benchmark that satisfies the criteria (see Guidelines > Task) cannot be extracted from the post, return an empty JSON object: `{}`.

# 🧭 Guidelines

## Context

- Include only direct quotes, no paraphrasing.

## Task

- The low-level description should be precise and unambiguous (can deviate from original phrasing).
- The high-level description should be more user-like and less formal (cannot deviate from original phrasing).

For both levels:

- Ensure that the task is realistic and can be solved with `jq`.
- The task must be a self-contained JSON transformation problem where:
  - Input is JSON (or can be treated as JSON).
  - Output is derived purely from the input using jq operations.
  - No external environment dependencies (shell variables, environment variables, file I/O).
  - No command-line tools other than `jq` itself.
- Avoid details about the solution that can be derived from the data:
  - The structure of the input JSON.
  - The exact path of values in the input JSON.
- Avoid details from the original discussion that are not essential to the problem:
  - The programming language used to ask the question.
  - The source of the JSON data, if adapted from another format (e.g., XML, CSV, HTML).
  - The destination of the JSON data (e.g., database, file, variable).
  - Specific command-line tools or scripts (e.g., curl, aws, git).
  - Shell scripting context or variable assignments.
  - File paths or file system operations.

If the original discussion is not about a JSON transformation problem that can be solved with `jq`, create a new, realistic JSON problem inspired by the discussion.

## Candidates

- Candidates are not required to be correct, but they should be plausible and relevant.
- Include all relevant expressions from the discussion.
- The `original` field should contain the expression as presented in the post.
- The `original` field may contain expressions in other querying or scripting languages, but NOT natural language descriptions.
- If the original expression is in another language, provide a plausible `jq` equivalent.
- If the original expression is in `jq`, ensure it is syntactically correct in the `jq` field.

## Data

- Include input values mentioned in the post, if any.
- Include expected output values mentioned in the post, if any, such that `output` is the result of applying the `jq` expression to the `input`.
- Create one `Data` entry per input example.

""".strip()


def process_post(post: Question, model: ChatModel) -> Optional[ExtractedBenchmark]:
    """Process a single post and return structured benchmark with identifier."""
    response = model.chat(
        [
            Message(role=Role.System, content=SYSTEM),
            Message(role=Role.User, content=format_question(post)),
        ],
        ChatRequest(response_format={"type": "json_object"}),
    )
    response_json = response.json or {}
    if response_json:
        try:
            return ExtractedBenchmark.model_validate(response_json)
        except Exception:
            return None
    return dict()


if __name__ == "__main__":
    # fmt: off
    parser = ArgumentParser()
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--take", type=int, default=0)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    data_out.parent.mkdir(parents=True, exist_ok=True)
    # fmt: on

    # load model
    model_spec = args.model
    model_cache = JsonCache(
        cache_root / f"extract-{args.model.replace('/', '--')}.json"
    )
    model = ChatModel(model=model_spec, cache=model_cache)

    # load done
    done = list()
    with open(data_out, "r", encoding="utf-8") as f:
        done.extend(json.load(f))
    print(f"⚡  Loaded {len(done)} done items.")

    todo: list[Question] = list()
    with open(data_in, "r", encoding="utf-8") as f:
        if args.skip:
            for _ in range(args.skip):
                next(f)
        for line in f:
            line_question = Question.model_validate_json(line)
            if any(d["id"] == line_question.id for d in done):
                continue
            todo.append(line_question)
            if args.take and len(todo) >= args.take:
                break
    print(f"⚡  Loaded {len(todo)} todo items.")

    def save():
        with open(data_out, "w", encoding="utf-8") as f:
            d = json.dumps(done, indent=2)
            f.write(d)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_post, post, model): post for post in todo}
        for future in tqdm(
            as_completed(futures), total=len(futures), position=1, leave=False
        ):
            result = future.result()
            if result is None:
                continue
            if isinstance(result, ExtractedBenchmark):
                result = result.model_dump(mode="json")
            done.append({"id": futures[future].id, **result})
            if len(done) % 100 == 0:
                save()

    save()
