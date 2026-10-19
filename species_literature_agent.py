import re
import json
import time
import argparse
import hashlib
from pathlib import Path

import requests
import os

OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY")

# ============================================================
# SETTINGS
# ============================================================

CATEGORIES = [
    "Genetics & Genomics",
    "Disease & Health",
    "Diet & Foraging",
    "Behavior",
    "Reproduction & Breeding",
    "Demography & Survival",
    "Habitat & Ecology",
    "Conservation & Management",
    "Movement & Dispersal",
    "Physiology",
    "Morphology",
    "Climate & Environment",
    "Other",
]

OPENALEX_URL = "https://api.openalex.org/works"
OLLAMA_URL = "http://localhost:11434/api/generate"


# ============================================================
# BASIC HELPERS
# ============================================================

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def stable_id(title):
    return hashlib.md5(
        normalize_title(title).encode("utf-8")
    ).hexdigest()


def save_json(data, path):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def load_json(path, default):

    if not path.exists():
        return default

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)

def work_key(work):
    """
    Unique ID used to determine whether a paper
    was already processed.
    """

    if work.get("openalex_id"):
        return work["openalex_id"]

    if work.get("doi"):
        return work["doi"].lower()

    return stable_id(
        work.get("title", "")
    )

# ============================================================
# REBUILD ABSTRACT FROM OPENALEX
# ============================================================

def rebuild_abstract(inverted_index):

    if not inverted_index:
        return ""

    words = []

    for word, positions in inverted_index.items():

        for position in positions:
            words.append(
                (position, word)
            )

    words.sort()

    return " ".join(
        word
        for _, word in words
    )


# ============================================================
# SEARCH OPENALEX
# ============================================================

def search_openalex(
    search_term,
    max_results=100
):

    results = []
    cursor = "*"

    while len(results) < max_results:

        print(
            f"Searching literature for "
            f"'{search_term}': "
            f"{len(results)} collected..."
        )

        remaining = (
            max_results
            - len(results)
        )

        params = {
            "search": search_term,
            "per-page": min(100, remaining),
            "cursor": cursor,
            "api_key": OPENALEX_API_KEY,
        }

        response = requests.get(
            OPENALEX_URL,
            params=params,
            timeout=60,
        )

        response.raise_for_status()

        data = response.json()

        works = data.get(
            "results",
            []
        )

        if not works:
            break

        for work in works:

            title = (
                work.get("title") or ""
            ).strip()

            if not title:
                continue

            abstract = rebuild_abstract(
                work.get(
                    "abstract_inverted_index"
                )
            )

            # ------------------------------
            # AUTHORS
            # ------------------------------

            authors = []

            for authorship in work.get(
                "authorships",
                []
            ):

                author_name = (
                    authorship
                    .get("author", {})
                    .get("display_name")
                )

                if author_name:
                    authors.append(
                        author_name
                    )

            doi = (
                work.get("doi")
                or ""
            )

            primary_location = (
                work.get(
                    "primary_location"
                )
                or {}
            )

            link = (
                primary_location.get(
                    "landing_page_url"
                )
                or doi
                or work.get(
                    "id",
                    ""
                )
            )

            source = (
                primary_location.get(
                    "source"
                )
                or {}
            )

            result = {
                "openalex_id": work.get(
                    "id",
                    ""
                ),
                "title": title,
                "year": work.get(
                    "publication_year"
                ),
                "type": work.get(
                    "type",
                    "unknown"
                ),
                "authors": authors,
                "doi": doi,
                "link": link,
                "abstract": abstract,
                "journal_or_source":
                    source.get(
                        "display_name",
                        ""
                    ),
                "cited_by": work.get(
                    "cited_by_count",
                    0
                ),
            }

            results.append(
                result
            )

            if (
                len(results)
                >= max_results
            ):
                break

        cursor = (
            data
            .get("meta", {})
            .get("next_cursor")
        )

        if not cursor:
            break

        time.sleep(0.25)

    return results


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def deduplicate(results):

    unique = {}

    for work in results:

        key = normalize_title(
            work.get(
                "title",
                ""
            )
        )

        if not key:
            continue

        if key not in unique:

            unique[key] = work

        else:

            old_abstract = (
                unique[key]
                .get(
                    "abstract",
                    ""
                )
            )

            new_abstract = (
                work.get(
                    "abstract",
                    ""
                )
            )

            if (
                len(new_abstract)
                > len(old_abstract)
            ):

                unique[key] = work

    return list(
        unique.values()
    )


