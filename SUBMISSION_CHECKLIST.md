# Submission checklist

Gemma 4 Good Hackathon — Kaggle + Google DeepMind
Deadline: **May 18, 2026 23:59 UTC**
Competition URL: https://www.kaggle.com/competitions/gemma-4-good-hackathon

---

## What Kaggle expects (from the competition description)

Every submission must include:

1. **Working demo** — functional application running somewhere
2. **Public code repository** — GitHub URL, openly licensed
3. **Technical write-up** — how Gemma 4 is applied, architecture,
   deployment story
4. **Short video** — real-world demonstration, typically 3-5 minutes,
   uploaded to YouTube/Vimeo and linked

The submission happens on the Kaggle competition page after team/solo
registration — Kaggle provides a form with fields for repo URL, writeup
text/URL, and video URL. There is no code upload to Kaggle itself.

Tracks (pick one or more):
- Education
- Health
- Digital Equity
- **Global Resilience** (+ Climate & Green Energy sub-track)
- **Safety**
- Ollama special mention
- Unsloth special mention ($10K separate prize)

Rule text (paraphrased from search-indexed announcements):
- Must use at least one Gemma 4 model
- Preference for solutions working in "low-bandwidth environments,
  areas without cloud connectivity, or contexts where data privacy
  is paramount" — our core pitch matches exactly
- Judging weighted toward impact + technical execution + clarity of
  use case

**Not yet verified** (Kaggle's Rules tab is a JS SPA and didn't render
through automated fetch; human-eyeball needed before submit):
- Exact team-size cap
- Country eligibility list
- Required license on submitted code (Apache 2.0 should be fine; MIT
  would be even safer)
- Whether the writeup must be a Kaggle notebook, a README, or a
  prose document
- Whether video must be publicly listed or can be unlisted

---

## Our submission status

### Ready ✅

| Artifact | State | Location |
|----------|-------|----------|
| Working demo | ✅ | `demo/run_demo.py` — 5-arc end-to-end. Also `demo/gemma_smoke.py` driving real Gemma 4 E2B via Ollama. 252/252 tests pass. |
| Public repo | ✅ | https://github.com/dp-web4/gemma4-good-submission — public, Apache 2.0 + NOTICE |
| Technical writeup | ✅ | `docs/paper.md` — 900+ lines, includes live output appendix |
| Kaggle notebook | ✅ | `notebooks/attested_resilience.ipynb` — 29 cells, auto-falls-back to StubExecutor if no Ollama |
| Track alignment | ✅ | Submitting into **Safety** and **Global Resilience** — pitch in `docs/paper.md §7` maps both |
| Gemma 4 usage | ✅ | `GemmaOllamaExecutor` proven live against gemma4:e2b (gemma4:e4b is the fleet's primary target on 16GB+ machines) |

### Needs action ⚠️

| Artifact | What's missing | Who |
|----------|----------------|-----|
| Video (3-5 min) | **Not recorded yet.** Script + shot list ready in `video/script.md`. HTML visualizer ready in `video/render_bundle.py`. Need actual screen recording + voiceover. | **Dennis** |
| YouTube/Vimeo upload | Video host URL to paste into Kaggle form | **Dennis** |
| Kaggle team registration | Team formation, agree to rules, select tracks | **Dennis** |
| Kaggle submission form | Paste repo URL + writeup link + video URL | **Dennis** |
| License verification | Confirm Kaggle accepts Apache 2.0 (should be fine; MIT is safer if they're strict) | **Dennis** to check on Rules tab |
| Unsloth stretch | Delegated to Thor (fleet plan doc exists); LoRA training + upload; optional for main submission | **Thor** |

### Optional polish 📎

- **Landing page** for the repo — currently using GitHub README, which
  is adequate. A vercel-hosted version with the architecture diagram
  rendered would look nicer but isn't required.
- **Demo video in the README** — embed YouTube player on GitHub render
  after recording.
- **Paper PDF** — export `docs/paper.md` to PDF. Most judges will read
  on GitHub; PDF only adds value if they want to print.

---

## Recommended submission sequence (when ready to submit)

1. Record the video (3-5 min) following `video/script.md`
2. Upload to YouTube, unlisted unless Kaggle rules require public
3. Verify Kaggle Rules tab for:
   - Accepted code license (Apache 2.0 — if not accepted, we can
     retroactively add a MIT dual-license; all submission code is
     clean-room so no legal blocker)
   - Video hosting requirements (public vs unlisted)
   - Writeup field type (URL vs text)
   - Team size and eligibility
4. Join the competition; form a team (or solo) on Kaggle
5. Final `git push` to the submission repo; tag `v1.0-submission`
6. Paste into the Kaggle submission form:
   - **Repo URL**: `https://github.com/dp-web4/gemma4-good-submission`
   - **Writeup**: link to `docs/paper.md` on the tag
   - **Video**: YouTube URL
   - **Tracks**: Safety, Global Resilience (and Ollama/Unsloth if fields exist)
7. Submit. Confirm receipt email.

---

## What "ready" means today

**Core claim**: everything we can ship from code is shipped. The repo
is public, the architecture runs end-to-end on real hardware, the paper
is complete, the notebook is Kaggle-ready.

**What's left is human-in-the-loop**: recording a 3-5 minute video,
registering on Kaggle, and pasting four URLs into a form.

**Risk check**: none of the remaining steps require rebuilding or
reshaping what's been done. If the repo were submitted exactly as it
stands today (plus a video and a Kaggle form), the submission would
land on the Safety and Global Resilience tracks with a complete,
reproducible, cryptographically-anchored story.

---

## Open questions a human needs to answer before submit

1. **Who is the submitter?** Dennis / Metalinxx Inc. as the team lead,
   with Claude Opus 4.6 credited as co-author in the paper's byline.
2. **Team name on Kaggle?** Suggestion: `dp-web4` (matches GitHub org).
3. **Contact email** for the Kaggle account — needs to be one the
   submitter actually checks; prize communications go here.
4. **Prize assignment** — if we win, who receives? (Prize T&Cs live on
   Kaggle's Rules tab; worth reading before submit.)
5. **Is the Unsloth stretch in-scope for this submission or separate?**
   Kaggle allows multiple submissions for special tracks; recommend
   submitting the main architecture now and the LoRA fine-tune as a
   parallel Unsloth track entry once Thor completes it.
