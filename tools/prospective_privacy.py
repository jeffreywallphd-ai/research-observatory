"""Prospective Git privacy checks; existing approved history is not rewritten."""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.abc
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from types import ModuleType
from urllib.parse import unquote

PROTECTED = "artifacts/evidence/W1.A04.B00.json"
RAW_REPORTS = {"artifacts/bootstrap/bootstrap-report.json", "artifacts/bootstrap/setup-verification.json"}
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
EMAIL_LOCAL = r"A-Za-z0-9.!#$%&'*+/=?^_`{|}~-"
EMAIL = re.compile(rf"(?<![{EMAIL_LOCAL}])[{EMAIL_LOCAL}]+@[A-Za-z0-9.-]+\.[A-Za-z]{{2,}}")
PROFILE = re.compile(r"(?i)(?:[a-z]:/|(?<![\w:])/)(?:users|home|documents and settings)/([^/\s\"'<>`]+)")
WORKSPACE = re.compile(r"(?i)[a-z]:/ai-projects(?:/|\b)")
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".exe", ".dll"}
RETIRED_REFS = {
    "refs/heads/codex/t03-lineage-safety-92ec600",
    "refs/heads/codex/t03-unsplit-backup",
    "refs/heads/codex/w1-t02-invalid-hardening-backup",
}
REDIRECT = {"GIT_DIR", "GIT_WORK_TREE", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_SHALLOW_FILE", "GIT_GRAFT_FILE"}
YAML_SOURCE_NAMES = tuple(
    name + ".py"
    for name in (
        "__init__",
        "composer",
        "constructor",
        "dumper",
        "emitter",
        "error",
        "events",
        "loader",
        "nodes",
        "parser",
        "reader",
        "representer",
        "resolver",
        "scanner",
        "serializer",
        "tokens",
    )
)


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args], input=data, capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError("Git input could not be verified")
    return result.stdout


def normalize(text: str) -> str:
    for _ in range(4):
        text = html.unescape(unquote(text))
        text = re.sub(r"\\u([0-9a-f]{4})", lambda m: chr(int(m[1], 16)), text, flags=re.I)
    return re.sub(r"\\+", "/", text)


def text_reasons(text: str, allowed: set[str], *, metadata: bool = False) -> set[str]:
    value = normalize(text)
    reasons = set()
    if any(m[1].casefold() not in {"researcher", "redacted-user"} for m in PROFILE.finditer(value)):
        reasons.add("personal-profile-path")
    if WORKSPACE.search(value):
        reasons.add("concrete-workspace-path")
    for email in EMAIL.findall(value):
        domain = email.rpartition("@")[2].casefold()
        safe = domain in {"users.noreply.github.com", "example.invalid"}
        if not metadata:
            safe = safe or domain in {"example.com", "example.org", "example.net", "example.test"}
            safe = safe or domain.endswith(".invalid") or email.casefold() in allowed
        if not safe:
            reasons.add("non-public-email")
    return reasons


def validate_path(path: str) -> None:
    lower = path.casefold()
    if lower == PROTECTED.casefold():
        raise ValueError("Protected witness is tracked; no content read")
    if lower.startswith((".local/", "artifacts/tmp/")):
        raise ValueError("Ignored private output is tracked")


def entries(repo: Path, commit: str | None) -> dict[str, tuple[str, str]]:
    result = {}
    args = ("ls-files", "--stage", "-z") if commit is None else ("ls-tree", "-r", "-z", commit)
    for record in git(repo, *args).split(b"\0"):
        if not record:
            continue
        fields, raw_path = record.split(b"\t", 1)
        mode, second, third = fields.decode("ascii").split()
        path = raw_path.decode("utf-8")
        validate_path(path)
        if commit is None:
            oid = second
            if third != "0":
                raise ValueError("Unmerged index is not publishable")
        else:
            oid = third
        result[path] = mode, oid
    return result


