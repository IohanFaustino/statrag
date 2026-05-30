# code:neo4j_llm:ch07 — Introducing the Neo4j Spring AI and LangChain4j Frameworks for Building Recommendation Systems

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch07
chapter_title: Introducing the Neo4j Spring AI and LangChain4j Frameworks for Building Recommendation Systems
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch7

## Summary
Chapter 7 uses Cypher scripts to build a fashion retail knowledge graph from the H&M dataset (customers, articles, transactions) as the foundation for LangChain4j and Spring AI recommendation systems. Seven `.cql` files progressively create constraints and indexes, load Customer and Article nodes with rich taxonomy (ProductType, ProductGroup, GraphicalAppearance, ColorGroup, Department, Index, GarmentGroup), ingest transaction sequences as a linked list (START_TRANSACTION → NEXT → LATEST), derive seasonal sub-graphs (SUMMER_2019 etc. via APOC dynamic relationships), and query seasonal purchase history.

## Libraries & frameworks
(none detected — pure Cypher/Neo4j scripts)

## Models & APIs
- Neo4j (local or Aura, APOC plugin required)
- Neo4j APOC (`apoc.create.relationship` for dynamic season relationship names)

## Concepts / patterns
- knowledge graph construction for retail recommendations (Customer, Article, Product, Transaction nodes)
- linked-list transaction modeling (START_TRANSACTION → NEXT chain → LATEST pointer)
- dynamic relationship naming via APOC (`SUMMER_2019`, `FALL_2019`, …) for seasonal segmentation
- graph traversal to extract customer purchase sequences per season
- foundation for Spring AI / LangChain4j graph-augmented recommendation (ch9)

## Files

## Code entities
(none detected)

## Key snippets

```cypher
-- 04-load-articles.cql — article taxonomy graph construction
MERGE(a:Article {id:row.article_id})
SET a.desc = row.detail_desc
MERGE(p:Product {code:row.product_code})
MERGE(a)-[:OF_PRODUCT]->(p)
MERGE(pt:ProductType {id:row.product_type_no})
MERGE(p)-[:HAS_TYPE]->(pt)
-- ... continues for ProductGroup, ColorGroup, Department, Index, GarmentGroup
```

```cypher
-- 05-load-transactions.cql — linked-list transaction chain
CREATE (t:Transaction {date: row.t_dat, price: row.price})
CREATE (t)-[:HAS_ARTICLE]->(a)
-- Append to linked list:
MATCH (c)-[r:LATEST]->(lt) DELETE r
CREATE (lt)-[:NEXT]->(t)
CREATE (c)-[:LATEST]->(t)
```

```cypher
-- 06-create-season-relationships.cql — APOC dynamic seasonal edges
WITH c, relName, head(collect(node)) as start
WHERE relName is not null
CALL apoc.create.relationship(c, relName, {}, start) YIELD rel
-- relName examples: 'SUMMER_2019', 'FALL_2019'
```
