import argparse,json,sys,threading,os,secrets
from copy import deepcopy
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
R=Path(__file__).resolve().parents[1]
S=R/"demo"/"static"
D=R/"demo"/"data"/"trajectories"
sys.path.insert(0,str(R/"demo"/"onpolicy"))
from engine import Environment
E=Environment()
L=threading.RLock()
M={}
TOKEN=os.getenv("EMOTREE_DEBUG_TOKEN") or secrets.token_urlsafe(12)
def authorized(u):
 return secrets.compare_digest(parse_qs(u.query).get("token",[""])[0],TOKEN)
def path(i):return D/(i+".json")
def save(x):
 D.mkdir(parents=True,exist_ok=True);path(x["session_id"]).write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")
def load(i):
 if i in M:return M[i]
 if path(i).exists():M[i]=json.loads(path(i).read_text());return M[i]
def participant(x):
 last=x["trajectory"][-1] if x["trajectory"] else None
 # Participant payload contains only observable output. Hidden state, transition
 # labels, thresholds and research logs remain server-side.
 observation={
  "cue":(last.get("observable_cue") or {}).get("text") if last else E.scenario["opening"]["cue"],
  "external":deepcopy((last.get("observable_cue") or {}).get("multimodal_control")) if last else None,
 }
 return {"session_id":x["session_id"],"scenario_id":x["scenario_id"],"status":x["status"],"turn_id":x["turn_id"],"max_turns":x["max_turns"],"conversation":x["conversation"],"current_advisor_message":x["conversation"][-1],"state_observation":observation,"created_at":x["created_at"],"updated_at":x["updated_at"]}
def compact(x):return {"session_id":x["session_id"],"turn_id":x["turn_id"],"status":x["status"],"discrete_state":x["discrete_state"],"previous_state":x["previous_state"],"created_at":x["created_at"],"updated_at":x["updated_at"],"transition_count":sum(bool(t["state_transition"]) for t in x["trajectory"])}
class App(SimpleHTTPRequestHandler):
 def __init__(self,*a,**k):super().__init__(*a,directory=str(S),**k)
 def reply(self,x,n=200):
  b=json.dumps(x,ensure_ascii=False).encode();self.send_response(n);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(b)
 def body(self):return json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}")
 def do_GET(self):
  u=urlparse(self.path);p=u.path
  if p in ["/researcher.html","/replay.html"] and not authorized(u):return self.reply({"error":"researcher token required"},403)
  if p=="/api/health":return self.reply({"ok":True,"scenario":E.scenario["scenario_id"]})
  if p=="/api/scenario":
   s=E.scenario;return self.reply({"scenario_id":s["scenario_id"],"title":s["title"],"world_facts":s["world_facts"],"student":s["student"],"advisor":{"identity":s["advisor"]["identity"]},"max_turns":s["max_turns"],"opening":s["opening"]})
  if p=="/api/sessions":
   if not authorized(u):return self.reply({"error":"researcher token required"},403)
   a=[]
   for f in D.glob("*.json") if D.exists() else []:
    try:a.append(compact(json.loads(f.read_text())))
    except:pass
   a.sort(key=lambda x:x["updated_at"],reverse=True);return self.reply(a)
  if p.startswith("/api/sessions/"):
   i=p.split("/")[3];x=load(i)
   if not x:return self.reply({"error":"session not found"},404)
   view=parse_qs(u.query).get("view",["participant"])[0]
   if view=="researcher" and not authorized(u):return self.reply({"error":"researcher token required"},403)
   return self.reply(deepcopy(x) if view=="researcher" else participant(x))
  return super().do_GET()
 def do_POST(self):
  u=urlparse(self.path);q=u.path.strip("/").split("/")
  try:
   b=self.body()
   if u.path=="/api/sessions":
    with L:x=E.new_session(b.get("mode","participant"));M[x["session_id"]]=x;save(x)
    return self.reply(participant(x),201)
   if len(q)>=4 and q[:2]==["api","sessions"]:
    with L:
     x=load(q[2])
     if not x:return self.reply({"error":"session not found"},404)
     if q[3]=="turn":x,t=E.step(x,b.get("student_text",""));save(x);return self.reply({"participant":participant(x),"turn_id":t["turn_id"],"transition_occurred":bool(t["state_transition"])})
     if q[3]=="end":x["status"]="completed";save(x);return self.reply(participant(x))
     if q[3]=="fork":
      if not authorized(u):return self.reply({"error":"researcher token required"},403)
      y=E.new_session("researcher")
      for t in x["trajectory"]:
       if t["turn_id"]>int(b.get("through_turn",x["turn_id"])):break
       y,_=E.step(y,t["student_text"])
      M[y["session_id"]]=y;save(y);return self.reply(y,201)
   return self.reply({"error":"not found"},404)
  except Exception as e:return self.reply({"error":str(e)},400)
 def log_message(self,f,*a):print("[demo] "+f%a)
def main():
 p=argparse.ArgumentParser();p.add_argument("--host",default="0.0.0.0");p.add_argument("--port",type=int,default=8000);a=p.parse_args();s=ThreadingHTTPServer((a.host,a.port),App);print("Participant: http://127.0.0.1:{}/".format(a.port));print("Researcher: http://127.0.0.1:{}/researcher.html?token={}".format(a.port,TOKEN));print("Replay: http://127.0.0.1:{}/replay.html?token={}".format(a.port,TOKEN))
 try:s.serve_forever()
 except KeyboardInterrupt:pass
if __name__=="__main__":main()
