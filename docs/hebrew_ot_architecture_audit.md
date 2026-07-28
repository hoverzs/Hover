# Hebrew OT Prototype Architecture Audit

## Source Audit

Official source repository: `STEPBible/STEPBible-Data`.

Current Hebrew tagged text name in the repository is `TAHOT`, not `THOT`:

- `Translators Amalgamated OT+NT/TAHOT Gen-Deu - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt`
- `Translators Amalgamated OT+NT/TAHOT Jos-Est - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt`
- `Translators Amalgamated OT+NT/TAHOT Job-Sng - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt`
- `Translators Amalgamated OT+NT/TAHOT Isa-Mal - Translators Amalgamated Hebrew OT - STEPBible.org CC BY.txt`

Related files:

- `Lexicons/TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt`
- `Morphology codes/TEHMC - Translators Expansion of Hebrew Morphology Codes - STEPBible.org CC BY.txt`

The TAHOT record identifier uses `Book.chapter.verse#word=sourceEdition`, for example `Rut.1.1#01=L` and `Rut.3.14#02=Q(K)`.

TAHOT fields used in the prototype:

- reference and source edition
- Hebrew surface text
- transliteration
- English gloss
- disambiguated Strong tags
- morphology code
- meaning variant
- spelling variant
- simple Strong instance
- alternate Strong
- expanded Strong tags

## Licensing

The STEPBible-Data repository states the data is CC BY 4.0. Required attribution should credit `STEP Bible` and link to `www.STEPBible.org`.

The TAHOT Hebrew text is described as derived from WLC via OpenScriptures and corrected by Tyndale/STEPBible. The TBESH brief lexicon notes that its meanings are based on Abridged BDB by Online Bible and are provided for guidance; production use should preserve attribution and avoid presenting the brief lexicon as an internally authored Hungarian lexicon.

## Greek Reuse Audit

Reusable:

- project-root path helpers in `bible_engine.paths`
- SQLite repository pattern
- fixture-first parser tests
- passage loader shape returning grouped verse tokens
- source attribution pattern
- lexicon fallback concept

Greek-specific:

- TAGNT parser fields and Greek text rendering rules
- Greek morphology decoder
- Greek Strong alias handling
- Greek lexicon schema and Hungarian production lexicon
- `components/greek_token_selector` layout assumptions, especially LTR token flow

Do not generalize by renaming Greek classes in place. Add Hebrew-specific parser/repository modules first, then introduce shared interfaces only after both languages have stable requirements.

## Hebrew-Specific Requirements

TAHOT uses `/` to separate Hebrew word components and `\` for punctuation. The parser must preserve:

- prefix components
- core component
- suffix components
- maqaf and punctuation
- ketiv/qere variants
- source edition flags
- multiple Strong IDs per surface token
- Hebrew vs Aramaic language marking
- normalized surface and accent-stripped surface

The first prototype keeps a whole surface token selectable by stable key `book:chapter:verse:word_index`; component-level selection should be a later UI phase.

## Production Prototype Database

Production prototype output path: `data/generated/tahot_ot.sqlite3`.

Tables:

- `metadata`
- `books`
- `tokens`
- `token_components`
- `token_strong_ids`
- `ketiv_qere`
- `lexicon_entries`
- `strong_aliases`

The separate TBESH lexicon database is `data/generated/tbesh_lexicon.sqlite3`.
It stores the full parsed TBESH source as English fallback data, without any
Hungarian translation.

Generated audits:

- `data/generated/tahot_ot_import_audit.json`
- `data/generated/tahot_strong_alias_audit.json`
- `data/generated/hebrew_morphology_coverage.json`

The build writes to a temporary SQLite file first, validates the import, then
atomically replaces the production path. On Windows the replacement uses a short
retry because Python's SQLite context manager commits transactions but does not
close connections unless explicitly closed.

The stable clickable unit remains the whole surface word. Prefix, core and
suffix components are retained in `token_components`; component-level selection
is intentionally separate from first-phase surface-word selection.

## Current Full Import Snapshot

Latest local full import from the four official TAHOT files:

- books: 39
- chapters: 830
- verses: 21178
- surface words: 283717
- component rows: 501363
- Hebrew surface words: 280075
- Aramaic surface words: 3642
- ketiv/qere records: 1216
- embedded direct TBESH matches in TAHOT DB: 13212
- full TBESH DB unique entries: 16913

Fourteen duplicate source stable keys from `X` edition rows are skipped with
audit warnings instead of receiving artificial keys. This preserves the
contract that the clickable stable key is `book:chapter:verse:word_index`.

## Alias And Morphology Position

`bible_engine/data/hebrew_strong_aliases.json` starts as an empty production
alias list. The Hebrew audit does not automatically trim suffix letters such as
`H0376H -> H0376`, because suffixes can carry lexical, homograph or
disambiguation meaning. A parser fix now extracts normalized Strong IDs from
annotated TBESH fields such as `H6635B = a Name of`, which reclassifies most
previously missing IDs as direct TBESH matches.

`bible_engine/hebrew_morphology.py` provides a structured TEHMC decoder. It
uses full TEHMC expansions when available, inherits language codes across
slash-separated component analyses, records unknown parts in `unresolved_parts`,
and gives an explicit status: `fully_decoded`, `partially_decoded`,
`unresolved`, or `malformed`. It does not invent Hebrew or Hungarian
terminology for undocumented code fragments.

The generated SQLite databases are large generated artifacts and should not be
committed until the project explicitly decides to version the Hebrew production
data.
