"""run_intent_eval.py - compares intent-routing methods on eval/data/eval_set.csv.

Run (from the project root):  python eval/run_intent_eval.py
Needs:  pip install -e ".[eval]"

Methods
  1. rules      : keyword/regex baseline (order_assistant.routing.rules)
  2. tfidf_lr   : TF-IDF (word + character n-grams) + logistic regression

Validation: 5-fold GroupKFold BY template_id. A model is always tested on
templates it never saw in training, so it cannot just memorise wording.
Order IDs are masked so the model cannot memorise specific IDs.

Outputs: eval/results/intent_eval.json and eval/results/intent_confusion_tfidf_lr.csv
"""
import json
import pathlib
import re

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline, make_union

from order_assistant.routing.rules import INTENTS, rule_based_intent

HERE = pathlib.Path(__file__).parent
DATA = HERE / "data" / "eval_set.csv"
RESULTS = HERE / "results"


def mask_ids(text):
    return re.sub(r"ORD-\d+", "ORDERID", text)


def build_model():
    features = make_union(
        TfidfVectorizer(lowercase=True, ngram_range=(1, 2)),
        TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(2, 4)),
    )
    return make_pipeline(features, LogisticRegression(max_iter=2000, class_weight="balanced"))


def main():
    df = pd.read_csv(DATA)
    texts = df["query"].map(mask_ids)
    y = df["intent"]
    groups = df["template_id"]

    # 1) rule-based baseline: no training, so it is evaluated on every row
    rules_pred = df["query"].map(rule_based_intent)

    # 2) TF-IDF + LR: out-of-fold predictions
    lr_pred = pd.Series(index=df.index, dtype=object)
    for train_idx, test_idx in GroupKFold(n_splits=5).split(texts, y, groups):
        model = build_model().fit(texts.iloc[train_idx], y.iloc[train_idx])
        lr_pred.iloc[test_idx] = model.predict(texts.iloc[test_idx])

    results = {}
    for name, pred in [("rules", rules_pred), ("tfidf_lr", lr_pred)]:
        results[name] = {
            "accuracy": round(accuracy_score(y, pred), 3),
            "macro_f1": round(f1_score(y, pred, average="macro", labels=list(INTENTS), zero_division=0), 3),
            "per_class": classification_report(y, pred, labels=list(INTENTS),
                                               output_dict=True, zero_division=0),
        }

    print(f"{len(df)} queries, {groups.nunique()} templates\n")
    print(f"{'method':10} {'accuracy':>9} {'macro_f1':>9}")
    for name, r in results.items():
        print(f"{name:10} {r['accuracy']:>9} {r['macro_f1']:>9}")

    print("\nPer-class F1")
    print(f"{'intent':20} {'rules':>7} {'tfidf_lr':>9}")
    for intent in INTENTS:
        a = results["rules"]["per_class"][intent]["f1-score"]
        b = results["tfidf_lr"]["per_class"][intent]["f1-score"]
        print(f"{intent:20} {a:>7.2f} {b:>9.2f}")

    # Where does the language matter?
    print("\nAccuracy by language (tfidf_lr)")
    for lang, sub in df.groupby("language"):
        print(f"  {lang:10} {accuracy_score(sub['intent'], lr_pred[sub.index]):.3f}")

    RESULTS.mkdir(exist_ok=True)
    cm = pd.DataFrame(confusion_matrix(y, lr_pred, labels=list(INTENTS)),
                      index=[f"true_{i}" for i in INTENTS], columns=[f"pred_{i}" for i in INTENTS])
    cm.to_csv(RESULTS / "intent_confusion_tfidf_lr.csv")
    (RESULTS / "intent_eval.json").write_text(json.dumps(results, indent=2))

    # Rows the better model got wrong: your starting point for error analysis.
    errors = df.assign(pred=lr_pred)[lr_pred != y][["query", "intent", "pred"]]
    errors.to_csv(RESULTS / "intent_errors_tfidf_lr.csv", index=False)
    print(f"\nsaved results to {RESULTS} ({len(errors)} misclassified rows in intent_errors_tfidf_lr.csv)")


if __name__ == "__main__":
    main()
