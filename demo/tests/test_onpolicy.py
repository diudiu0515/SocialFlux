import sys,unittest
from pathlib import Path
ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT/'demo'/'onpolicy'))
from engine import Environment,interpret_action
class T(unittest.TestCase):
 def setUp(self):self.e=Environment()
 def runx(self,xs):
  s=self.e.new_session()
  for x in xs:s,_=self.e.step(s,x)
  return s
 def test_action_sensitivity(self):
  a=self.runx(['我希望逐项核对版本记录和贡献，我们讨论具体方案。']*4);b=self.runx(['你这个无耻的骗子，你就是在霸凌我，我现在就举报你！']*4)
  self.assertEqual(a['discrete_state'],'NEGOTIATION_OPEN');self.assertIn(b['discrete_state'],['HOSTILE','RELATIONSHIP_RUPTURE']);self.assertGreater(b['latent_state']['anger'],a['latent_state']['anger'])
 def test_procedural_escalation(self):
  s=self.runx(['如果无法解决，我会把记录提交学院走正式程序。']*3);self.assertEqual(s['discrete_state'],'THREATENED');self.assertLess(s['trajectory'][-1]['interpreted_action']['dimensions']['hostility'],.4)
 def test_recovery(self):
  s=self.runx(['如果无法解决，我会把记录提交学院走正式程序。']*3)
  for _ in range(5):s,_=self.e.step(s,'我不希望关系闹僵。我们冷静下来逐项核对记录，一起找方案。')
  self.assertIn(s['discrete_state'],['NEGOTIATION_OPEN','DEESCALATED'])
 def test_history_sensitivity(self):
  a=self.runx(['我们逐项核对版本和贡献，讨论具体方案。']*3);b=self.runx(['你这个无耻的骗子，你就是在霸凌我！']*3);a,la=self.e.step(a,'那我们明天再谈。');b,lb=self.e.step(b,'那我们明天再谈。');self.assertNotEqual(la['state_after'],lb['state_after']);self.assertNotEqual(la['advisor_response'],lb['advisor_response'])
 def test_log_and_bounds(self):
  s=self.runx(['我希望看版本记录并讨论署名。']);z=s['trajectory'][0];need={'student_text','interpreted_action','state_before','proposed_state_effects','state_after','discrete_state_before','discrete_state_after','triggered_conditions','observable_cue','advisor_response','memory_after'};self.assertTrue(need.issubset(z));self.assertEqual(len(z['state_after']),15);self.assertTrue(all(0<=v<=100 for v in z['state_after'].values()))
 def test_deterministic_replay(self):
  xs=["我希望看版本记录。","如果不行我会走学院程序。","我们冷静下来一起找方案。"]
  a=self.runx(xs);b=self.runx(xs)
  self.assertEqual(a["latent_state"],b["latent_state"]);self.assertEqual(a["discrete_state"],b["discrete_state"]);self.assertEqual([x["advisor_response"] for x in a["trajectory"]],[x["advisor_response"] for x in b["trajectory"]])
 def test_twenty_turn_limit(self):
  s=self.runx(["请解释署名变更原因。"]*20);self.assertEqual(s["turn_id"],20);self.assertEqual(s["status"],"completed")
  with self.assertRaises(ValueError):self.e.step(s,"继续")
 def test_multilabel(self):
  s=self.e.new_session();a=interpret_action('请逐项核对版本记录，如果不行我会走学院正式程序。',s,s['memory']);self.assertIn('provide_evidence',a['strategy_labels']);self.assertIn('procedural_escalation',a['strategy_labels'])
if __name__=='__main__':unittest.main()
