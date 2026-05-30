# code:langchain_genai:ch03 — Building Workflows with LangGraph

book: Generative AI with LangChain
slug: langchain_genai
chapter: ch03
chapter_title: Building Workflows with LangGraph
repo: https://github.com/benman1/generative_ai_with_langchain (branch second_edition)
folder: chapter3

## Summary
<!-- AUTHOR:summary — 2-4 sentences on what this chapter's code does -->

## Libraries & frameworks
IPython, base64, collections, enum, langchain, langchain_core, langchain_google_genai, langgraph, logging, operator, pydantic, typing, typing_extensions

## Models & APIs
<!-- AUTHOR:models — models/APIs used, e.g. gpt-4o, text-embedding-3-large -->

## Concepts / patterns
<!-- AUTHOR:concepts — patterns demonstrated, tie to book theme -->

## Files
- README.md — <!-- AUTHOR:purpose --> (md)
- error_handling.ipynb — <!-- AUTHOR:purpose --> (py)
- langgraph_intro.ipynb — <!-- AUTHOR:purpose --> (py)
- map_reduce.ipynb — <!-- AUTHOR:purpose --> (py)
- memory.ipynb — <!-- AUTHOR:purpose --> (py)
- multimodality.ipynb — <!-- AUTHOR:purpose --> (py)
- output_parsers.ipynb — <!-- AUTHOR:purpose --> (py)
- prompt_templates.ipynb — <!-- AUTHOR:purpose --> (py)
- retry_with_error_output_parser.ipynb — <!-- AUTHOR:purpose --> (py)
- self_consistency.ipynb — <!-- AUTHOR:purpose --> (py)

## Code entities
- error_handling.ipynb: IsSuitableJobEnum, analyze_job_description, MessagesIterator, JobApplicationState, generate_application, is_suitable_condition, analyze_job_description, analyze_job_description
- langgraph_intro.ipynb: JobApplicationState, analyze_job_description, generate_application, is_suitable_condition, JobApplicationState, analyze_job_description, generate_application, JobApplicationState, analyze_job_description, generate_application, my_reducer, JobApplicationState, analyze_job_description, generate_application, generate_application
- map_reduce.ipynb: _create_input_messages, _merge_summaries, AgentState, _ChunkState, _summarize_video_chunk, _map_summaries, _generate_final_summary
- memory.ipynb: PrintOutputCallback, get_session_history, test_node
- output_parsers.ipynb: IsSuitableJobEnum, JobApplicationState, analyze_job_description, is_suitable_condition, generate_application
- retry_with_error_output_parser.ipynb: SearchAction

## Key snippets
<!-- AUTHOR:snippets — paste a few short representative blocks -->
