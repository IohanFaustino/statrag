# code:langchain_genai:ch07 — Software Development and Data Analysis Agents

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch07
chapter_title: Software Development and Data Analysis Agents
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter7

## Summary
Chapter 7 applies LLM agents to two specialist domains: software development and data analysis. The software-development track builds a `PythonDeveloper` sandbox that takes a task description, generates Python code via an LLM, executes it in a sandboxed subprocess with an audit log, and auto-installs missing packages. The data-science track creates a `create_pandas_dataframe_agent` over an Iris CSV and a `create_python_agent` with a PythonREPLTool for exploratory analysis. Additional notebooks demonstrate code models (HumanEval benchmarking, CodeGemma), code understanding via RAG over a cloned Git repository, and building a Chroma RAG over LangChain docs using `text-embedding-3-large`.

## Libraries & frameworks
chapter7, config, contextlib, data_science, dataclasses, datasets, evaluate, git, huggingface_hub, io, langchain, langchain_anthropic, langchain_chroma, langchain_community, langchain_core, langchain_experimental, langchain_google_genai, langchain_openai, langchain_text_splitters, langsmith, logging, math, nest_asyncio, os, pandas, pathlib, pip, pydantic, pygame, re, sklearn, streamlit, sys, transformers, typing, uuid

## Models & APIs
`claude-3-opus-20240229` (ChatAnthropic — data_science.ipynb Python REPL agent), `ChatOpenAI` default (data_science agent and langchain_rag), `gemini-pro` (code_models.ipynb code generation), `google/codegemma-2b` (HuggingFacePipeline — software_development.ipynb), `text-embedding-3-large` via `CacheBackedEmbeddings` (langchain_rag.ipynb), Chroma vector store, FAISS alternative

## Concepts / patterns
Python code generation and sandboxed execution with audit trail, auto package installation, `PythonREPLTool` agent, `create_pandas_dataframe_agent` for CSV data analysis, `create_python_agent`, HumanEval benchmark evaluation (`code_eval` metric, `pass@k`), code understanding RAG (clone repo → `GenericLoader` + `LanguageParser` → `RecursiveCharacterTextSplitter.from_language` → Chroma QA chain), `DocusaurusLoader` for documentation RAG, CacheBackedEmbeddings.

## Files
- README.md — Chapter overview with notebook and subdirectory links (md)
- __init__.py — Chapter package init (py)
- code_models.ipynb — Evaluates code models on HumanEval (pass@k metric) and generates FizzBuzz with Gemini-pro (py)
- code_understanding.ipynb — Clones the book's GitHub repo, parses Python files with LanguageParser, builds a Chroma RAG for code Q&A (py)
- data_science/__init__.py — Package init for the data_science subpackage (py)
- data_science/agent.py — create_pandas_dataframe_agent factory (create_agent) and query_agent wrapper using ChatOpenAI (py)
- data_science/app.py — Streamlit GUI for interactive data analysis via the pandas agent (py)
- data_science/prompts.py — System prompt template for the data analysis agent (py)
- data_science.ipynb — Runs create_python_agent with Claude-3-opus (PythonREPLTool) and create_pandas_dataframe_agent on Iris CSV (py)
- langchain_rag.ipynb — Crawls LangChain docs with DocusaurusLoader, builds Chroma vector store with text-embedding-3-large, runs Q&A chain (py)
- software_development/README.md — Instructions for the software development subproject (md)
- software_development/__init__.py — Subpackage init (py)
- software_development/baby_dev.py — Minimal LLM-driven code generation demo (py)
- software_development/customer.py — Customer class demonstrating generated code patterns (py)
- software_development/customer2.py — Alternate Customer variant (py)
- software_development/dev/main.py — Entry point for the software development sandbox (py)
- software_development/prime_numbers.py — LLM-generated prime number calculator (calculate_primes) (py)
- software_development/prime_numbers2.py — Revised calculate_primes version (py)
- software_development/python_developer.py — PythonDeveloper class: LLM code generation, sandboxed exec, auto-install, audit log (py)
- software_development/test.py — construct_chain helper for testing generated code (py)
- software_development.ipynb — Demonstrates calculate_primes completion and simple_code_completion with CodeGemma (py)

## Code entities
- data_science/agent.py: create_agent, query_agent
- langchain_rag.ipynb: format_docs
- software_development/customer.py: Customer
- software_development/customer2.py: Customer
- software_development/prime_numbers.py: calculate_primes
- software_development/prime_numbers2.py: calculate_primes
- software_development/python_developer.py: PythonExecutorInput, meaningful_output, set_directory, PythonDeveloper
- software_development/test.py: construct_chain
- software_development.ipynb: calculate_primes, simple_code_completion

## Key snippets
```python
# PythonDeveloper: generate + execute code with auto-install (python_developer.py)
class PythonDeveloper:
    def run(self, task: str, filename: str = "serve_index.py") -> str:
        code = self.write_code(task)          # LLM generates code
        if self.do_sanitize_input:
            code = sanitize_input(code)
        self.write_file(code=code, filename=filename)
        try:
            return self.execute_code(code, filename)
        except ModuleNotFoundError as ex:
            if self.install_package(ex):      # auto-install missing package
                return self.execute_code(code, filename)
            raise ex
```

```python
# create_pandas_dataframe_agent for Iris CSV (data_science/agent.py)
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent

def create_agent(csv_file: str) -> AgentExecutor:
    llm = ChatOpenAI()
    df = pd.read_csv(csv_file)
    return create_pandas_dataframe_agent(llm, df, verbose=True)
```