def validate_history(repo: Path, baseline: str) -> None:
    if not SHA.fullmatch(baseline):
        raise ValueError("Invalid approved baseline")
    if any(os.environ.get(key) for key in REDIRECT):
        raise ValueError("Ambient Git redirection is unsupported")
    git(repo, "rev-parse", "--verify", baseline + "^{commit}")
    if git(repo, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ValueError("Full history is required")
    for name in ("info/grafts", "objects/info/alternates"):
        path = Path(git(repo, "rev-parse", "--git-path", name).decode().strip())
        if (path if path.is_absolute() else repo / path).exists():
            raise ValueError("Substituted history is unsupported")
    if git(repo, "for-each-ref", "--format=%(refname)", "refs/replace").strip():
        raise ValueError("Replacement history is unsupported")
    # Names only, including deleted versions. Never read the protected witness.
    if git(repo, "log", "--format=", "--name-only", baseline, "--", PROTECTED).strip():
        raise ValueError("Protected witness in baseline history; no content read")


def changed_entries(
    current: dict[str, tuple[str, str]], predecessors: list[dict[str, tuple[str, str]]]
) -> dict[str, tuple[str, str]]:
    # A merge entry must be unchanged in every parent to skip inspection.
    return {
        p: item for p, item in current.items() if not predecessors or any(old.get(p) != item for old in predecessors)
    }


def reviewed_artifacts(reviews: dict | None, policy: dict, config: Path) -> dict[tuple[str, str, str, int], dict]:
    """Validate an externally reviewed, installer-sealed registry; never a live repo allowlist."""
    if reviews is None:
        return {}
    required = {
        "schemaVersion",
        "documentType",
        "baselineCommit",
        "scannerSha256",
        "configSha256",
        "reviewer",
        "implementer",
        "disposition",
        "rationale",
        "artifacts",
    }
    if not isinstance(reviews, dict) or set(reviews) not in (required, required | {"preservation"}):
        raise ValueError("Malformed artifact review")
    expected = {
        "schemaVersion": "1.0",
        "documentType": "independent-artifact-privacy-review",
        "baselineCommit": policy["baselineCommit"],
        "scannerSha256": policy["scannerSha256"],
        "configSha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "disposition": "approved",
    }
    if any(reviews.get(key) != value for key, value in expected.items()):
        raise ValueError("Artifact review authority differs")
    if any(not isinstance(reviews[k], str) or not reviews[k].strip() for k in ("reviewer", "implementer", "rationale")):
        raise ValueError("Missing independent artifact review")
    if reviews["reviewer"].strip().casefold() == reviews["implementer"].strip().casefold():
        raise ValueError("Artifact review is not independent")
    if "preservation" in reviews:
        preservation_documents(reviews["preservation"])
    artifacts = reviews["artifacts"]
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 2000:
        raise ValueError("Invalid artifact review inventory")
    result = {}
    fields = {"path", "mode", "sha256", "size", "binaryReviewed", "nonEmailTokens", "credentialFindingFingerprints"}
    for item in artifacts:
        if not isinstance(item, dict) or set(item) not in (fields, fields | {"retainedMetadata"}):
            raise ValueError("Malformed artifact admission")
        path = item["path"]
        if not isinstance(path, str) or not path or "\\" in path or ":" in path:
            raise ValueError("Invalid reviewed artifact path")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or parsed.as_posix() != path or ".." in parsed.parts:
            raise ValueError("Noncanonical reviewed artifact path")
        validate_path(path)
        if path.casefold() in RAW_REPORTS or text_reasons(path, set()):
            raise ValueError("Private reviewed artifact name")
        if item["mode"] not in {"100644", "100755"} or type(item["binaryReviewed"]) is not bool:
            raise ValueError("Invalid reviewed artifact mode")
        if type(item["size"]) is not int or not 0 <= item["size"] <= 16 * 1024 * 1024:
            raise ValueError("Invalid reviewed artifact size")
        if not isinstance(item["sha256"], str) or not SHA256.fullmatch(item["sha256"]):
            raise ValueError("Invalid reviewed artifact digest")
        tokens, fingerprints = item["nonEmailTokens"], item["credentialFindingFingerprints"]
        if not isinstance(tokens, list) or any(not isinstance(t, str) for t in tokens):
            raise ValueError("Malformed non-email adjudication")
        for token in tokens:
            token_path = PurePosixPath(token)
            if (
                normalize(token) != token
                or "/" not in token
                or ":" in token
                or token_path.is_absolute()
                or ".." in token_path.parts
                or token_path.as_posix() != token
                or not EMAIL.fullmatch(token)
                or token_path.suffix.lower() not in BINARY
                or text_reasons(token, {token.casefold()})
            ):
                raise ValueError("Non-email review must identify an exact safe relative artifact filename")
        if (
            not isinstance(fingerprints, list)
            or any(not isinstance(f, str) or not SHA256.fullmatch(f) for f in fingerprints)
            or len(set(fingerprints)) != len(fingerprints)
            or len(set(tokens)) != len(tokens)
        ):
            raise ValueError("Malformed finding adjudication")
        identity = path, item["mode"], item["sha256"], item["size"]
        if identity in result:
            raise ValueError("Duplicate artifact admission")
        if "retainedMetadata" in item:
            validate_retention_records(item)
        result[identity] = item
    return result


def preservation_documents(value: dict) -> dict[str, dict]:
    """Opt-in sealed seed authority; exact historical artifact admissions remain separate."""
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "parserSha256", "workerSha256", "documents"}:
        raise ValueError("Malformed metadata preservation policy")
    if (
        value["schemaVersion"] != "1.0"
        or not isinstance(value["parserSha256"], str)
        or not SHA256.fullmatch(value["parserSha256"])
        or not isinstance(value["workerSha256"], str)
        or not SHA256.fullmatch(value["workerSha256"])
    ):
        raise ValueError("Invalid preservation parser binding")
    documents = value["documents"]
    if not isinstance(documents, list) or not 1 <= len(documents) <= 32:
        raise ValueError("Invalid preservation document inventory")
    result = {}
    required = {
        "path",
        "mode",
        "baselineBlob",
        "baselineSha256",
        "baselineSize",
        "seedCommit",
        "seedBlob",
        "seedSha256",
        "seedSize",
        "fields",
    }
    for document in documents:
        if not isinstance(document, dict) or set(document) != required:
            raise ValueError("Malformed preservation document")
        path = document["path"]
        if not isinstance(path, str) or not path or "\\" in path or ":" in path:
            raise ValueError("Invalid preservation path")
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or parsed.as_posix() != path
            or ".." in parsed.parts
            or parsed.suffix not in {".yaml", ".yml"}
        ):
            raise ValueError("Preservation requires one canonical YAML document")
        validate_path(path)
        if text_reasons(path, set()) or document["mode"] != "100644" or path in result:
            raise ValueError("Private, nonregular or duplicate preservation path")
        for key in ("baselineBlob", "seedCommit", "seedBlob"):
            if not isinstance(document[key], str) or not SHA.fullmatch(document[key]):
                raise ValueError("Invalid preservation Git binding")
        for key in ("baselineSha256", "seedSha256"):
            if not isinstance(document[key], str) or not SHA256.fullmatch(document[key]):
                raise ValueError("Invalid preservation raw binding")
        for key in ("baselineSize", "seedSize"):
            if type(document[key]) is not int or not 0 < document[key] <= 16 * 1024 * 1024:
                raise ValueError("Invalid preservation size")
        fields = document["fields"]
        if not isinstance(fields, list) or not 1 <= len(fields) <= 10000:
            raise ValueError("Invalid preservation field inventory")
        selectors, lines = set(), set()
        for field in fields:
            if not isinstance(field, dict) or set(field) != {"selector", "baselineLine", "sha256"}:
                raise ValueError("Malformed preservation field")
            selector = field["selector"]
            if not isinstance(selector, list) or not 1 <= len(selector) <= 64:
                raise ValueError("Invalid preservation selector")
            for part in selector:
                if not isinstance(part, dict) or len(part) != 1 or next(iter(part)) not in {"key", "id"}:
                    raise ValueError("Preservation requires typed stable key/record-ID selectors")
                item = next(iter(part.values()))
                if not isinstance(item, str) or not item or text_reasons(item, set()):
                    raise ValueError("Invalid preservation selector value")
            identity = json.dumps(selector, sort_keys=True, separators=(",", ":"))
            line = field["baselineLine"]
            if identity in selectors or type(line) is not int or line < 1 or line in lines:
                raise ValueError("Duplicate or invalid preservation field location")
            if not isinstance(field["sha256"], str) or not SHA256.fullmatch(field["sha256"]):
                raise ValueError("Invalid preservation line digest")
            selectors.add(identity)
            lines.add(line)
        result[path] = document
    return result


