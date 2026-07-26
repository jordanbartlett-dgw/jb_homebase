# Third-agent handoff

Slug: med-check
Display name: Med Check
Short description: Medication safety pre-screening for Jordan's daughter (Rett syndrome, congenital Long QT).
Primary purpose: Given a medication name, check public data (RxNorm identity, FDA label QT warnings, CredibleMeds category, Rett-specific sources) against her current medication list and report findings with sources. Decision support for pharmacist and cardiology conversations. It never clears a drug as safe.
Capabilities: core (current_datetime), meds (normalize_medication, fetch_fda_label, get_medication_profile, save_medication_profile), web (search_web, fetch_article), memory (recall_memory, forget_memory)
Suggested icon: Icons.medication_outlined (already wired in Agent.roster)
Preferred accent color: Color(0xFF4A6BE0) (cobalt family, already wired in Agent.roster)
Starter prompts (3-4):
1. "Her doctor wants to start her on [medication]. Can you check it?"
2. "What's on her current med list?"
3. "She started ondansetron 4 mg as needed today. Add it to her profile."
4. "Does amoxicillin interact with anything she takes?"
Special UI/data requirements:
- Reports are long-form markdown with per-source findings and a bottom line. Render markdown fully.
- The agent NEVER says "safe", "cleared", or "no risk". Do not add UI copy implying a safety verdict (no green "all clear" badges). A "no flag found" result is not a clearance.
- On ambiguous drug names the agent asks which one before checking. Expect mid-check clarification turns.
- Checks make several tool calls (RxNorm, openFDA, web); replies can take noticeably longer than claw-main. Existing 120s /app/messages timeout is sufficient.
- Profile updates are conversational (no form needed); one medication_profiles row per org.
- Care documents (emergency one-pager, caregiver handoff) live in the vault, not in the app; the weekly staleness check's nudges arrive as briefing artifacts (pull-only until push).
Commit SHA: bf209b7 (main; includes the agent, the Flutter roster entry, and the history-trim fix)
Production deployed: yes (deploy 80cd3981, commit bf209b7, /health green with three agents)
Database row created and active: yes (agents row read back, prompt byte-identical to migration 022, model resolves to org default sonnet-5)
Verified through POST /app/messages using this slug: yes (2026-07-25, full ondansetron check round-tripped: flagged with FDA label + CredibleMeds sources, no forbidden phrases, $0.28/run in usage_events)
Conversation history verified: yes (GET /app/conversations?agent_slug=med-check returns the conversation with derived title)
