# code:neo4j_llm:ch04 — Building Your Neo4j Graph with Movies Dataset

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch04
chapter_title: Building Your Neo4j Graph with Movies Dataset
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch4

## Summary
Chapter 4 builds a production-scale Neo4j knowledge graph from the TMDB movies dataset (~10 000 movies). Normalizing scripts parse raw CSV metadata into flat CSVs for genres, production companies, countries, spoken languages, cast, crew, and keywords. The `CreateGraph` class then ingests all data via Cypher `LOAD CSV` with `MERGE` + constraint enforcement, creating a rich multi-entity graph with nodes Movie, Genre, ProductionCompany, Country, SpokenLanguage, Person (Actor/Director/Producer/User) and relationships ACTED_IN, DIRECTED, PRODUCED, HAS_GENRE, RATED, and more.

## Libraries & frameworks
ast, dotenv, neo4j, os, pandas, warnings

## Models & APIs
- Neo4j Aura (or local Neo4j instance via bolt)
- Google Cloud Storage (CSV source: `storage.googleapis.com/movies-packt/`)

## Concepts / patterns
- knowledge graph construction from structured CSV data
- Cypher MERGE + constraint-based upsert pattern
- LOAD CSV with HEADERS + CALL…IN TRANSACTIONS for large dataset ingestion
- APOC `apoc.create.relationship` for dynamic relationship types (DIRECTED, PRODUCED)
- multi-label entity modeling (Person also labeled Actor/Director/Producer/User)
- graph schema with uniqueness constraints and property indexes

## Files
- graph_build.py — `CreateGraph` class: creates constraints/indexes, loads movies, genres, companies, countries, languages, keywords, actors, crew, links, and ratings via Cypher LOAD CSV (py)
- normalizing_scripts/normalize_credits.py — Parses raw `credits.csv` to extract cast (actor_id, name, character) and crew (Director/Producer) into flat CSVs (py)
- normalizing_scripts/normalize_keywords.py — Parses raw `keywords.csv` JSON arrays and aggregates keyword names per movie into `normalized_keywords.csv` (py)
- normalizing_scripts/normalize_movies_metadata.py — Extracts genres, production companies, countries, spoken languages, and collection names from `movies_metadata.csv` into separate normalized CSVs (py)

## Code entities
- graph_build.py: CreateGraph, main
- normalizing_scripts/normalize_credits.py: extract_cast, extract_crew
- normalizing_scripts/normalize_keywords.py: normalize_keywords
- normalizing_scripts/normalize_movies_metadata.py: extract_genres, extract_production_companies, extract_production_countries, extract_spoken_languages, extract_collection_name

## Key snippets

```python
# graph_build.py — constraint and index creation
queries = [
    "CREATE CONSTRAINT unique_tmdb_id IF NOT EXISTS FOR (m:Movie) REQUIRE m.tmdbId IS UNIQUE;",
    "CREATE CONSTRAINT unique_genre_id IF NOT EXISTS FOR (g:Genre) REQUIRE g.genre_id IS UNIQUE;",
    "CREATE INDEX actor_id IF NOT EXISTS FOR (p:Person) ON (p.actor_id);",
]
```

```cypher
// graph_build.py — LOAD CSV actor ingestion with batched transactions
LOAD CSV WITH HEADERS FROM $csvFile AS row
CALL (row) {
  MATCH (m:Movie {tmdbId: toInteger(row.tmdbId)})
  MERGE (p:Person {actor_id: toInteger(row.actor_id)})
  ON CREATE SET p.name = row.name, p.role = 'actor'
  MERGE (p)-[a:ACTED_IN]->(m)
  ON CREATE SET a.character = coalesce(row.character, "None")
} IN TRANSACTIONS OF 50000 ROWS;
```

```python
# normalize_movies_metadata.py — extract genres from JSON string
def extract_genres(genres_str):
    genres_list = ast.literal_eval(genres_str)
    return [{'genre_id': int(g['id']), 'genre_name': g['name']} for g in genres_list]
```