def _load_sealed_yaml(parser_raw: bytes) -> None:
    """Execute only source bytes from the already authenticated in-memory ZIP snapshot."""
    if len(parser_raw) > 1024 * 1024 or any(name == "yaml" or name.startswith("yaml.") for name in sys.modules):
        raise ValueError("Unexpected parser runtime state")
    with zipfile.ZipFile(io.BytesIO(parser_raw)) as archive:
        names = archive.namelist()
        if len(names) != len(YAML_SOURCE_NAMES) or set(names) != {"yaml/" + name for name in YAML_SOURCE_NAMES}:
            raise ValueError("Unexpected parser source inventory")
        if sum(info.file_size for info in archive.infolist()) > 1024 * 1024:
            raise ValueError("Oversized parser source inventory")
        sources = {name: archive.read(name) for name in names}

    class SealedYamlImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        def find_spec(self, fullname: str, path: object = None, target: ModuleType | None = None):
            if fullname != "yaml" and not fullname.startswith("yaml."):
                return None
            name = "yaml/__init__.py" if fullname == "yaml" else fullname.replace(".", "/") + ".py"
            if name not in sources:
                raise ModuleNotFoundError("Only authenticated pure-Python YAML modules are available")
            return importlib.util.spec_from_loader(fullname, self, is_package=fullname == "yaml")

        def create_module(self, spec):
            return None

        def exec_module(self, module: ModuleType) -> None:
            name = "yaml/__init__.py" if module.__name__ == "yaml" else module.__name__.replace(".", "/") + ".py"
            module.__file__ = "sealed-parser/" + name
            exec(compile(sources[name], module.__file__, "exec"), module.__dict__)

    sys.meta_path.insert(0, SealedYamlImporter())


