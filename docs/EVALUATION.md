# Evaluating the classifier

The fixture in `tests/fixtures/problem_detection_eval.jsonl` contains 35 hand-written sentences.
It is a smoke test, not evidence of real-world quality: report numbers only from a labeled sample
of real ingested content.

## Protocol

1. Ingest real data (`python -m scripts.run_unmeet`).
2. Export a stratified sample, 100 items per source:

   ```bash
   python -m scripts.export_eval_sample --output data/eval_sample.jsonl --per-source 100
   ```

3. Label every line by adding `"expected_is_problem": true|false`. Use the definition in the
   classifier prompt (`app/problem_detection/llm.py`). Have a second person label a random 20%
   and report agreement (Cohen's kappa); disagreements show where the definition is ambiguous.
   Freeze the file before looking at model outputs.
4. Evaluate each backend on the same file:

   ```bash
   python -m scripts.evaluate_problem_classifier --dataset data/eval_sample.jsonl --backend qwen3
   python -m scripts.evaluate_problem_classifier --dataset data/eval_sample.jsonl --backend llm
   ```

5. Report precision, recall, F1 **with its 95% bootstrap interval** and the dataset size. Two
   classifiers whose intervals overlap heavily are not meaningfully different on that sample.

`data/` is git-ignored: labeled samples contain user-generated text and stay local.
