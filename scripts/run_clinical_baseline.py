#!/usr/bin/env python3
"""Fit local clinical policy clones and OLS DM point baselines on complete artifacts."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np
from threadpoolctl import threadpool_limits, threadpool_info
from april_repro.clinical_dataset import load_clinical_dataset
from april_repro.clinical_models import fit_policy, fit_reward
from april_repro.cohort_splits import ACTIONS, SPLITS

RULE_VERSION = 'clinical-baseline-v1'
DEPENDENCIES = {'numpy':'2.2.6', 'scipy':'1.15.3', 'scikit-learn':'1.7.2',
                'joblib':'1.5.2', 'threadpoolctl':'3.6.0'}
CODE_PATHS = ('scripts/run_clinical_baseline.py', 'src/april_repro/clinical_dataset.py',
              'src/april_repro/clinical_models.py', 'src/april_repro/rewards.py',
              'src/april_repro/decision_features.py', 'src/april_repro/cohort_splits.py',
              'src/april_repro/cohort_patient_splits.py', 'config/clinical-baseline.toml',
              'requirements-g3.lock')


def validate_protocol(protocol):
    # This file records the fixed main implementation; it is not a tuning grid.
    expected={'policy':{'model':'sklearn.linear_model.LogisticRegression','solver':'lbfgs',
                        'penalty':'l2','fit_intercept':True,'C':1.0,'tol':1e-4,'max_iter':1000,'random_state':0,'class_weight':'none'},
              'reward':{'model':'sklearn.linear_model.LinearRegression','fit_intercept':True,
                        'context_action_interactions':False,'penalty':'none','clip_predictions':False,
                        'action_encoding':'discrete paper action divided by40 forK or500 forNa',
                        'training_population':'behavior train events only','reward_formula':'main text sigma=2.5'},
              'evaluation':{'d0':'target validation empirical event distribution; event equal weights',
                            'bootstrap_datasets':0},
              'execution':{'blas_threads':1,'prediction_batch_size':5000,
                           'patient_rows_local_only':True,'external_llm_calls':False,'database_queries':False}}
    if protocol.get('rule_version')!=RULE_VERSION:
        raise ValueError('Point baseline protocol mismatch')
    for section, fields in expected.items():
        if any(protocol.get(section,{}).get(key)!=value for key,value in fields.items()):
            raise ValueError('Recorded settings differ from this fixed main implementation')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for part in iter(lambda:handle.read(1024*1024),b''): h.update(part)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n'
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as handle:
        tmp=Path(handle.name); handle.write(payload.encode())
    tmp.chmod(0o600); tmp.replace(path)


def action_counts(values,task):
    return {str(a):int(np.count_nonzero(values==a)) for a in ACTIONS[task]}


def classification_report(y, probabilities, train_actions, task):
    actions=np.asarray(ACTIONS[task])
    y=np.asarray(y); probabilities=np.asarray(probabilities)
    if y.ndim!=1 or probabilities.shape!=(len(y),len(actions)):
        raise ValueError('Invalid policy validation dimensions')
    if not np.isin(y,actions).all() or not np.isin(train_actions,actions).all():
        raise ValueError('Unknown action in policy validation')
    if not np.isfinite(probabilities).all() or np.any(probabilities<0) or np.any(probabilities>1):
        raise ValueError('Invalid policy probabilities')
    if len(y) and not np.allclose(probabilities.sum(axis=1),1,rtol=0,atol=1e-10):
        raise ValueError('Policy probability rows do not sum to one')
    support=action_counts(y,task); training=action_counts(train_actions,task)
    counts=np.asarray([training[str(a)] for a in actions])
    majority=int(actions[int(np.argmax(counts))]) if counts.sum() else None
    report={'status':'estimated' if len(y) and majority is not None else 'not_estimable',
            'validation_events':len(y),'training_action_counts':training,'validation_action_counts':support,
            'action_order':actions.tolist(),'training_majority_action':majority,
            'absent_training_actions':[int(a) for a in actions if not training[str(a)]],
            'accuracy':None,'always_zero_accuracy':None,'training_majority_accuracy':None,
            'confusion_matrix':None,'recall_by_action':{str(a):None for a in actions}}
    if report['status']=='not_estimable':
        report['reason']='empty_validation' if not len(y) else 'empty_training'
        return report
    predicted=actions[np.argmax(probabilities,axis=1)]
    confusion=np.zeros((len(actions),len(actions)),dtype=np.int64)
    np.add.at(confusion,(np.searchsorted(actions,y),np.searchsorted(actions,predicted)),1)
    report.update(accuracy=float(np.mean(predicted==y)),always_zero_accuracy=float(np.mean(y==0)),
                  training_majority_accuracy=float(np.mean(y==majority)),confusion_matrix=confusion.tolist(),
                  recall_by_action={str(a):float(confusion[i,i]/support[str(a)]) if support[str(a)] else None
                                    for i,a in enumerate(actions)})
    return report


def usable_policy(model):
    state=model.to_dict()
    converged=getattr(model,'converged',state.get('metadata',{}).get('converged',state.get('converged')))
    return model.status=='complete' and (converged is True or (converged is None and state.get('link')=='constant'))


def score_policy(model, dataset, train, validation):
    y=dataset.actions[validation]
    if not usable_policy(model):
        return {'status':'not_estimable','reason':'policy_training_unavailable_or_not_converged',
                'validation_events':len(y),'accuracy':None,
                'training_action_counts':action_counts(dataset.actions[train],dataset.task),
                'validation_action_counts':action_counts(y,dataset.task)}
    probabilities=model.predict_proba(dataset.features[validation]) if len(y) else np.empty((0,len(ACTIONS[dataset.task])))
    report=classification_report(y,probabilities,dataset.actions[train],dataset.task)
    report.update(training_events=int(train.sum()),training_subjects=int(len(np.unique(dataset.subject_ids[train]))),
                  validation_subjects=int(len(np.unique(dataset.subject_ids[validation]))))
    return report


def point_dm(policy, reward_model, dataset, evaluation, behavior_train, dest, batch_size=5000):
    indices=np.flatnonzero(evaluation)
    base={'evaluation_events':len(indices),'evaluation_subjects':int(len(np.unique(dataset.subject_ids[evaluation]))),
          'd0':'target_validation_empirical_event_distribution',
          'reference':'same_target_validation_observed_reward_mean_proxy',
          'bootstrap_datasets':0,'rmse':None,'standard_error':None,'dm':None,
          'observed_reference':None,'signed_difference':None,'absolute_difference':None}
    if not len(indices):
        return dict(base,status='not_estimable',reason='empty_target_validation')
    if not usable_policy(policy) or reward_model.status=='not_estimable':
        return dict(base,status='not_estimable',reason='dependent_model_unavailable_or_not_converged')
    actions=ACTIONS[dataset.task]
    behavior_counts=action_counts(dataset.actions[behavior_train],dataset.task)
    unsupported=np.asarray([behavior_counts[str(a)]==0 for a in actions])
    values=[]; refs=[]; unsupported_sums=[]; outside=0
    path=dest/'dm-evaluation.csv'
    fields=['event_id','subject_id','hadm_id','observed_action','observed_reward','expected_reward']
    fields += ['pi_'+str(a) for a in actions]+['reward_'+str(a) for a in actions]
    with path.open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,lineterminator='\n'); writer.writeheader()
        for start in range(0,len(indices),batch_size):
            selected=indices[start:start+batch_size]; X=dataset.features[selected]
            probabilities=policy.predict_proba(X)
            # Each model applies its own training-fitted preprocessor to raw X.
            predictions=reward_model.predict_action_values(X)
            if not np.isfinite(predictions).all(): raise ValueError('Nonfinite OLS prediction')
            if probabilities.shape!=predictions.shape or not np.isfinite(probabilities).all():
                raise ValueError('Policy/reward action dimensions disagree')
            if np.any(probabilities<0) or not np.allclose(probabilities.sum(axis=1),1,rtol=0,atol=1e-10):
                raise ValueError('Invalid evaluation probabilities')
            expectation=(probabilities*predictions).sum(axis=1)
            values.append(float(expectation.sum())); refs.append(float(dataset.rewards[selected].sum()))
            unsupported_sums.append(float(probabilities[:,unsupported].sum()))
            outside+=int(np.count_nonzero((predictions<0)|(predictions>1)))
            for offset,i in enumerate(selected):
                row={'event_id':dataset.event_ids[i],'subject_id':int(dataset.subject_ids[i]),
                     'hadm_id':int(dataset.hadm_ids[i]),'observed_action':int(dataset.actions[i]),
                     'observed_reward':float(dataset.rewards[i]),'expected_reward':float(expectation[offset])}
                row.update({'pi_'+str(a):float(probabilities[offset,j]) for j,a in enumerate(actions)})
                row.update({'reward_'+str(a):float(predictions[offset,j]) for j,a in enumerate(actions)})
                writer.writerow(row)
    path.chmod(0o600)
    import math
    dm=math.fsum(values)/len(indices); ref=math.fsum(refs)/len(indices)
    return dict(base,status='estimated',dm=dm,observed_reference=ref,signed_difference=dm-ref,
                absolute_difference=abs(dm-ref),behavior_training_action_counts=behavior_counts,
                target_probability_mass_on_behavior_unseen_actions=math.fsum(unsupported_sums)/len(indices),
                ols_action_predictions_outside_unit_interval=outside,ols_predictions_clipped=False,
                predictions_file=path.name)


def run(source):
    source=(ROOT/source).resolve()
    if not source.is_relative_to((ROOT/'artifacts/treatment-features').resolve()):
        raise ValueError('Input must be a local treatment-features artifact')
    dependencies={name:importlib.metadata.version(name) for name in DEPENDENCIES}
    if dependencies!=DEPENDENCIES: raise ValueError('Numerical backend does not match requirements-g3.lock')
    protocol=tomllib.loads((ROOT/'config/clinical-baseline.toml').read_text())
    validate_protocol(protocol)
    if subprocess.run(['git','check-ignore','--quiet','artifacts/clinical-baselines/probe'],
                      cwd=ROOT,capture_output=True).returncode:
        raise ValueError('Clinical output must be Git ignored')
    dataset=load_clinical_dataset(source)
    versions={rel:sha(ROOT/rel) for rel in CODE_PATHS}
    parent=ROOT/'artifacts/clinical-baselines'; parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    dest=Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-')+dataset.task+'-',dir=parent))
    for rel in versions:
        target=dest/'code'/rel;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copyfile(ROOT/rel,target);target.chmod(0o600)
    input_manifest=json.loads((source/'manifest.json').read_text())
    inputs={'directory':str(source.relative_to(ROOT)),'manifest_sha256':sha(source/'manifest.json'),
            'outputs':input_manifest['outputs']}
    manifest={'rule_version':RULE_VERSION,'status':'running','task':dataset.task,'started_at_utc':now(),
              'input':inputs,'versions':versions,'dependencies':dependencies,'protocol':protocol,
              'runtime':{'python':platform.python_version(),'machine':platform.machine()},
              'dataset_summary':dataset.summary,'results':{},'database_queried':False,'llm_called':False,
              'bootstrap_executed':False,'full_paper_reproduction_complete':False}
    save(dest/'manifest.json',manifest)
    try:
        with threadpool_limits(limits=1):
            manifest['runtime']['threadpools']=threadpool_info()
            for split in SPLITS:
                out=dest/split;out.mkdir(mode=0o700)
                behavior_train=dataset.mask(split,'behavior','train')
                target_train=dataset.mask(split,'target','train')
                models={role:fit_policy(dataset.features[mask],dataset.actions[mask],dataset.task)
                        for role,mask in [('behavior',behavior_train),('target',target_train)]}
                reward=fit_reward(dataset.features[behavior_train],dataset.actions[behavior_train],
                                  dataset.rewards[behavior_train],dataset.task)
                for role,model in models.items():save(out/(role+'-policy.json'),model.to_dict())
                save(out/'reward-model.json',reward.to_dict())
                policies={role:score_policy(models[role],dataset,mask,dataset.mask(split,role,'validation'))
                          for role,mask in [('behavior',behavior_train),('target',target_train)]}
                dm=point_dm(models['target'],reward,dataset,dataset.mask(split,'target','validation'),behavior_train,out)
                report={'split':split,'policies':policies,'dm':dm}
                save(out/'summary.json',report);manifest['results'][split]=report
                save(dest/'manifest.json',manifest)
        if sha(source/'manifest.json')!=inputs['manifest_sha256'] or any(sha(source/name)!=digest for name,digest in inputs['outputs'].items()):
            raise ValueError('Input artifact changed during fitting')
        if any(sha(ROOT/rel)!=digest for rel,digest in versions.items()):
            raise ValueError('Source code changed during fitting')
        manifest['status']='complete'
        manifest['outputs']={str(p.relative_to(dest)):sha(p) for p in dest.rglob('*')
                             if p.is_file() and p.name!='manifest.json' and 'code' not in p.relative_to(dest).parts}
    except Exception as exc:
        manifest.update(status='failed',error_type=type(exc).__name__,error=str(exc))
    manifest['finished_at_utc']=now();save(dest/'manifest.json',manifest)
    return {'status':manifest['status'],'artifact':str(dest.relative_to(ROOT)),
            'results':manifest['results'],'error_type':manifest.get('error_type')}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input-directory',required=True)
    args=parser.parse_args(argv);old=os.umask(0o077)
    try:
        result=run(Path(args.input_directory));print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0 if result['status']=='complete' else 2
    finally:os.umask(old)


if __name__=='__main__': raise SystemExit(main())