def _yaml_private_fields(raw: bytes, allowed: set[str]) -> list[dict]:
    """Runs only inside the isolated pinned-parser worker; never constructs YAML objects."""
    import yaml

    if len(raw) > 16 * 1024 * 1024 or b"\0" in raw:
        raise ValueError("Structured metadata must be bounded UTF-8 text")
    try:
        root = yaml.compose(raw.decode("utf-8"), Loader=yaml.SafeLoader)
    except (yaml.YAMLError, UnicodeError, RecursionError) as exc:
        raise ValueError("Structured metadata cannot be parsed safely") from exc
    contents = raw.splitlines(keepends=True)
    found: list[dict] = []
    active: set[int] = set()
    visits = 0
    scalar_tags = {"tag:yaml.org,2002:" + name for name in ("str", "null", "bool", "int", "float", "timestamp")}

    def walk(node: object, selector: list[dict], depth: int) -> None:
        nonlocal visits
        visits += 1
        if depth > 64 or visits > 1000000 or id(node) in active:
            raise ValueError("Cyclic or excessive YAML structure")
        active.add(id(node))
        if isinstance(node, yaml.MappingNode):
            if node.tag != "tag:yaml.org,2002:map":
                raise ValueError("Unsupported YAML mapping tag")
            keys = []
            for key, child in node.value:
                if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str" or key.value == "<<":
                    raise ValueError("Ambiguous YAML mapping key")
                if text_reasons(key.value, allowed):
                    raise ValueError("Private decoded YAML mapping key")
                keys.append(key.value)
                walk(child, [*selector, {"key": key.value}], depth + 1)
            if len(keys) != len(set(keys)):
                raise ValueError("Duplicate YAML mapping keys")
        elif isinstance(node, yaml.SequenceNode):
            if node.tag != "tag:yaml.org,2002:seq":
                raise ValueError("Unsupported YAML sequence tag")
            identities = set()
            for index, child in enumerate(node.value):
                identity = None
                if isinstance(child, yaml.MappingNode):
                    ids = [v for k, v in child.value if isinstance(k, yaml.ScalarNode) and k.value == "id"]
                    if ids:
                        if (
                            len(ids) != 1
                            or not isinstance(ids[0], yaml.ScalarNode)
                            or ids[0].tag != "tag:yaml.org,2002:str"
                            or not ids[0].value
                        ):
                            raise ValueError("Ambiguous YAML record identity")
                        identity = ids[0].value
                        if identity in identities:
                            raise ValueError("Duplicate YAML record identity")
                        identities.add(identity)
                walk(child, [*selector, {"id": identity} if identity is not None else {"index": index}], depth + 1)
        elif isinstance(node, yaml.ScalarNode):
            if node.tag not in scalar_tags:
                raise ValueError("Unsupported YAML scalar tag")
            if text_reasons(node.value, allowed):
                if any("index" in part for part in selector) or node.start_mark.line != node.end_mark.line:
                    raise ValueError("Private metadata lacks a stable single-line location")
                line = node.start_mark.line
                found.append(
                    {"selector": selector, "line": line + 1, "sha256": hashlib.sha256(contents[line]).hexdigest()}
                )
        else:
            raise ValueError("Unsupported YAML document")
        active.remove(id(node))

    walk(root, [], 0)
    if len({item["line"] for item in found}) != len(found):
        raise ValueError("Private YAML aliases do not have independent unchanged raw lines")
    return found


PRESERVATION_WORKER_BOOTSTRAP = """import io, json, sys
packet = json.loads(sys.stdin.buffer.read())
sys.stdin = io.TextIOWrapper(io.BytesIO(packet["request"].encode("utf-8")), encoding="utf-8")
exec(compile(packet["source"], "<sealed-privacy-worker>", "exec"),
     {"__name__": "__main__", "__file__": "<sealed-privacy-worker>"})
"""


def yaml_private_fields(raw: bytes, parser: Path, parser_sha: str, worker_sha: str, allowed: set[str]) -> list[dict]:
    # A worker retains -I -S even when a library caller has already imported an
    # unrelated mutable yaml module. No repository/site-package import can win.
    if parser.is_symlink() or hashlib.sha256(parser.read_bytes()).hexdigest() != parser_sha:
        raise ValueError("Preservation parser pin differs")
    worker = Path(__file__)
    worker_raw = worker.read_bytes()
    if worker.is_symlink() or hashlib.sha256(worker_raw).hexdigest() != worker_sha:
        raise ValueError("Preservation worker pin differs")
    # Execute the held authenticated source, not its mutable pathname. The
    # child likewise imports the parser only from its held authenticated bytes.
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            PRESERVATION_WORKER_BOOTSTRAP,
            "yaml-fields",
            str(parser.resolve()),
            parser_sha,
        ],
        input=json.dumps(
            {
                "source": worker_raw.decode("utf-8"),
                "request": json.dumps({"text": raw.decode("utf-8"), "allowed": sorted(allowed)}),
            }
        ).encode(),
        capture_output=True,
        check=False,
        timeout=30,
    )
    if process.returncode:
        raise ValueError("Structured metadata parsing was denied")
    value = json.loads(process.stdout)
    if not isinstance(value, list):
        raise ValueError("Invalid structured metadata parser result")
    return value