# ============================================================
# UPDATE OLD CACHED DATA
# ============================================================

def backfill_metadata(
    processed,
    search_results
):

    """
    If old cached processed files are missing
    authors/year/link/etc., copy them from
    the current OpenAlex search results.
    """

    lookup = {
        stable_id(
            paper.get(
                "title",
                ""
            )
        ): paper

        for paper
        in search_results
    }

    fields = [
        "authors",
        "year",
        "type",
        "link",
        "doi",
        "journal_or_source",
        "abstract",
        "cited_by",
        "openalex_id",
    ]

    for paper in processed:

        key = stable_id(
            paper.get(
                "title",
                ""
            )
        )

        source = lookup.get(key)

        if not source:
            continue

        for field in fields:

            current_value = (
                paper.get(field)
            )

            new_value = (
                source.get(field)
            )

            if (
                not current_value
                and new_value
            ):
                paper[field] = (
                    new_value
                )

    return processed


# ============================================================
# CHECK OLLAMA
# ============================================================

def check_ollama():

    try:

        response = requests.get(
            "http://localhost:11434/api/tags",
            timeout=10,
        )

        response.raise_for_status()

    except Exception:

        print(
            "\nERROR: Ollama is not running."
        )

        print(
            "Open Ollama and try again.\n"
        )

        raise SystemExit


# ============================================================
# ANALYZE ONE STUDY WITH OLLAMA
# ============================================================

