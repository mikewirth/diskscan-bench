import sys, os, json, importlib.util
sys.argv=[sys.argv[0]]+sys.argv[1:]
spec=importlib.util.spec_from_file_location("b",os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","site","build.py"))
src=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","site","build.py")).read()
# only load defs, avoid main
src=src.split("\nif __name__")[0]
g={"__file__":os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","site","build.py"),"__name__":"b"}
exec(compile(src,"build.py","exec"),g)
for f in sys.argv[1:]:
    r=json.load(open(f)); out,base,bad=g["scores"](r,"cli")
    print("==",f,r["runner"]["platform"],"baseline",base,"suspect",bad)
    for i,d in enumerate(out,1):
        print(f'{i:2} {d["tool"]:10} {d["score"]:.2f}x  n={d["n"]}/{d["cells"]} cold={d["cold"] or 0:.3f} warm={d["warm"] or 0:.3f} {d["warn"]}')
