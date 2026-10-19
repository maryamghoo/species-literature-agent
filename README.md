# Species Literature Agent

A simple local AI tool for finding, organizing, and updating scientific literature about any species.

I built this project because I wanted a faster way to do something I had done manually during my PhD: search through a large number of papers, decide which ones are actually relevant to a species, organize them by topic, and summarize the main findings.

The species is supplied from the command line, so the same code can be reused for different organisms without editing the Python file.

## What it does

The agent:

1. Searches OpenAlex using the common and scientific name of a species.
2. Removes duplicate records.
3. Uses a local LLM through Ollama to decide whether each study is genuinely relevant to the target species.
4. Handles possible problems with historical taxonomy, synonyms, subspecies, and older scientific names during the relevance check.
5. Assigns each accepted paper to one main biological category:
   - Genetics & Genomics
   - Disease & Health
   - Diet & Foraging
   - Behavior
   - Reproduction & Breeding
   - Demography & Survival
   - Habitat & Ecology
   - Conservation & Management
   - Movement & Dispersal
   - Physiology
   - Morphology
   - Climate & Environment
   - Other
6. Extracts the study location when it is clearly reported.
7. Creates a three-sentence summary of the main findings.
8. Saves the first author, year, source, paper link, category, study location, and summary.
9. Organizes accepted papers from newest to oldest within each category.
10. Saves progress after every paper, so a long run can be stopped and continued later.
11. Supports an update mode that searches OpenAlex again and analyzes only studies that were not processed before.

## How it works

```text
Species name
    ↓
OpenAlex search
    ↓
Remove duplicates
    ↓
Species relevance / taxonomy check
    ↓
Local LLM analysis with Ollama
    ↓
One biological category per study
    ↓
Location + 3-sentence summary
    ↓
Structured JSON + text reports
```

The current version uses:

- **Python** for the main workflow
- **OpenAlex API** for literature discovery and metadata
- **Ollama** for running the language model locally
- **Llama 3.2 3B** as the default local model
- **JSON files** for saving raw and processed data
- **TXT files** for the final human-readable reports

Because the language model runs locally through Ollama, there is no paid LLM API required.

## Requirements

You need:

- Python 3
- Ollama
- An Ollama model such as `llama3.2:3b`
- A free OpenAlex API key
- Python `requests` package

## Setup

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install the Python dependency:

```bash
python -m pip install requests
```

Install the Ollama model:

```bash
ollama pull llama3.2:3b
```

Set your OpenAlex API key:

```bash
export OPENALEX_API_KEY="YOUR_OPENALEX_API_KEY"
```

Make sure Ollama is running before starting the agent.

## Running the agent

Example for Florida Scrub-Jay:

```bash
.venv/bin/python species_literature_agent.py \
  --species "Florida Scrub-Jay" \
  --scientific-name "Aphelocoma coerulescens" \
  --max-results 10000
```

Example for another species:

```bash
.venv/bin/python species_literature_agent.py \
  --species "Monarch Butterfly" \
  --scientific-name "Danaus plexippus" \
  --max-results 10000
```

You do not need to edit the Python code when changing species.

`--max-results` is the maximum number of search results to collect for processing. If OpenAlex has fewer matching records, the search stops automatically.

## Stopping and continuing later

The program saves each completed study.

If the program stops, crashes, or you close the terminal, run the same command again **without `--fresh`**.

The agent will:

- load the saved search results,
- load the studies already processed,
- skip completed studies,
- continue only with unfinished studies.

This makes long runs much safer.

## Checking for new or previously missed studies

When you come back later and want to search OpenAlex again, use `--update`:

```bash
.venv/bin/python species_literature_agent.py \
  --species "Florida Scrub-Jay" \
  --scientific-name "Aphelocoma coerulescens" \
  --max-results 10000 \
  --update
```

Update mode does **not** start over.

It searches OpenAlex again, combines the new search with the saved search, compares the records with studies already processed, and sends only unseen studies to Ollama.

For example:

```text
Previously processed: 4805
New studies to process: 3
```

Only those 3 studies will be analyzed.

A newly discovered study does not have to be newly published. An older paper may appear if it was missed before or was added/indexed in OpenAlex later.

The agent identifies previously processed records primarily using the OpenAlex ID, then DOI when needed, with the normalized title as a fallback.

## Starting over for one species

Use `--fresh` only when you intentionally want to erase the saved results for the species you are currently running and start that species from the beginning:

```bash
.venv/bin/python species_literature_agent.py \
  --species "Florida Scrub-Jay" \
  --scientific-name "Aphelocoma coerulescens" \
  --max-results 10000 \
  --fresh
```

`--fresh` now removes only the cached files for the selected species. It does **not** delete results belonging to other species.

Do not use `--fresh` when you only want to check for newly discovered papers. Use `--update` instead.

## Output files

The main files are saved under:

```text
species_literature/
├── raw/
├── processed/
└── outputs/
```

For a species such as Florida Scrub-Jay, the files include:

```text
species_literature/raw/florida_scrub_jay_raw.json
species_literature/processed/florida_scrub_jay_processed.json
species_literature/outputs/florida_scrub_jay_literature.txt
species_literature/outputs/florida_scrub_jay_rejected.txt
```

The accepted report contains papers grouped by biological category and ordered from newest to oldest within each category.

The rejected report keeps studies that were reviewed but judged not relevant to the target species, together with the reason for rejection.

## Reusing it for another species

The same program can be used for another species by changing only the command-line arguments.

Example:

```bash
.venv/bin/python species_literature_agent.py \
  --species "African Elephant" \
  --scientific-name "Loxodonta africana" \
  --max-results 10000
```

Each species gets its own raw, processed, accepted, and rejected files.

The relevance prompt is generic and uses the species name supplied by the user. It is not hard-coded for Florida Scrub-Jays.

## Current limitations

This project is meant to assist literature review, not replace careful scientific review.

Important limitations:

- OpenAlex does not contain every paper, dissertation, book, government report, or other scientific document.
- Search results can include papers that mention the species but are not actually about it; the LLM relevance step is used to filter these.
- Historical taxonomy can still be difficult, especially when old scientific names were used for multiple populations or taxa.
- The current summaries are mainly based on metadata and abstracts available through OpenAlex, not necessarily the full paper.
- A local LLM can make mistakes, so important scientific results should still be checked manually.
- Processing thousands of records with a local model can take a long time.
- A study newly found during `--update` may be an older publication rather than a newly published paper.

## Why I built it

During my PhD, I manually searched and organized large amounts of species-specific biological literature. This project explores how a local AI workflow can automate much of that repetitive work while keeping the process transparent, resumable, and reusable.

The goal is not simply to generate summaries. The goal is to build a structured species literature database that can help researchers quickly understand what has been studied, where studies were conducted, and which biological topics each paper addresses.

## Future improvements

Possible next steps include:

- Retrieve legally available full-text open-access papers
- Add literature sources beyond OpenAlex
- Export results to CSV
- Add a simple web interface
- Improve taxonomic validation
- Add stronger scientific quality checks
- Support manual review and correction of AI-generated results
- Add scheduled automatic update checks
- Add tests and a cleaner installation package

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.