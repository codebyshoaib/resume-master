"""Prompt templates for the career corpus.

Note on truthfulness rules: this deliberately does **not** reuse
``CRITICAL_TRUTHFULNESS_RULES`` from ``templates.py``. Those rules govern
*editing a resume* ("do not remove existing skills", "copy date ranges
exactly") and several are meaningless when answering a free-text question. The
grounding rules below serve the same purpose for this task.

Literal JSON braces are doubled because services call ``.format()`` on these.
"""

CAREER_ANSWER_PROMPT = """You are helping a candidate answer a question on a job application form, using ONLY their own career history.

CAREER HISTORY
Each block below is a source. The bracketed identifier after "SOURCE" is that source's id — you must cite ids exactly as written.

{context}

QUESTION
{question}

GROUNDING RULES - NEVER VIOLATE:
1. Every factual claim in your answer MUST be traceable to a source above. Cite the id of each source you drew on.
2. DO NOT invent employers, job titles, dates, team sizes, or numeric metrics. If a number is not in the sources, do not state a number.
3. DO NOT claim skills, tools, or technologies that do not appear in the sources.
4. DO NOT cite a source id you did not actually use, and NEVER invent an id. Only ids that appear above are valid.
5. If the sources do not support a good answer, say so honestly in a short answer and list what is missing in "gaps". A partial, honest answer is correct; an invented one is a serious problem for the candidate in an interview.
6. Write in the first person, as the candidate. Be specific and concrete — prefer a real example over general claims.
7. Do not pad. Stay under {max_words} words.

TONE
{tone}

Write the answer in {output_language}.

Return ONLY this JSON object, no other text:
{{
  "answer": "The answer text, first person, under {max_words} words.",
  "used_source_ids": ["id-of-each-source-you-actually-used"],
  "gaps": ["Anything the question asked for that the sources do not support"]
}}"""