def preservation_receipt(
    repo: Path,
    raw: bytes,
    path: str,
    mode: str,
    document: dict,
    parents: list[str],
    prior: list[dict[str, tuple[str, str]]],
    baseline_entries: dict[str, tuple[str, str]],
    baseline: str,
    parser: Path,
    parser_sha: str,
    worker_sha: str,
    allowed: set[str],
    cache: dict[str, list[dict]],
) -> dict:
    """Derive only exact unchanged-field receipts; no future bytes or new locations are trusted."""
    if len(parents) != 1 or len(prior) != 1 or mode != document["mode"] or path not in prior[0]:
        raise ValueError("Preservation requires one existing same-mode predecessor")
    if prior[0][path][0] != mode or baseline_entries.get(path) != (mode, document["baselineBlob"]):
        raise ValueError("Preservation path/mode/baseline differs")
    git(repo, "merge-base", "--is-ancestor", baseline, document["seedCommit"])
    git(repo, "merge-base", "--is-ancestor", document["seedCommit"], parents[0])
    seed_tree = git(repo, "ls-tree", document["seedCommit"], "--", path).decode().split("\t", 1)[0].split()
    if seed_tree != [mode, "blob", document["seedBlob"]]:
        raise ValueError("Preservation seed path/blob differs")
    snapshots = {"successor": raw}
    for label, oid in (
        ("baseline", document["baselineBlob"]),
        ("seed", document["seedBlob"]),
        ("predecessor", prior[0][path][1]),
    ):
        size = int(git(repo, "cat-file", "-s", oid))
        if size > 16 * 1024 * 1024:
            raise ValueError("Preservation source is oversized")
        payload = git(repo, "cat-file", "blob", oid)
        if label != "predecessor" and (
            size != document[label + "Size"] or hashlib.sha256(payload).hexdigest() != document[label + "Sha256"]
        ):
            raise ValueError("Preservation source binding differs")
        snapshots[label] = payload
    expected = {
        json.dumps(item["selector"], sort_keys=True, separators=(",", ":")): item for item in document["fields"]
    }
    maps = {}
    for label, payload in snapshots.items():
        digest = hashlib.sha256(payload).hexdigest()
        if digest not in cache:
            cache[digest] = yaml_private_fields(payload, parser, parser_sha, worker_sha, allowed)
        fields = cache[digest]
        mapping = {json.dumps(item["selector"], sort_keys=True, separators=(",", ":")): item for item in fields}
        if len(mapping) != len(fields) or set(mapping) != set(expected):
            raise ValueError("Preservation private-field inventory changed")
        for selector, item in mapping.items():
            if item["sha256"] != expected[selector]["sha256"] or (
                label == "baseline" and item["line"] != expected[selector]["baselineLine"]
            ):
                raise ValueError("Preservation private field changed or was re-encoded")
        maps[label] = mapping
    return {
        "retainedMetadata": [
            {
                "predecessorCommit": parents[0],
                "baselineBlob": document["baselineBlob"],
                "baselineSha256": document["baselineSha256"],
                "baselineSize": document["baselineSize"],
                "predecessorBlob": prior[0][path][1],
                "predecessorSha256": hashlib.sha256(snapshots["predecessor"]).hexdigest(),
                "predecessorSize": len(snapshots["predecessor"]),
                "lines": [
                    {
                        "baselineLine": maps["baseline"][key]["line"],
                        "predecessorLine": maps["predecessor"][key]["line"],
                        "successorLine": maps["successor"][key]["line"],
                        "sha256": item["sha256"],
                    }
                    for key, item in expected.items()
                ],
            }
        ]
    }


def validate_retention_records(item: dict) -> None:
    """Validate sealed review shape; logical field equality is independent review's duty."""
    records = item["retainedMetadata"]
    if (
        item["binaryReviewed"]
        or Path(item["path"]).suffix.lower() in BINARY
        or not isinstance(records, list)
        or not 1 <= len(records) <= 2000
    ):
        raise ValueError("Retention requires reviewed regular text transitions")
    fields = {
        "schemaVersion",
        "disposition",
        "rationale",
        "baselineBlob",
        "baselineSha256",
        "baselineSize",
        "predecessorCommit",
        "predecessorBlob",
        "predecessorSha256",
        "predecessorSize",
        "lines",
    }
    line_fields = {
        "baselineLine",
        "predecessorLine",
        "successorLine",
        "sha256",
        "logicalLocation",
        "unchangedLogicalLocation",
    }
    parents = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != fields:
            raise ValueError("Malformed retained metadata transition")
        if record["schemaVersion"] != "1.0" or record["disposition"] != "unchanged-existing-metadata":
            raise ValueError("Retention cannot authorize new disclosures")
        if not isinstance(record["rationale"], str) or not record["rationale"].strip():
            raise ValueError("Retention review rationale is required")
        for key in ("baselineBlob", "predecessorCommit", "predecessorBlob"):
            if not isinstance(record[key], str) or not SHA.fullmatch(record[key]):
                raise ValueError("Invalid retention Git binding")
        for key in ("baselineSha256", "predecessorSha256"):
            if not isinstance(record[key], str) or not SHA256.fullmatch(record[key]):
                raise ValueError("Invalid retention raw binding")
        for key in ("baselineSize", "predecessorSize"):
            if type(record[key]) is not int or not 0 <= record[key] <= 16 * 1024 * 1024:
                raise ValueError("Invalid retention size")
        parent = record["predecessorCommit"]
        if parent in parents:
            raise ValueError("Duplicate retention predecessor")
        parents.add(parent)
        lines = record["lines"]
        if not isinstance(lines, list) or not 1 <= len(lines) <= 10000:
            raise ValueError("Retention requires bounded one-to-one line evidence")
        used: dict[str, set] = {key: set() for key in ("baselineLine", "predecessorLine", "successorLine")}
        for line in lines:
            if not isinstance(line, dict) or set(line) != line_fields:
                raise ValueError("Malformed retention line binding")
            if (
                line["unchangedLogicalLocation"] is not True
                or not isinstance(line["logicalLocation"], str)
                or not line["logicalLocation"].strip()
                or text_reasons(line["logicalLocation"], set())
                or not isinstance(line["sha256"], str)
                or not SHA256.fullmatch(line["sha256"])
            ):
                raise ValueError("Invalid independent logical-location disposition")
            for key, indexes in used.items():
                value = line[key]
                if type(value) is not int or value < 1 or value in indexes:
                    raise ValueError("Retention lines must be unique positive positions")
                indexes.add(value)


