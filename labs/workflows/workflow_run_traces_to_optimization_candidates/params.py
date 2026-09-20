from __future__ import annotations
import warnings
from typing import Any,Literal
from pydantic import ConfigDict,Field,field_validator,model_validator
from botpipe_optimizer import SelectedWorkflowTaskFramingParameters
from botpipe.stdlib import positive_int_fields
class Params(SelectedWorkflowTaskFramingParameters):
    model_config=ConfigDict(extra="forbid")
    run_refs:list[str]=Field(default_factory=list); run_statuses:list[str]=Field(default_factory=lambda:["success","failed","awaiting_input","blocked","paused"]); route_tags:list[str]=Field(default_factory=list)
    history_limit:int=25; top_k_steps:int=1; objective:Literal["reliability","token_usage","latency"]="reliability"
    include_adversarial_generation:bool=True; include_token_optimization:bool=True; include_workflow_level_candidates:bool=True
    max_candidates:int=3; max_provider_turns:int=6; provider_turn_timeout_seconds:int=600; max_analysis_seconds:int=1800
    max_evidence_bytes:int=50*1024*1024; max_output_bytes:int=10*1024*1024; focus:str|None=None; sponsor_role:str|None=None; desired_outcome:str|None=None; constraints:list[str]=Field(default_factory=list)
    max_candidates_per_pass:int|None=Field(default=None,exclude=True); optimization_depth:Literal["cheap","standard","ablation"]|None=Field(default=None,exclude=True)
    @model_validator(mode="before")
    @classmethod
    def aliases(cls,value:Any):
        if not isinstance(value,dict): return value
        d=dict(value)
        if "max_candidates_per_pass" in d:
            if "max_candidates" in d and d["max_candidates"]!=d["max_candidates_per_pass"]: raise ValueError("max_candidates conflicts with deprecated max_candidates_per_pass")
            d["max_candidates"]=d["max_candidates_per_pass"]; warnings.warn("max_candidates_per_pass is deprecated; use max_candidates",FutureWarning,stacklevel=2)
        if d.get("optimization_depth") is not None:
            warnings.warn("optimization_depth is deprecated; ablation is planning-only",FutureWarning,stacklevel=2); turns,seconds=((12,3600) if d["optimization_depth"]=="standard" else (6,1800)); d.setdefault("max_provider_turns",turns); d.setdefault("max_analysis_seconds",seconds)
        return d
    @field_validator("run_refs")
    @classmethod
    def refs(cls,v):
        if any(x.count("/")!=1 or not all(x.split("/",1)) for x in v) or len(v)!=len(set(v)): raise ValueError("run_refs must be unique task_id/run_id values")
        return v
    @field_validator("run_statuses","route_tags","constraints")
    @classmethod
    def lists(cls,v):
        out=[]
        for x in v:
            x=str(x).strip()
            if not x: raise ValueError("list entries must be non-empty")
            if x not in out: out.append(x)
        return out
    _positive=positive_int_fields("history_limit","top_k_steps","max_candidates","max_provider_turns","provider_turn_timeout_seconds","max_analysis_seconds","max_evidence_bytes","max_output_bytes")
__all__=["Params"]
