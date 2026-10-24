#!/usr/bin/env python3
"""Render selected budget curves from bundled aggregate metrics; no fitting or API calls."""
import argparse
import hashlib
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/figures'))
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import ScalarFormatter
    root = Path(__file__).resolve().parent
    source = root / 'reports/all-budget-curves/source-metrics.json'
    data = json.loads(source.read_text())
    if data['status'] != 'complete' or data['synthetic']:
        raise ValueError('Expected completed real-data aggregate results')
    budgets = [0, 100, 200, 300, 400, 500]
    cases = [('sodium', 'gender', 'deepseek', 'Sodium: female to male', 'DeepSeek', '#E69F00', '^'),
             ('potassium', 'dosage', 'gpt-4o-mini', 'Potassium: low to high dose', 'GPT-4o-mini', '#009E73', 's')]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
        'axes.spines.top': False, 'axes.spines.right': False,
        'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(1, 2, figsize=(10.3, 5.1))
    fig.subplots_adjust(left=.09, right=.98, bottom=.27, top=.76, wspace=.34)
    fig.suptitle('Selected APRIL-style baselines: annotation budget curves',
                 y=.96, fontsize=15, fontweight='bold')
    for ax, (task, split, model, title, label, color, marker) in zip(axes, cases):
        selected = {r['requested_annotation_budget']: r for r in data['rows']
                    if r['task'] == task and r['split'] == split and r['model_key'] == model}
        rows = [selected[b] for b in budgets]
        if any(r['status'] != 'complete' or r['paired_draws'] != 500 for r in rows):
            raise ValueError('A selected curve is incomplete')
        dm, se = rows[0]['dm_rmse'], rows[0]['dm_rmse_mc_se_delta']
        ys = [r['dmplus_rmse'] for r in rows]
        es = [r['dmplus_rmse_mc_se_delta'] for r in rows]
        ax.errorbar(budgets, [dm]*6, yerr=[se]*6, color='#0072B2', marker='o',
                    linestyle='--', linewidth=1.6, markersize=4, capsize=3, label='DM')
        ax.errorbar(budgets, ys, yerr=es, color=color, marker=marker,
                    linewidth=2, markersize=5, capsize=3, label=f'DM+ ({label})')
        ax.set_title(title, fontsize=12, pad=16)
        ax.set_xlabel('Requested counterfactual annotations', labelpad=8)
        ax.set_ylabel('Policy-value RMSE (lower is better)')
        ax.set_xticks(budgets)
        ax.set_xlim(-18, 518)
        ax.grid(axis='y', color='#E3E7EC', linewidth=.7)
        low = min(min(y-e for y, e in zip(ys, es)), dm-se)
        high = max(max(y+e for y, e in zip(ys, es)), dm+se)
        span = high-low
        ax.set_ylim(max(0, low-.14*span), high+.20*span)
        fmt = ScalarFormatter(useMathText=True)
        fmt.set_powerlimits((-3, 3)); fmt.set_useOffset(False)
        ax.yaxis.set_major_formatter(fmt)
        ax.legend(loc='lower left', frameon=False, fontsize=9)
        ax.text(.97, .95, f"500-budget gain: {rows[-1]['relative_rmse_improvement_pct']:.2f}%",
                transform=ax.transAxes, ha='right', va='top', fontsize=10)
    notes = [
        'Selected after inspecting results; all five-model results are retained separately. Independent zoomed y-axes.',
        'Each point uses 500 paired patient-bootstrap draws. Bars: +/- 1 Monte Carlo SE, not a 95% confidence interval.',
        'Budgets count requested labels; valid at 500: DeepSeek 497, GPT-4o-mini 499. Invalid labels are not replaced.',
        'Reference: observed target-validation reward mean proxy, not known causal policy value.'
    ]
    for i, line in enumerate(notes):
        fig.text(.065, .16-i*.033, line, fontsize=8.2, color='#475467')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for ext in ('pdf', 'png', 'svg'):
        path = out / f'selected_baseline_budget_curves.{ext}'
        fig.savefig(path, dpi=200, facecolor='white')
        files.append(path.name)
    plt.close(fig)
    metadata = {'source': 'reports/all-budget-curves/source-metrics.json',
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'statistics_recomputed': False, 'database_queries': 0, 'llm_calls': 0,
                'output_hashes': {name: hashlib.sha256((out/name).read_bytes()).hexdigest() for name in files}}
    (out/'figure-manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps({'status': 'rendered', 'directory': str(out)}))

if __name__ == '__main__':
    main()
