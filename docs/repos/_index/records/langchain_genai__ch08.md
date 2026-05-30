# code:langchain_genai:ch08 — Evaluation and Testing

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch08
chapter_title: Evaluation and Testing
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter8

## Summary
Chapter 8 covers systematic evaluation of LLM applications at three levels of sophistication. The basic evaluators notebook demonstrates exact-match, LLM-as-judge scoring (with and without reference), and criteria-based evaluation (tone, conciseness, JSON format). The advanced notebook adds chain-of-thought reasoning assessment and agent trajectory analysis with a custom `trajectory_subsequence` subsequence-matching scorer. The LangSmith notebook shows how to create evaluation datasets, configure multi-dimensional evaluators (accuracy, completeness, clarity, financial accuracy), and run benchmarks with LangSmith's `evaluate` API against an insurance-claim RAG chain.

## Libraries & frameworks
config, datasets, evaluate, langchain, langchain_community, langchain_core, langchain_mistralai, langchain_openai, langsmith, os, pydantic, sys

## Models & APIs
`mistral-large-latest` (ChatMistralAI — ScoreStringEvalChain LLM judge), `ChatOpenAI` default (LangSmith evaluation and RAG chain), `gpt-4o` referenced as judge model in LangSmith multi-dimensional evaluator

## Concepts / patterns
LLM-as-judge evaluation (ScoreStringEvalChain, LabeledScoreStringEvalChain), ExactMatchStringEvaluator, criteria-based evaluation (conciseness, tone), chain-of-thought reasoning evaluator (`cot_qa`), agent trajectory evaluation with custom subsequence scorer, LangSmith dataset creation and `evaluate()` benchmarking, multi-dimensional evaluation (accuracy, completeness, clarity, financial accuracy), tracing with LANGCHAIN_TRACING_V2.

## Files
- README.md — Chapter overview with per-notebook descriptions and Colab/Kaggle links (md)
- advanced_evaluation.ipynb — Chain-of-thought reasoning evaluation and agent trajectory scoring with trajectory_subsequence (py)
- basic_evaluators.ipynb — Exact-match, LLM-as-judge (scored and labeled), and criteria-based evaluators for finance Q&A (py)
- langsmith_evaluation.ipynb — LangSmith dataset creation, multi-dimensional LLM-judge evaluators, and full benchmark run against a RAG chain (py)

## Code entities
- advanced_evaluation.ipynb: trajectory_subsequence, run_graph_with_trajectory
- langsmith_evaluation.ipynb: construct_chain, InsuranceClaim

## Key snippets
```python
# Exact match and LLM-as-judge scoring (basic_evaluators.ipynb)
from langchain.evaluation import load_evaluator, ExactMatchStringEvaluator
from langchain_mistralai import ChatMistralAI
from langchain.evaluation.scoring import ScoreStringEvalChain

exact_evaluator = ExactMatchStringEvaluator(ignore_case=True)
result = exact_evaluator.evaluate_strings(prediction="0.25%", reference="0.25%")

llm = ChatMistralAI(temperature=0, model="mistral-large-latest")
chain = ScoreStringEvalChain.from_llm(llm=llm)
scored = chain.evaluate_strings(input="What is the Fed rate?", prediction="0.25%")
```

```python
# Trajectory subsequence scorer (advanced_evaluation.ipynb)
def trajectory_subsequence(outputs: dict, reference_outputs: dict) -> float:
    """Check how many of the desired steps the agent took."""
    i = j = 0
    while i < len(reference_outputs['trajectory']) and j < len(outputs['trajectory']):
        if reference_outputs['trajectory'][i] == outputs['trajectory'][j]:
            i += 1
        j += 1
    return i / len(reference_outputs['trajectory'])
```