def retained_metadata_text(
    repo: Path,
    raw: bytes,
    path: str,
    mode: str,
    admission: dict,
    parents: list[str],
    prior: list[dict[str, tuple[str, str]]],
    baseline_entries: dict[str, tuple[str, str]],
    allowed: set[str],
) -> str:
    """Authenticate exact reviewed raw lines; never mask credentials or metadata inputs."""
    records = admission.get("retainedMetadata")
    if not records:
        return raw.decode("utf-8", errors="replace")
    if len(parents) != 1 or len(prior) != 1:
        raise ValueError("Retention requires one actual predecessor; merges are unsupported")
    matches = [record for record in records if record["predecessorCommit"] == parents[0]]
    if len(matches) != 1:
        raise ValueError("Retention receipt is stale for this predecessor edge")
    record = matches[0]
    if baseline_entries.get(path) != (mode, record["baselineBlob"]) or prior[0].get(path) != (
        mode,
        record["predecessorBlob"],
    ):
        raise ValueError("Retention path, mode or baseline/predecessor blob differs")
    snapshots = {"successor": raw}
    for label in ("baseline", "predecessor"):
        oid = record[label + "Blob"]
        if int(git(repo, "cat-file", "-s", oid)) != record[label + "Size"]:
            raise ValueError("Retention predecessor size differs")
        payload = git(repo, "cat-file", "blob", oid)
        if hashlib.sha256(payload).hexdigest() != record[label + "Sha256"]:
            raise ValueError("Retention predecessor digest differs")
        snapshots[label] = payload
    for payload in snapshots.values():
        payload.decode("utf-8")
        if b"\0" in payload:
            raise ValueError("Retention cannot mask binary content")
    lines = {label: payload.splitlines(keepends=True) for label, payload in snapshots.items()}
    approved_indexes = set()
    for mapping in record["lines"]:
        matched = []
        for label, contents in lines.items():
            index = mapping[label + "Line"] - 1
            if index >= len(contents):
                raise ValueError("Retention line is out of range")
            value = contents[index]
            if hashlib.sha256(value).hexdigest() != mapping["sha256"]:
                raise ValueError("Retained metadata line changed or was re-encoded")
            matched.append(value)
        if len(set(matched)) != 1 or not text_reasons(matched[0].decode("utf-8"), allowed):
            raise ValueError("Retention must identify unchanged existing private metadata")
        approved_indexes.add(mapping["successorLine"] - 1)
    return b"".join(
        b"\n" if index in approved_indexes else line for index, line in enumerate(lines["successor"])
    ).decode("utf-8")


def credential_report(raw: bytes, scanner: Path, scanner_sha: str, config: Path) -> list[dict]:
    if hashlib.sha256(scanner.read_bytes()).hexdigest() != scanner_sha:
        raise ValueError("Credential scanner identity changed")
    if (config.parent / "no-suppressions").exists():
        raise ValueError("Credential suppressions are not permitted")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITLEAKS_")}
    process = subprocess.run(
        [
            str(scanner),
            "stdin",
            "--no-banner",
            "--no-color",
            "--redact=100",
            "--ignore-gitleaks-allow",
            "--gitleaks-ignore-path",
            str(config.parent / "no-suppressions"),
            "--config",
            str(config),
            "--report-format",
            "json",
            "--report-path",
            "-",
            "--log-level",
            "error",
        ],
        input=raw,
        capture_output=True,
        env=env,
        check=False,
        timeout=120,
    )
    if process.returncode not in {0, 1}:
        raise ValueError("Credential scanner failed; review cannot waive errors")
    try:
        report = json.loads(process.stdout)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Credential scanner returned malformed output") from exc
    if not isinstance(report, list) or bool(report) != bool(process.returncode):
        raise ValueError("Credential scanner outcome is inconsistent")
    for finding in report:
        if (
            not isinstance(finding, dict)
            or not isinstance(finding.get("RuleID"), str)
            or not finding["RuleID"]
            or any(
                type(finding.get(k)) is not int or finding[k] < 1
                for k in ("StartLine", "EndLine", "StartColumn", "EndColumn")
            )
        ):
            raise ValueError("Credential scanner finding is malformed")
    return report


