"""Local transport compatibility for the observed GPT route top_p rejection.

The canonical appraisers and their prompts remain unchanged. Keep this scoped to
new offline jobs rather than mutating the shared environment/provider defaults.
"""
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
    def __init__(self,base):
        self.base=base

    @property
    def provenance(self):
        return {**self.base.provenance,'offline_transport_omits':{'gpt_state_and_interaction':['top_p']}}

    def __call__(self):
        env=self.base()
        for appraiser in (env.state_updater.state_appraiser,env.state_updater.interaction_appraiser):
            appraiser.provider=OfflineSamplingProvider(appraiser.provider)
        env.state_updater.provider=env.state_updater.state_appraiser.provider
        env.provenance=self.provenance
        return env
