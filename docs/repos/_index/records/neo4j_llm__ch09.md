# code:neo4j_llm:ch09 — Integrating LangChain4j and Spring AI with Neo4j

book: Building Neo4j-Powered Applications with LLMs
slug: neo4j_llm
chapter: ch09
chapter_title: Integrating LangChain4j and Spring AI with Neo4j
repo: https://github.com/PacktPublishing/Building-Neo4j-Powered-Applications-with-LLMs (branch main)
folder: ch9

## Summary
Chapter 9 provides two parallel Spring Boot applications — one using LangChain4j and one using Spring AI — that embed fashion article descriptions into Neo4j and then generate customer purchase summaries with OpenAI. The LangChain4j app uses `langchain4j-neo4j` for the vector store, `langchain4j-open-ai-spring-boot-starter` for chat and `langchain4j-embeddings-all-minilm-l6-v2` for local embeddings, exposing a REST endpoint that batches article embeddings into Neo4j and returns LLM-generated purchase summaries. The Spring AI app mirrors the same architecture using `spring-ai-neo4j-store-spring-boot-starter` and `spring-ai-openai-spring-boot-starter` (Spring AI 1.0.0-M3).

## Libraries & frameworks
- LangChain4j (`langchain4j-spring-boot-starter`, `langchain4j-open-ai-spring-boot-starter`, `langchain4j-neo4j`, `langchain4j-embeddings-all-minilm-l6-v2`)
- Spring AI (`spring-ai-neo4j-store-spring-boot-starter`, `spring-ai-openai-spring-boot-starter`, version 1.0.0-M3)
- Spring Boot 3.3.5, Maven

## Models & APIs
- OpenAI GPT (chat, via LangChain4j `langchain4j-open-ai-spring-boot-starter` and Spring AI `spring-ai-openai`)
- `all-MiniLM-L6-v2` (LangChain4j local embedding model, `langchain4j-embeddings-all-minilm-l6-v2`)
- OpenAI embeddings (Spring AI variant)
- Neo4j vector store (LangChain4j `langchain4j-neo4j`; Spring AI `spring-ai-neo4j-store`)

## Concepts / patterns
- GraphRAG with LangChain4j: Neo4j vector store + OpenAI chat for fashion purchase summarisation
- GraphRAG with Spring AI: Neo4j vector store + OpenAI embeddings + chat, same use case
- batch embedding ingestion into Neo4j (100-record batches, thread-safe)
- `@AiService` interface pattern in LangChain4j for declarative prompt engineering
- REST controller exposing `/encode` (embed articles) and `/chat` (generate summary) endpoints
- seasonal graph traversal context fed to the LLM for personalised summaries

## Files
- langchain_graphaugment/HELP.md — Spring Boot Maven project setup guide for the LangChain4j application (md)
- springai_graphaugment/HELP.md — Spring Boot Maven project setup guide for the Spring AI application (md)

## Code entities
(none detected)

## Key snippets

```java
// langchain_graphaugment — ChatAssistant @AiService (LangChain4j declarative prompt)
@AiService
public interface ChatAssistant {
    @SystemMessage("""
        You are a helpful assistant with expertise in fashion for a clothing company.
        Generate a summary of products purchased by the customer.
        Section 1 - Overall fashion preference summary (3 sentences).
        Section 2 - Highlight 3-5 individual purchases.
        Data: {text}
    """)
    String chat(String text);
}
```

```java
// langchain_graphaugment — ProcessArticles: batch embedding into Neo4j (LangChain4j)
if (i > 0 && i % batchSize == 0) {
    List<Embedding> embedList = embeddingModelService.generateEmbeddingBatch(inputData);
    for (int j = 0; j < embedList.size(); j++) {
        embedMap.put("id", ids.get(j));
        embedMap.put("embedding", embedList.get(j).vector());
        embeddings.add(embedMap);
    }
    neo4jService.saveArticleEmbeddings(embeddings);
}
```

```java
// springai_graphaugment — ProcessRequest: seasonal context retrieval + chat (Spring AI)
List<EncodeRequest> dbData = neo4jService.getDataFromDB(startSeason, endSeason);
// Embeds purchase summaries and calls OpenAI chat via Spring AI OpenAI starter
```
