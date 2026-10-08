# Evaluation

```bash
pip install -e ".[eval]"
python eval/build_eval_set.py        # writes data/eval_set.csv (147 synthetic queries)
python eval/run_intent_eval.py       # rules vs TF-IDF + logistic regression, no API key needed
python eval/run_agent_eval.py --limit 20   # end-to-end agent; needs MySQL + GROQ_API_KEY, uses free-tier quota
```

## What each script measures

| Script | Question |
|--------|----------|
| `run_intent_eval.py` | Can a cheap router classify the intent without calling the LLM? Rules vs a trained model |
| `run_agent_eval.py` | (uses Groq; add `--sleep 4` if you hit rate limits) Does the agent call the right tool, hand off when it should, and **never leak another customer's order**? |

## Read the numbers honestly

- The eval set is **synthetic**: made from 98 hand-written templates. It is good for building and debugging, not for claims.
- The rules were written by someone who had already seen this style of wording, so the baseline's score is optimistic.
- 98 templates is very little training data, so the trained model is starved. A baseline beating a model is a real and common result, and it is a finding, not a bug.
- Before you quote any number in a resume, add 50-100 queries you wrote or collected yourself (including real Hinglish with typos) and re-run.

## Results from the first run (synthetic set)

| Method | Accuracy | Macro-F1 |
|--------|---------:|---------:|
| Rules | 0.741 | 0.695 |
| TF-IDF + LR | 0.653 | 0.676 |

Weakest classes and the error list: see `results/intent_errors_tfidf_lr.csv`.

## Ideas for next experiments

1. Sentence embeddings + logistic regression instead of TF-IDF.
2. Ask the LLM to classify intent (few-shot) and compare accuracy, latency and cost.
3. Replace the regex injection flag with a classifier and compare precision/recall on `adversarial`.
4. Policy questions: add retrieval over longer policy documents and measure recall@k.
5. Prompt versions: change `PROMPT_VERSION` in `agent/prompts.py` and compare tool accuracy.
