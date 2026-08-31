"""Controlled policies for environment validity checks."""

class ControlledPolicy:
    def __init__(self, policy_id, actions, repeat_last=True):
        if not actions:
            raise ValueError("controlled policy requires at least one action")
        self.policy_id = policy_id
        self.actions = list(actions)
        self.repeat_last = repeat_last
        self.index = 0

    def reset(self):
        self.index = 0

    def generate(self, observation):
        if self.index >= len(self.actions) and not self.repeat_last:
            raise StopIteration
        index = min(self.index, len(self.actions) - 1)
        self.index += 1
        action = self.actions[index]
        if isinstance(action, str):
            return {"action_id": "default", "text": action}
        return dict(action)
