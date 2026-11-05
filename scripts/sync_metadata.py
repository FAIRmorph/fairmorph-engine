#!/usr/bin/env python3
"""Synchronisiert Projektmetadaten aus pyproject.toml in citation.cff,

codemeta.json und src/fairmorph_engine/__init__.py.
Standardbibliothek only (Python 3.11+).
"""

import json
import re
import sys
import tomllib
from datetime import date
from pathlib import Path


def bump_semver(current: str, part: str) -> str:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", current)
    if not match:
        raise ValueError(f"Ungültiges SemVer-Format: {current}")
    major, minor, patch = map(int, match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return part  # Explizite Versionsnummer übergeben


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject_path = root / "pyproject.toml"

    if not pyproject_path.exists():
        sys.exit("❌ pyproject.toml wurde nicht gefunden.")

    pyproject_raw = pyproject_path.read_text(encoding="utf-8")
    data = tomllib.loads(pyproject_raw)
    project = data.get("project", {})

    current_version = project.get("version", "0.1.0")

    # Optionales Version-Bumping per CLI-Argument (analog zu pnpm version)
    if len(sys.argv) > 1:
        target = sys.argv[1].lower()
        new_version = bump_semver(current_version, target)
        if new_version != current_version:
            pyproject_raw = re.sub(
                r'^(version\s*=\s*")[^"]+(")',
                rf"\g<1>{new_version}\g<2>",
                pyproject_raw,
                flags=re.MULTILINE,
            )
            pyproject_path.write_text(pyproject_raw, encoding="utf-8")
            data = tomllib.loads(pyproject_raw)
            project = data.get("project", {})
            print(f"📦 Version erhöht: {current_version} -> {new_version}")

    # Metadaten auslesen
    name = project.get("name", "fairmorph-engine")
    version = project.get("version", "0.1.0")
    description = project.get("description", "")
    keywords = project.get("keywords", [])

    license_field = project.get("license", "MIT")
    license_str = (
        license_field.get("text", "MIT") if isinstance(license_field, dict) else str(license_field)
    )

    authors = project.get("authors", [])
    author_name = "FAIRmorph Team"
    author_email = ""
    if authors and isinstance(authors, list):
        author_name = authors[0].get("name", author_name)
        author_email = authors[0].get("email", "")

    urls = {k.lower(): v for k, v in project.get("urls", {}).items()}
    homepage = urls.get("homepage", "")
    documentation = urls.get("documentation", urls.get("docs", ""))
    repository = urls.get("repository", urls.get("source", ""))
    issues = urls.get("issues", urls.get("bugs", ""))

    today_iso = date.today().isoformat()

    print(f"🔄 Synchronisiere Metadaten für {name} v{version}...")

    # 1. src/fairmorph_engine/__init__.py (__version__)
    init_path = root / "src" / "fairmorph_engine" / "__init__.py"
    if init_path.exists():
        init_content = init_path.read_text(encoding="utf-8")
        if re.search(r"^__version__\s*=", init_content, flags=re.MULTILINE):
            init_content = re.sub(
                r'^__version__\s*=\s*["\'][^"\']+["\']',
                f'__version__ = "{version}"',
                init_content,
                flags=re.MULTILINE,
            )
        else:
            init_content = f'__version__ = "{version}"\n' + init_content
        init_path.write_text(init_content, encoding="utf-8")
        print("  ✓ src/fairmorph_engine/__init__.py")

    # 2. citation.cff
    cff_path = root / "CITATION.cff"
    if cff_path.exists():
        cff = cff_path.read_text(encoding="utf-8")
        cff = re.sub(r"^title:\s*.+$", f'title: "{name}"', cff, flags=re.MULTILINE)
        cff = re.sub(r"^version:\s*.+$", f"version: {version}", cff, flags=re.MULTILINE)
        cff = re.sub(
            r"^abstract:\s*.+$",
            f'abstract: "{description}"',
            cff,
            flags=re.MULTILINE,
        )
        cff = re.sub(r"^license:\s*.+$", f"license: {license_str}", cff, flags=re.MULTILINE)
        cff = re.sub(
            r"^date-released:\s*.+$",
            f'date-released: "{today_iso}"',
            cff,
            flags=re.MULTILINE,
        )

        if homepage:
            cff = re.sub(r"^url:\s*.+$", f'url: "{homepage}"', cff, flags=re.MULTILINE)
        if repository:
            cff = re.sub(
                r"^repository-code:\s*.+$",
                f'repository-code: "{repository}"',
                cff,
                flags=re.MULTILINE,
            )

        # YAML Authors-Block
        author_lines = ["authors:", f'  - name: "{author_name}"']
        if author_email:
            author_lines.append(f'    email: "{author_email}"')
        if homepage:
            author_lines.append(f'    website: "{homepage}"')
        authors_yaml = "\n".join(author_lines)

        if re.search(r"^authors:", cff, flags=re.MULTILINE):
            cff = re.sub(
                r"^authors:(?:\r?\n(?![a-zA-Z0-9_#-]+:).*)*\r?\n?",
                f"{authors_yaml}\n",
                cff,
                flags=re.MULTILINE,
            )
        else:
            cff += f"\n{authors_yaml}\n"

        cff_path.write_text(cff, encoding="utf-8")
        print("  ✓ citation.cff")

    # 3. codemeta.json
    codemeta_path = root / "codemeta.json"
    if codemeta_path.exists():
        codemeta = json.loads(codemeta_path.read_text(encoding="utf-8"))
        codemeta["name"] = name
        codemeta["version"] = version
        codemeta["description"] = description
        codemeta["license"] = f"https://spdx.org/licenses/{license_str}"
        codemeta["dateModified"] = today_iso

        if homepage:
            codemeta["url"] = homepage
        if repository:
            codemeta["codeRepository"] = repository
        if documentation:
            codemeta["documentation"] = documentation
        if issues:
            codemeta["issueTracker"] = issues
        if keywords:
            codemeta["keywords"] = keywords

        if isinstance(codemeta.get("author"), list) and len(codemeta["author"]) > 0:
            codemeta["author"][0]["name"] = author_name
            if author_email:
                codemeta["author"][0]["email"] = author_email
            if homepage:
                codemeta["author"][0]["url"] = homepage

        codemeta_path.write_text(
            json.dumps(codemeta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("  ✓ codemeta.json")

    print("✨ Engine-Metadaten erfolgreich synchronisiert.")


if __name__ == "__main__":
    main()
