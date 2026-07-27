"""Prompts for semantic JD match analysis and gap closing.

Why these exist: the JD Match tab used to score the resume by exact token
overlap against every non-stopword in the posting, so "onsite" and "benefits"
sat in the denominator and `Kubernetes` never matched `K8s`. These prompts grade
the *requirements* the extractor already pulled off the posting, semantically,
and then close the ones that came back short.

The match score itself is NOT asked of the model — it is computed from the
per-requirement statuses in ``services/jd_match.py``. A model asked for a
percentage invents a plausible one; a model asked to judge one requirement at a
time can be checked against its own evidence quote.

Literal JSON braces are doubled because services call ``.format()`` on these.
"""

JD_MATCH_PROMPT = """Judge how well this resume evidences each job requirement. Output ONLY the JSON object, no other text.

You are screening the way a technical recruiter does: you are looking for evidence the candidate has done the thing, not for the exact word. Judge MEANING, not string overlap.

STATUS for each requirement - pick exactly one:
- "covered": the resume shows this clearly. Equivalents count in full: K8s = Kubernetes, RESTful services = REST APIs, Postgres = PostgreSQL, CI pipelines = CI/CD, "built data pipelines" = ETL. A demonstrated superset counts (React Native experience covers "mobile development").
- "partial": adjacent or implied but not shown directly - the requirement asks for depth, scale, or a specific tool the resume only brushes against. Also use this when the resume names the technology but shows no work with it.
- "missing": nothing in the resume speaks to this.

RULES:
1. Judge every requirement given below, in the order given. Do not add, merge, split, or drop any.
2. "evidence" must QUOTE the resume text that convinced you, copied exactly. For "missing", use an empty string.
3. Do not credit a requirement because the job description mentions it. Only the resume counts as evidence.
4. Do not invent evidence. If you cannot quote it, the status is not "covered".
5. "gap_note" is for "partial" and "missing" only: one short clause naming what is absent, written for the candidate. Empty string for "covered".
6. Write evidence quotes verbatim; write gap_note in {output_language}.

REQUIREMENTS TO JUDGE:
{requirements}

RESUME (JSON):
{resume_data}

JOB DESCRIPTION (context for what each requirement means, NOT evidence):
{job_description}

Output this exact JSON format, nothing else:
{{
  "requirements": [
    {{
      "requirement": "the requirement text, copied exactly from the list above",
      "status": "covered",
      "evidence": "exact quote from the resume, or empty string",
      "gap_note": "what is missing, or empty string"
    }}
  ]
}}"""


CLOSE_GAPS_PROMPT = """Close these resume gaps against the job description. Output ONLY the JSON object, no other text.

Each gap below is a job requirement the resume does not evidence. For each one, emit the ONE change that makes the resume evidence it.

CHANGE TYPES - use exactly these two:
1. action "add_skill" on path "additional.technicalSkills" - value is the skill name. Use this when the gap is a tool, technology, framework, or platform.
2. action "append" on path "workExperience[i].description" or "personalProjects[i].description" - value is one new bullet. Use this when the gap is a responsibility, practice, or scope. Pick the entry index where the work most plausibly belongs, and write the bullet as work done in that role.

RULES:
1. Emit at most one change per gap. Skip a gap only when neither change type fits.
2. A gap may need BOTH a skill and a bullet - in that case emit the bullet, and add the skill separately only if the skill is not already in the list.
3. Bullets: one concise line, plain action verb, the job description's terminology, concrete figures where they make the bullet land. NEVER these verbs or buzzwords in any form: spearhead, orchestrate, champion, leverage, utilize, facilitate, architect (as a verb), robust, scalable, seamless, holistic, cutting-edge, world-class, best-in-class, impactful, proactive, dynamic, results-driven.
4. NEVER change or invent employers, job titles, dates, degrees, or certifications, and never add a work, education, or project ENTRY. You are only appending bullets to entries that already exist and adding skills.
5. "original" must be null for both action types.
6. "reason" states which gap the change closes, in {output_language}, and that it is a suggested addition for the candidate to confirm.
7. Do not use em dash characters.
8. Write all new text in {output_language}.

GAPS TO CLOSE:
{gaps}

EXISTING SKILLS (do not re-add anything already here):
{existing_skills}

RESUME ENTRIES you may append to:
{entry_index}

RESUME (JSON):
{resume_data}

JOB DESCRIPTION:
{job_description}

Output this exact JSON format, nothing else:
{{
  "changes": [
    {{
      "path": "additional.technicalSkills",
      "action": "add_skill",
      "original": null,
      "value": "Kubernetes",
      "reason": "closes the Kubernetes gap; suggested addition to confirm"
    }},
    {{
      "path": "workExperience[0].description",
      "action": "append",
      "original": null,
      "value": "Ran deployments on Kubernetes across three environments, cutting release time to under 10 minutes.",
      "reason": "closes the container orchestration gap; suggested addition to confirm"
    }}
  ],
  "strategy_notes": "brief note on how the gaps were closed"
}}"""
