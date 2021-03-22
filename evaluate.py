#!/usr/bin/env python3
import argparse
from decimal import Decimal
import json
from pathlib import Path
import random
import statistics
from typing import Any, Dict, Tuple, List, Set, Optional

import tabulate


def main() -> None:
    """ Perform evaluation for all prediction files, comparing
    results with ground truth.
    Python3.8+ is required.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--n-bootstrap', type=int, default=1000)
    parser.add_argument('--output', type=Path, help='output results as json')
    parser.add_argument('--show-errors', action='store_true')
    args = parser.parse_args()
    root = Path('dataset')
    ground_truth = load_json(root / 'ground-truth.json')
    attributes = {
        'price': decimal_matching,
        'sku': hard_matching,
        'availability': hard_matching,
        'InStock': hard_matching,
        'OutOfStock': hard_matching,
    }
    metrics_by_name: Dict[str, Dict[str, Dict]] = {}
    predictions = {
        path: load_json(path)
        for path in sorted((root / 'output').glob('*.json'))}
    header = ['Attribute', 'System', 'F1', 'Precision', 'Recall', 'Support']
    table = []
    for attribute, metric in attributes.items():
        for path, prediction in predictions.items():
            m = evaluate(
                ground_truth, prediction, attribute, metric,
                n_bootstrap=args.n_bootstrap,
                show_errors=args.show_errors)
            table.append([
                attribute,
                path.stem,
                f'{m["f1"]:.3f} ± {m["f1_std"]:.3f}',
                f'{m["precision"]:.3f} ± {m["precision_std"]:.3f}',
                f'{m["recall"]:.3f} ± {m["recall_std"]:.3f}',
                m['support'],
            ])
            metrics_by_name.setdefault(path.stem, {})[attribute] = m

    print(tabulate.tabulate(table, header, tablefmt='grid'))

    if args.output:
        args.output.write_text(
            json.dumps(metrics_by_name, indent=4, sort_keys=True))


def evaluate(
        ground_truth: Dict[str, Dict[str, Set[str]]],  # multiple gt values
        prediction: Dict[str, Dict[str, str]],  # single predicted value
        attribute: str,
        metric,
        *,
        n_bootstrap: int,
        show_errors: bool,
        ) -> Dict[str, float]:
    """ Evaluate one attribute.
    """
    if ground_truth.keys() != prediction.keys():
        raise ValueError('prediction keys do not match ground truth')
    tp_fp_fns = []
    support = 0
    for key in ground_truth.keys():
        true = set(ground_truth[key].get(attribute, []))
        support += bool(true)
        pred = prediction[key].get(attribute)
        tp_fp_fn = metric(true, pred)
        if show_errors and any(tp_fp_fn[1:]):
            print(attribute, true, repr(pred), tp_fp_fn, key, sep='\t')
        tp_fp_fns.append(tp_fp_fn)
    metrics = metrics_from_tp_fp_fns(tp_fp_fns)
    metrics['support'] = support

    # add bootstrap estimates of condifence intervals
    random.seed(42)
    b_values: Dict[str, List[float]] = {}
    for _ in range(n_bootstrap):
        n = len(tp_fp_fns)
        indices = [random.randint(0, n - 1) for _ in range(n)]
        b_metrics = metrics_from_tp_fp_fns([tp_fp_fns[i] for i in indices])
        for key in b_metrics:
            b_values.setdefault(key, []).append(b_metrics[key])
    for key, values in sorted(b_values.items()):
        metrics[f'{key}_std'] = statistics.stdev(values)

    return metrics


TP_FP_FN = Tuple[int, int, int]


def metrics_from_tp_fp_fns(tp_fp_fns: List[TP_FP_FN]) -> Dict[str, float]:
    tp_fp_fn: TP_FP_FN = tuple(map(sum, zip(*tp_fp_fns)))  # type: ignore
    precision = precision_score(*tp_fp_fn)
    recall = recall_score(*tp_fp_fn)
    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0
    return {
        'f1': f1,
        'precision': precision,
        'recall': recall,
    }


def precision_score(tp: int, fp: int, fn: int) -> float:
    if fp == fn == 0:
        return 1.
    if tp == fp == 0:
        return 0.
    return tp / (tp + fp)


def recall_score(tp: int, fp: int, fn: int) -> float:
    if fp == fn == 0:
        return 1.
    if tp == fn == 0:
        return 0.
    return tp / (tp + fn)


def decimal_matching(true: Set[str], pred: Optional[str]) -> TP_FP_FN:
    return hard_matching(
        {Decimal(x) for x in true},
        Decimal(pred) if pred is not None else None,
    )


def hard_matching(true: Set[Any], pred: Optional[Any]) -> TP_FP_FN:
    tp = fp = fn = 0
    if pred is None:
        if true:
            fn += 1
    else:
        if pred in true:
            tp += 1
        else:
            fp += 1
            if true:
                fn += 1
    return tp, fp, fn


def load_json(path: Path):
    with path.open('rt', encoding='utf8') as f:
        return json.load(f)


if __name__ == '__main__':
    main()