def secret_scan(
    raw: bytes, scanner: Path, scanner_sha: str, config: Path, approved_findings: list[str] | None = None
) -> None:
    report = credential_report(raw, scanner, scanner_sha, config)
    fingerprints = [
        hashlib.sha256(json.dumps(f, sort_keys=True, separators=(",", ":")).encode()).hexdigest() for f in report
    ]
    if sorted(fingerprints) != sorted(approved_findings or []):
        raise ValueError("Credential scan failed or requires review; raw values withheld")


def inspect(
    repo: Path,
    policy: dict,
    *,
    staged: bool,
    tips: list[str],
    scanner: Path,
    config: Path,
    reviews: dict | None = None,
    yaml_parser: Path | None = None,
) -> dict:
    baseline = policy["baselineCommit"]
    validate_history(repo, baseline)
    admissions = reviewed_artifacts(reviews, policy, config)
    preservation = reviews.get("preservation") if reviews else None
    documents = preservation_documents(preservation) if preservation is not None else {}
    if preservation is not None and (
        yaml_parser is None
        or yaml_parser.is_symlink()
        or hashlib.sha256(yaml_parser.read_bytes()).hexdigest() != preservation["parserSha256"]
    ):
        raise ValueError("Sealed metadata preservation parser is required")
    field_cache: dict[str, list[dict]] = {}
    baseline_entries = (
        entries(repo, baseline)
        if documents or any(item.get("retainedMetadata") for item in admissions.values())
        else {}
    )
    allowed = {value.casefold() for value in policy["allowedContentEmails"]}
    findings = []
    payloads: list[tuple[bytes, list[str]]] = []
    seen: set[tuple[str, str, str, tuple[str, ...]]] = set()
    count = 0

    def check_tree(
        current: dict[str, tuple[str, str]], prior: list[dict[str, tuple[str, str]]], parents: list[str]
    ) -> None:
        nonlocal count
        for path, (mode, oid) in changed_entries(current, prior).items():
            # The same successor blob on a different parent edge is new authority.
            identity = path, mode, oid, tuple(parents)
            if identity in seen:
                continue
            seen.add(identity)
            count += 1
            payloads.extend(((path.encode("utf-8"), []), (normalize(path).encode("utf-8"), [])))
            reasons = text_reasons(path, allowed)
            if path.casefold() in RAW_REPORTS:
                reasons.add("raw-machine-report")
            if mode not in {"100644", "100755"}:
                reasons.add("unsupported-file-mode")
            else:
                size = int(git(repo, "cat-file", "-s", oid))
                if size > 16 * 1024 * 1024:
                    reasons.add("oversized-file-needs-review")
                else:
                    raw = git(repo, "cat-file", "blob", oid)
                    admission = admissions.get((path, mode, hashlib.sha256(raw).hexdigest(), size), {})
                    non_emails = {value.casefold() for value in admission.get("nonEmailTokens", [])}
                    retained = admission
                    if path in documents and not any(
                        len(parents) == 1 and record["predecessorCommit"] == parents[0]
                        for record in admission.get("retainedMetadata", [])
                    ):
                        assert yaml_parser is not None and preservation is not None
                        retained = preservation_receipt(
                            repo,
                            raw,
                            path,
                            mode,
                            documents[path],
                            parents,
                            prior,
                            baseline_entries,
                            baseline,
                            yaml_parser,
                            preservation["parserSha256"],
                            preservation["workerSha256"],
                            allowed,
                            field_cache,
                        )
                    # Binary approval never suppresses readable private text or credential scanning.
                    inspected_text = retained_metadata_text(
                        repo, raw, path, mode, retained, parents, prior, baseline_entries, allowed
                    )
                    reasons.update(text_reasons(inspected_text, allowed | non_emails))
                    payloads.append((raw, admission.get("credentialFindingFingerprints", [])))
                    if b"\0" in raw or Path(path).suffix.lower() in BINARY:
                        if not admission.get("binaryReviewed"):
                            reasons.add("binary-needs-privacy-review")
                    else:
                        try:
                            raw.decode("utf-8")
                        except UnicodeDecodeError:
                            if not admission.get("binaryReviewed"):
                                reasons.add("non-text-needs-privacy-review")
                        else:
                            reasons.update(text_reasons(inspected_text, allowed | non_emails))
            if reasons:
                findings.append({"pathSha256": hashlib.sha256(path.encode()).hexdigest(), "reasons": sorted(reasons)})

    commits = []
    if staged:
        tree = entries(repo, None)
        prior = entries(repo, "HEAD")
        merge_path = Path(git(repo, "rev-parse", "--git-path", "MERGE_HEAD").decode().strip())
        if not merge_path.is_absolute():
            merge_path = repo / merge_path
        parents = [] if merge_path.exists() else [git(repo, "rev-parse", "HEAD").decode().strip()]
        check_tree(tree, [prior], parents)
        for role in ("AUTHOR", "COMMITTER"):
            identity = git(repo, "var", f"GIT_{role}_IDENT").decode()
            reasons = text_reasons(identity, set(), metadata=True)
            if reasons:
                findings.append({"field": role.lower(), "reasons": sorted(reasons)})
            payloads.append((identity.encode(), []))
    else:
        for tip in tips:
            if not SHA.fullmatch(tip):
                raise ValueError("Invalid push tip")
            git(repo, "rev-parse", "--verify", tip + "^{commit}")
        commits = (
            git(repo, "rev-list", "--reverse", "--topo-order", *tips, "--not", baseline, "--").decode().splitlines()
        )
        # Complete path inventory before any new commit/blob content is read.
        trees = {commit: entries(repo, commit) for commit in commits}
        for commit in commits:
            line = git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()
            check_tree(trees[commit], [entries(repo, parent) for parent in line[1:]], line[1:])
            raw = git(repo, "cat-file", "commit", commit)
            reasons = text_reasons(raw.decode("utf-8"), set(), metadata=True)
            if reasons:
                findings.append({"commit": commit, "reasons": sorted(reasons)})
            payloads.append((raw, []))
    if findings:
        return {"status": "FAIL", "commitsChecked": len(commits), "entriesChecked": count, "findings": findings}
    # Full new content plus metadata, not only added diff lines. No repository allowlists.
    for raw, approved_findings in payloads:
        secret_scan(raw, scanner, policy["scannerSha256"], config, approved_findings)
    return {"status": "PASS", "commitsChecked": len(commits), "entriesChecked": count, "findings": []}


