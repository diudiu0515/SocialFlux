"""Local transport compatibility for the observed GPT route top_p rejection.

The canonical appraisers and their prompts remain unchanged. Keep this scoped to
new offline jobs rather than mutating the shared environment/provider defaults.
"""
from pathlib import Path
import json
import time
from uuid import uuid4


class OfflineLoggedProvider:
    """Keep actual requests, outputs and failed attempts in private run files."""
    def __init__(self, provider, directory):
        self.provider=provider
        self.directory=Path(directory)

    def __getattr__(self,name):
        return getattr(self.provider,name)

    def complete(self,messages,**generation):
        from offline.choice_builder import save
        self.directory.mkdir(parents=True,exist_ok=True)
        record={'messages':messages,'generation':generation,'started_at_unix':time.time(),'status':'running'}
        path=self.directory/(uuid4().hex+'.json')
        save(path,record)
        try:
            result=self.provider.complete(messages,**generation)
            record['raw_output']=result
            record['status']='completed'
            return result
        except Exception as exc:
            record['status']='failed'
            record['error']={'type':type(exc).__name__,'message':str(exc)}
            raise
        finally:
            record['elapsed_seconds']=round(time.time()-record['started_at_unix'],3)
            metrics = getattr(self.provider, 'metrics', None)
            if isinstance(metrics, dict):
                record['provider_metrics'] = metrics
            save(path,record)

class OfflineSamplingProvider:
    def __init__(self, provider):
        self.provider=provider
        self.omitted_sampling=[]

    def __getattr__(self,name):
        return getattr(self.provider,name)

    @property
    def provenance(self):
        return {**self.provider.provenance,'offline_transport_omits':['top_p']}

    def complete(self,messages,**generation):
        omitted={k:generation.pop(k) for k in ['top_p'] if k in generation}
        if omitted:self.omitted_sampling.append(omitted)
        return self.provider.complete(messages,**generation)


class OfflineRuntimeFactory:
    def __init__(self,base,log_dir=None):
        self.base=base
        self.log_dir=Path(log_dir) if log_dir else None

    @property
    def provenance(self):
        return {**self.base.provenance,'offline_transport_omits':{'gpt_state_and_interaction':['top_p']}}

    def __call__(self):
        env=self.base()
        for role,appraiser in [('state',env.state_updater.state_appraiser),('interaction',env.state_updater.interaction_appraiser)]:
            appraiser.provider=OfflineSamplingProvider(appraiser.provider)
            if self.log_dir:
                appraiser.provider=OfflineLoggedProvider(appraiser.provider,self.log_dir/role)
        if self.log_dir:
            env.response_generator.provider=OfflineLoggedProvider(env.response_generator.provider,self.log_dir/'response')
        env.state_updater.provider=env.state_updater.state_appraiser.provider
        env.provenance=self.provenance
        return env
