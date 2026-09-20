"""Standard-library bootstrap for isolated candidate checks."""
from __future__ import annotations
import hashlib,json,os,runpy,sys,traceback
from pathlib import Path

def main()->int:
    if len(sys.argv)!=3:raise SystemExit("usage: bootstrap CONFIG RESULT")
    config_path=Path(sys.argv[1]).resolve(strict=True);result_path=Path(sys.argv[2]).resolve();config=json.loads(config_path.read_text(encoding="utf-8"));root=Path(config["staged_root"]).resolve(strict=True);deps=[Path(x).resolve(strict=True) for x in config["dependency_roots"]]
    script_dir=Path(__file__).resolve().parent;stdlib=[]
    for raw in sys.path:
        if not raw:continue
        path=Path(raw).resolve()
        if path not in [script_dir,root,*deps]:stdlib.append(str(path))
    sys.path[:]=[str(root),*(str(x) for x in deps),*stdlib];os.chdir(root);code=0
    try:
        if config["mode"]=="compile":
            from botpipe.core.compiler import compile_workflow
            from botpipe.runtime.loader import resolve_workflow_reference
            compiled=[]
            for reference in config["workflow_refs"]:
                resolved=resolve_workflow_reference(root,reference);plan=compile_workflow(resolved.workflow_cls);source=resolved.source_path
                compiled.append({"requested_reference":reference,"workflow_name":plan.workflow_name,"source_path":None if source is None else str(source.resolve()),"source_sha256":None if source is None else _sha(source)})
            payload={"ok":True,"compiled_workflows":compiled}
        elif config["mode"]=="python":
            code=_run(list(config["argv"]));payload={"ok":code==0,"python_exit_code":code}
        else:raise ValueError("unsupported bootstrap mode")
        origins=_origins();_validate(origins,root,set(config["project_prefixes"]),deps);payload["module_origins"]=origins
    except BaseException as exc:
        if isinstance(exc,SystemExit):
            code=0 if exc.code is None else exc.code if isinstance(exc.code,int) else 1;payload={"ok":code==0,"python_exit_code":code}
            try:origins=_origins();_validate(origins,root,set(config["project_prefixes"]),deps);payload["module_origins"]=origins
            except BaseException as origin:code=1;payload=_error(origin)
        else:code=1;payload=_error(exc)
    temporary=result_path.with_name(f".{result_path.name}.{os.getpid()}.tmp");temporary.write_text(json.dumps(payload,sort_keys=True),encoding="utf-8");os.replace(temporary,result_path);return code
def _run(argv:list[str])->int:
    if not argv:raise ValueError("Python argv must be non-empty")
    if argv[0] in {"pytest","py.test"}:sys.argv=[argv[0],*argv[1:]];runpy.run_module("pytest",run_name="__main__",alter_sys=True);return 0
    first=Path(argv[0]).name.lower()
    if not(first.startswith("python") or Path(argv[0]).resolve()==Path(sys.executable).resolve()):raise ValueError("Python check must start with pytest or interpreter")
    if len(argv)>=3 and argv[1]=="-m":sys.argv=[argv[2],*argv[3:]];runpy.run_module(argv[2],run_name="__main__",alter_sys=True);return 0
    if len(argv)>=2:
        script=Path(argv[1]);script=script if script.is_absolute() else Path.cwd()/script;sys.argv=[str(script),*argv[2:]];runpy.run_path(str(script.resolve(strict=True)),run_name="__main__");return 0
    raise ValueError("Python check must select module or script")
def _origins()->list[dict[str,str]]:
    result=[]
    for name,module in sorted(sys.modules.items()):
        raw=getattr(module,"__file__",None)
        if not isinstance(raw,str):continue
        try:path=Path(raw).resolve(strict=True)
        except OSError:continue
        if path.is_file():result.append({"module":name,"origin":str(path),"sha256":_sha(path)})
    return result
def _validate(origins:list[dict[str,str]],root:Path,prefixes:set[str],deps:list[Path])->None:
    for entry in origins:
        name=entry["module"];origin=Path(entry["origin"])
        if name.split(".",1)[0] in prefixes and not _under(origin,root):raise RuntimeError(f"project module {name!r} loaded outside staged tree: {origin}")
        if "site-packages" in origin.parts and not any(_under(origin,x) for x in deps):raise RuntimeError(f"module {name!r} loaded from unapproved dependency root: {origin}")
def _under(path:Path,root:Path)->bool:
    try:path.relative_to(root);return True
    except ValueError:return False
def _sha(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()
def _error(exc:BaseException)->dict[str,object]:return {"ok":False,"error_type":type(exc).__name__,"error":str(exc),"traceback":traceback.format_exc(limit=20)}
if __name__=="__main__":raise SystemExit(main())