def push_tips(data: str, destinations: list[str]) -> list[str]:
    tips = []
    for line in data.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError("Malformed push update")
        local_ref, local, remote_ref, remote = fields
        if text_reasons(local_ref, set(), metadata=True) or text_reasons(remote_ref, set(), metadata=True):
            raise ValueError("Branch name contains private metadata")
        if not SHA.fullmatch(local) or not SHA.fullmatch(remote) or local == "0" * 40:
            raise ValueError("Invalid push or deletion")
        if local_ref != remote_ref or remote_ref in RETIRED_REFS:
            raise ValueError("Renamed or retired branch publication is not permitted")
        if remote_ref not in destinations and not remote_ref.startswith("refs/heads/codex/"):
            raise ValueError("Push destination must be main or a same-name codex branch")
        tips.append(local)
    return sorted(set(tips))


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "yaml-fields":
        try:
            parser_path = Path(sys.argv[2])
            parser_raw = parser_path.read_bytes()
            if parser_path.is_symlink() or hashlib.sha256(parser_raw).hexdigest() != sys.argv[3]:
                raise ValueError("Parser pin differs")
            _load_sealed_yaml(parser_raw)
            request = json.loads(sys.stdin.buffer.read(32 * 1024 * 1024))
            print(json.dumps(_yaml_private_fields(request["text"].encode("utf-8"), set(request["allowed"]))))
            return 0
        except ValueError, OSError, KeyError, UnicodeError, RecursionError, ImportError, zipfile.BadZipFile:
            print("Structured metadata parsing denied; values withheld.")
            return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("staged", "push", "message"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--remote-url")
    parser.add_argument("--message", type=Path)
    parser.add_argument("--review-registry", type=Path)
    parser.add_argument("--yaml-parser", type=Path)
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        if args.mode == "message":
            if args.message is None:
                raise ValueError("Commit message is required")
            message = args.message.read_bytes()
            if text_reasons(message.decode("utf-8"), set(), metadata=True):
                raise ValueError("Commit message includes private metadata")
            secret_scan(message, args.scanner.resolve(), policy["scannerSha256"], args.config.resolve())
            print("Prospective privacy: commit message passed.")
            return 0
        tips = []
        if args.mode == "push":
            if args.remote_url != policy["remoteUrl"]:
                raise ValueError("Unexpected remote URL")
            updates = sys.stdin.read()
            tips = push_tips(updates, policy["remoteRefs"])
            # Ref names are new publication inputs even when the commit is old.
            for line in updates.splitlines():
                local_ref, _, remote_ref, _ = line.split()
                for ref in {local_ref, remote_ref}:
                    for raw in {ref.encode("utf-8"), normalize(ref).encode("utf-8")}:
                        secret_scan(raw, args.scanner.resolve(), policy["scannerSha256"], args.config.resolve())
            if not tips:
                print("Prospective privacy: no new push objects.")
                return 0
        result = inspect(
            args.repo.resolve(),
            policy,
            staged=args.mode == "staged",
            tips=tips,
            scanner=args.scanner.resolve(),
            config=args.config.resolve(),
            reviews=json.loads(args.review_registry.read_bytes()) if args.review_registry else None,
            yaml_parser=args.yaml_parser,
        )
        print(json.dumps(result))
        return int(result["status"] != "PASS")
    except ValueError, OSError, KeyError, UnicodeError, subprocess.SubprocessError:
        print("Prospective privacy: blocked; inputs or new content require review. No sensitive values printed.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
