import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from string import Template

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class SpecTemplate(Template):
    delimiter = "@"


def get_pyproject_metadata() -> dict:
    pyproject_path = Path("pyproject.toml")
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})

    version = project["version"]
    lic = project["license"]
    url = project["urls"]["Home"]

    first_author = project["authors"][0]
    author_str = f"{first_author['name']} <{first_author['email']}>"

    return {
        "version": version,
        "license": lic,
        "url": url,
        "author": author_str,
    }


def get_git_info() -> tuple[str, str]:
    git_hash = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()

    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    return git_hash, branch


def parse_changelog(changelog_path: Path, meta: dict) -> str:
    content = changelog_path.read_text(encoding="utf-8")

    # match '## version - YYYY-MM-DD'
    version_header_re = re.compile(
        r"^##\s+v?([0-9]+\.[0-9]+\.[0-9]+[^\]\s]*)\s*-\s*(\d{4}-\d{2}-\d{2})",
        re.MULTILINE,
    )
    matches = list(version_header_re.finditer(content))

    rpm_changelog_blocks = []

    for i, match in enumerate(matches):
        version = match.group(1)
        iso_date_str = match.group(2)

        parsed_date = datetime.strptime(iso_date_str, "%Y-%m-%d")
        rpm_date_str = parsed_date.strftime("%a %b %d %Y")

        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_text = content[start_pos:end_pos]

        entries = []
        for line in section_text.splitlines():
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                item = line[2:].strip()
                if item:
                    entries.append(f"- {item}")

        if not entries:
            continue

        header = f"* {rpm_date_str} {meta['author']} - {version}-1"
        body = "\n".join(entries)
        rpm_changelog_blocks.append(f"{header}\n{body}")

    return "\n\n".join(rpm_changelog_blocks)


def generate_spec(template_path: Path, changelog_path: Path, output_path: Path) -> None:
    meta = get_pyproject_metadata()
    git_hash, branch = get_git_info()
    timestamp = datetime.now().strftime("%Y%m%d")

    if branch == "main" or branch.startswith("v"):
        rpm_release = "1"
    else:
        rpm_release = f"1^{timestamp}git{git_hash}"

    changelog = parse_changelog(changelog_path, meta)

    template_content = template_path.read_text(encoding="utf-8")
    template = SpecTemplate(template_content)
    rendered_spec = template.substitute(
        VERSION=meta["version"],
        RELEASE=rpm_release,
        LICENSE=meta["license"],
        URL=meta["url"],
        CHANGELOG=changelog,
    )

    output_path.write_text(rendered_spec, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render RPM spec template with version info."
    )
    parser.add_argument(
        "-t",
        "--template",
        type=Path,
        default=Path("rpmbuild/python-arcticsecurity.spec.in"),
        help="Path to template file",
    )
    parser.add_argument(
        "-c",
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Path to changelog",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("rpmbuild/python-arcticsecurity.spec"),
        help="Output spec file path",
    )
    args = parser.parse_args()

    generate_spec(args.template, args.changelog, args.output)


if __name__ == "__main__":
    main()