def analyze_with_ollama(
    work,
    species,
    scientific_name,
    model,
):

    category_list = "\n".join(
        f"- {category}"
        for category
        in CATEGORIES
    )

    species_text = species

    if scientific_name:

        species_text += (
            f" ({scientific_name})"
        )

    prompt = f"""
You are a careful biological literature reviewer.

TARGET SPECIES:

{species_text}

IMPORTANT:

We want ONLY studies genuinely about:

{species_text}

The target species must be an important subject of the study,
not merely mentioned in passing.

Be careful with historical taxonomy, synonyms, subspecies,
and older scientific names. Do not assume a study is relevant
only because the scientific name appears.

If the paper appears to study a different species, subspecies,
historical taxon, or population that is not the target species,
return:

"relevant": false

STUDY TITLE:

{work.get("title", "")}


YEAR:

{work.get("year", "")}


SOURCE:

{work.get("journal_or_source", "")}


ABSTRACT:

{work.get("abstract", "")}


TASK 1 — RELEVANCE

Decide whether this study is genuinely
about the target species:

{species_text}

The target species must be an important
subject of the research, not merely
mentioned in passing.

Consider historical taxonomy, synonyms,
subspecies, taxonomic revisions, and older
scientific names carefully.

If the study focuses on a different species,
subspecies, historical taxon, or population
that is not the target species, return:

"relevant": false


TASK 2 — CATEGORY

If relevant, assign EXACTLY ONE category.

Allowed categories:

{category_list}

Choose the category representing the
PRIMARY research question and main
biological finding.

Never assign more than one category.


TASK 3 — SUMMARY

Write EXACTLY THREE sentences.

Summarize the most important findings.

Use only information supported by the
title and abstract.

Do NOT invent findings.

If there is not enough information,
say so clearly.


TASK 4 — STUDY LOCATION

Identify where individuals of the target species were:

- sampled
- observed
- captured
- monitored
- bred
- studied

Do NOT report the authors' university.

Do NOT guess.

If the location is not clearly stated,
return exactly:

"Not clearly reported"


TASK 5 — RELEVANCE REASON

Write one short explanation describing
why the study was accepted or rejected.


Return ONLY valid JSON:

{{
    "relevant": true,
    "category": "Behavior",
    "location": "Not clearly reported",
    "summary": "Sentence one. Sentence two. Sentence three.",
    "relevance_reason": "The study directly examines the target species."
}}
"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,

        # 10 minutes
        timeout=600,
    )

    response.raise_for_status()

    response_data = (
        response.json()
    )

    raw = (
        response_data
        .get(
            "response",
            ""
        )
        .strip()
    )

    try:

        result = json.loads(
            raw
        )

    except json.JSONDecodeError:

        print(
            "WARNING: Ollama returned "
            "invalid JSON."
        )

        return {
            "relevant": False,
            "category": "Other",
            "location":
                "Not clearly reported",
            "summary": "",
            "relevance_reason":
                "Invalid model output.",
        }

    # ------------------------------
    # VALIDATE MODEL OUTPUT
    # ------------------------------

    if (
        result.get("category")
        not in CATEGORIES
    ):
        result["category"] = (
            "Other"
        )

    if not isinstance(
        result.get("relevant"),
        bool
    ):
        result["relevant"] = (
            False
        )

    if not result.get(
        "location"
    ):
        result["location"] = (
            "Not clearly reported"
        )

    if not result.get(
        "summary"
    ):
        result["summary"] = (
            "Insufficient information "
            "was available to summarize "
            "this study."
        )

    if not result.get(
        "relevance_reason"
    ):
        result[
            "relevance_reason"
        ] = (
            "No relevance reason "
            "was provided."
        )

    return result


# ============================================================
# WRITE ACCEPTED STUDIES
# ============================================================

def write_report(
    papers,
    output_file,
    species,
    scientific_name,
):

    grouped = {
        category: []
        for category
        in CATEGORIES
    }

    for paper in papers:

        analysis = paper.get(
            "analysis",
            {}
        )

        if not analysis.get(
            "relevant"
        ):
            continue

        category = (
            analysis.get(
                "category",
                "Other"
            )
        )

        if category not in grouped:
            category = "Other"

        grouped[
            category
        ].append(
            paper
        )

    total_relevant = sum(
        len(items)
        for items
        in grouped.values()
    )

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "SPECIES LITERATURE DATABASE\n"
        )

        f.write(
            "=" * 75
            + "\n\n"
        )

        f.write(
            f"Species: {species}\n"
        )

        if scientific_name:

            f.write(
                f"Scientific name: "
                f"{scientific_name}\n"
            )

        f.write(
            f"Relevant studies: "
            f"{total_relevant}\n\n"
        )

        # --------------------------------
        # CATEGORY BY CATEGORY
        # --------------------------------

        for category in CATEGORIES:

            category_papers = (
                grouped[
                    category
                ]
            )

            if not category_papers:
                continue

            # NEWEST --> OLDEST
            category_papers.sort(
                key=lambda x:
                    x.get(
                        "year"
                    ) or 0,
                reverse=True,
            )

            f.write(
                "\n"
                + "=" * 75
                + "\n"
            )

            f.write(
                category.upper()
                + "\n"
            )

            f.write(
                "=" * 75
                + "\n\n"
            )

            for number, paper in enumerate(
                category_papers,
                start=1,
            ):

                analysis = (
                    paper[
                        "analysis"
                    ]
                )

                authors = (
                    paper.get(
                        "authors",
                        []
                    )
                    or []
                )

                if authors:

                    first_author = (
                        authors[0]
                    )

                else:

                    first_author = (
                        "Unknown"
                    )

                f.write(
                    f"{number}. "
                    f"{paper.get('title', '')}\n"
                )

                f.write(
                    f"Year: "
                    f"{paper.get('year') or 'Unknown'}\n"
                )

                f.write(
                    f"First author: "
                    f"{first_author}\n"
                )

                f.write(
                    f"Type: "
                    f"{paper.get('type') or 'Unknown'}\n"
                )

                f.write(
                    f"Source: "
                    f"{paper.get('journal_or_source') or 'Unknown'}\n"
                )

                f.write(
                    f"Link: "
                    f"{paper.get('link', '')}\n"
                )

                f.write(
                    f"Study location: "
                    f"{analysis.get('location', 'Not clearly reported')}\n"
                )

                f.write(
                    "Summary:\n"
                )

                f.write(
                    analysis.get(
                        "summary",
                        ""
                    )
                )

                f.write(
                    "\n\n"
                    + "-" * 75
                    + "\n\n"
                )


# ============================================================
# WRITE REJECTED STUDIES
# ============================================================

def write_rejected_report(
    papers,
    rejected_file,
):

    rejected = []

    for paper in papers:

        analysis = paper.get(
            "analysis",
            {}
        )

        if not analysis.get(
            "relevant",
            False
        ):

            rejected.append(
                paper
            )

    # newest first
    rejected.sort(
        key=lambda x:
            x.get("year") or 0,
        reverse=True,
    )

    with open(
        rejected_file,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            "REJECTED / NON-RELEVANT STUDIES\n"
        )

        f.write(
            "=" * 75
            + "\n\n"
        )

        for number, paper in enumerate(
            rejected,
            start=1,
        ):

            analysis = (
                paper.get(
                    "analysis",
                    {}
                )
            )

            authors = (
                paper.get(
                    "authors",
                    []
                )
                or []
            )

            first_author = (
                authors[0]
                if authors
                else "Unknown"
            )

            f.write(
                f"{number}. "
                f"{paper.get('title', '')}\n"
            )

            f.write(
                f"Year: "
                f"{paper.get('year') or 'Unknown'}\n"
            )

            f.write(
                f"First author: "
                f"{first_author}\n"
            )

            f.write(
                f"Reason: "
                f"{analysis.get('relevance_reason', '')}\n"
            )

            f.write(
                f"Link: "
                f"{paper.get('link', '')}\n"
            )

            f.write(
                "\n"
                + "-" * 75
                + "\n\n"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--species",
        required=True,
    )

    parser.add_argument(
        "--scientific-name",
        default=None,
    )

    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help=(
            "Maximum TOTAL number "
            "of unique studies to analyze."
        ),
    )

    parser.add_argument(
        "--model",
        default="llama3.2:3b",
    )

    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "Delete previous results "
            "and start from zero."
        ),
    )

    parser.add_argument(
    "--update",
    action="store_true",
    help=(
        "Search OpenAlex again and process "
        "only newly discovered studies."
    ),
)

    args = parser.parse_args()

    if args.fresh and args.update:
        parser.error(
            "Use either --fresh or --update, not both."
        )

    species = (
        args.species
    )

    scientific_name = (
        args.scientific_name
    )

    slug = slugify(
        species
    )

    base = Path(
        "species_literature"
    )

    raw_folder = (
        base / "raw"
    )

    processed_folder = (
        base / "processed"
    )

    output_folder = (
        base / "outputs"
    )

    raw_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    processed_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_file = (
        raw_folder
        / f"{slug}_raw.json"
    )

    processed_file = (
        processed_folder
        / f"{slug}_processed.json"
    )

    output_file = (
        output_folder
        / f"{slug}_literature.txt"
    )

    rejected_file = (
        output_folder
        / f"{slug}_rejected.txt"
    )

    # ========================================================
    # FRESH START
    # Delete ONLY files for the requested species.
    # Do not delete results for other species.
    # ========================================================

    if args.fresh:

        print(
            f"Deleting old cached results for {species}..."
        )

        for path in [
            raw_file,
            processed_file,
            output_file,
            rejected_file,
        ]:
            if path.exists():
                path.unlink()

    # ========================================================
    # CHECK OLLAMA
    # ========================================================

    check_ollama()

    # ========================================================
    # SEARCH
    # ========================================================

    saved_results = load_json(
        raw_file,
        [],
    )

    # Normal mode:
    # use the old saved search
    if raw_file.exists() and not args.update:

        print(
            "Loading saved search results..."
        )

        results = saved_results


    # Update mode OR first-ever run:
    # search OpenAlex again
    else:

        if args.update:
            print(
                "\nUPDATE MODE:"
                "\nSearching OpenAlex for new studies..."
            )

        all_results = []

        print(
            f"\nSearching common name: "
            f"{species}"
        )

        all_results.extend(
            search_openalex(
                species,
                args.max_results,
            )
        )

        if scientific_name:

            print(
                f"\nSearching scientific name: "
                f"{scientific_name}"
            )

            all_results.extend(
                search_openalex(
                    scientific_name,
                    args.max_results,
                )
            )

        new_search_results = deduplicate(
            all_results
        )

        new_search_results.sort(
            key=lambda x:
                x.get("cited_by", 0),
            reverse=True,
        )

        # Limit only the NEW search,
        # not your previously saved papers
        new_search_results = (
            new_search_results[
                :args.max_results
            ]
        )

        if args.update:

            # Keep old papers + add newly found papers
            results = deduplicate(
                saved_results
                + new_search_results
            )

        else:

            results = new_search_results

        save_json(
            results,
            raw_file,
        )

    # ========================================================
    # LOAD EXISTING PROGRESS
    # ========================================================

    processed = load_json(
        processed_file,
        [],
    )

    # Make sure old cached papers
    # get current author metadata
    processed = backfill_metadata(
        processed,
        results,
    )

    save_json(
        processed,
        processed_file,
    )

    completed = {
    work_key(paper)
    for paper in processed
    }

    new_candidates = [
        work
        for work in results
        if work_key(work)
        not in completed
    ]

    print(
        f"\nPreviously processed: "
        f"{len(processed)}"
    )

    print(
        f"New studies to process: "
        f"{len(new_candidates)}"
    )

    # ========================================================
    # PROCESS STUDIES
    # ========================================================

    for index, work in enumerate(
        new_candidates,
        start=1,
    ):

        work_id = work_key(
            work
        )

        print(
            f"\n[{index}/{len(new_candidates)}]"
        )

        print(
            work.get(
                "title",
                ""
            )
        )

        # --------------------------------
        # ANALYZE RELEVANCE AND CONTENT
        # --------------------------------

        try:

            work["analysis"] = (
                analyze_with_ollama(
                    work,
                    species,
                    scientific_name,
                    args.model,
                )
            )

        except Exception as error:

            print(
                f"ERROR: {error}"
            )

            print(
                "This study was not "
                "marked complete. "
                "Running the script again "
                "will retry it."
            )

            continue

        # --------------------------------
        # SAVE COMPLETED STUDY
        # --------------------------------

        processed.append(
            work
        )

        completed.add(
            work_id
        )

        save_json(
            processed,
            processed_file,
        )

        # Update reports after
        # every completed study
        write_report(
            processed,
            output_file,
            species,
            scientific_name,
        )

        write_rejected_report(
            processed,
            rejected_file,
        )

    # ========================================================
    # IMPORTANT:
    # ALWAYS REWRITE FINAL REPORTS
    # even when every paper was already processed
    # ========================================================

    processed = backfill_metadata(
        processed,
        results,
    )

    save_json(
        processed,
        processed_file,
    )

    write_report(
        processed,
        output_file,
        species,
        scientific_name,
    )

    write_rejected_report(
        processed,
        rejected_file,
    )

    # ========================================================
    # FINISHED
    # ========================================================

    print(
        "\nDONE!"
    )

    print(
        "\nAccepted studies:"
    )

    print(
        output_file
    )

    print(
        "\nRejected studies:"
    )

    print(
        rejected_file
    )


if __name__ == "__main__":
    main()