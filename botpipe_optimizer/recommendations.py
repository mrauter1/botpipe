"""Deterministic validation, publication, and consumer loading for optimizer v2."""
from __future__ import annotations
import json, os, tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
from .records import Candidate, CandidateKind, CandidateReview, CandidateSet, HandoffCandidate, PublicationReceipt, RefinementHandoff

def atomic_write_bytes(path:Path,content:bytes)->Path:
    path.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f: f.write(content); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return path
def atomic_write_record(path,record):
    payload=record.model_dump(mode="json",by_alias=True) if hasattr(record,"model_dump") else record
    return atomic_write_bytes(path,(json.dumps(payload,indent=2,sort_keys=True)+"\n").encode())
def _read_bounded(path:Path,limit:int,label:str)->bytes:
    if limit<=0: raise ValueError(f"{label} byte limit must be positive")
    if not path.is_file() or path.is_symlink(): raise ValueError(f"{label} must be a regular file")
    if path.stat().st_size>limit: raise ValueError(f"{label} exceeds byte limit")
    return path.read_bytes()
def read_candidate_set(path:Path,*,max_output_bytes:int)->CandidateSet: return CandidateSet.model_validate_json(_read_bounded(path,max_output_bytes,"CandidateSet"),strict=True)
def read_candidate_review(path:Path,*,max_output_bytes:int)->CandidateReview: return CandidateReview.model_validate_json(_read_bounded(path,max_output_bytes,"candidate review"),strict=True)
def _field(obj,name): return obj.get(name) if isinstance(obj,Mapping) else getattr(obj,name)
def _citable(snapshot):
    fn=getattr(snapshot,"citable_observation_ids",None)
    if callable(fn): return set(fn())
    return {(_field(o,"observation_id")) for o in (_field(snapshot,"observations") or [])}
def validate_candidate_set(candidate_set:CandidateSet,*,evidence_snapshot,max_candidates:int,allowed_kinds:Iterable[CandidateKind],expected_selected_workflow:str,allowed_target_paths:Iterable[str]|None=None,allowed_target_prefixes:Iterable[str]=())->CandidateSet:
    if max_candidates<=0: raise ValueError("max_candidates must be positive")
    candidate_set.verify_identity()
    if candidate_set.selected_workflow!=expected_selected_workflow: raise ValueError("CandidateSet selected_workflow does not match invocation")
    if candidate_set.evidence_snapshot_id!=_field(evidence_snapshot,"snapshot_id"): raise ValueError("CandidateSet evidence snapshot mismatch")
    if candidate_set.baseline_surface_manifest_id!=_field(evidence_snapshot,"baseline_surface_manifest_id"): raise ValueError("CandidateSet baseline mismatch")
    if len(candidate_set.candidates)>max_candidates: raise ValueError("CandidateSet exceeds max_candidates")
    ids=[c.candidate_id for c in candidate_set.candidates]
    if len(ids)!=len(set(ids)): raise ValueError("candidate IDs must be unique across kinds")
    forbidden=sorted({c.kind for c in candidate_set.candidates}-set(allowed_kinds))
    if forbidden: raise ValueError(f"disabled candidate kinds: {', '.join(forbidden)}")
    exact=None if allowed_target_paths is None else set(allowed_target_paths); prefixes=tuple(x.rstrip("/")+"/" for x in allowed_target_prefixes)
    for c in candidate_set.candidates:
        unknown=sorted(set(c.cited_observation_ids)-_citable(evidence_snapshot))
        if unknown: raise ValueError(f"candidate cites unknown/unverified observations: {', '.join(unknown)}")
        if exact is not None and any(t not in exact and not any(t.startswith(p) for p in prefixes) for t in c.targets): raise ValueError("candidate target is outside editable boundary")
    if candidate_set.candidates and candidate_set.next_action!="implement_candidate": raise ValueError("non-empty CandidateSet must request implementation")
    if not candidate_set.candidates and (candidate_set.next_action=="implement_candidate" or not candidate_set.no_candidate_reason): raise ValueError("empty CandidateSet needs an evidence/no-change reason")
    return candidate_set
def validate_candidate_review(review:CandidateReview,*,candidate_set:CandidateSet)->CandidateReview:
    review.verify_identity()
    if (review.candidate_set_id,review.evidence_snapshot_id,review.baseline_surface_manifest_id)!=(candidate_set.candidate_set_id,candidate_set.evidence_snapshot_id,candidate_set.baseline_surface_manifest_id): raise ValueError("review anchors do not match CandidateSet")
    ids=[c.candidate_id for c in candidate_set.candidates]
    if review.reviewed_candidate_ids!=ids: raise ValueError("reviewed IDs must exactly match CandidateSet order")
    if any(f.candidate_id not in ids for f in review.findings): raise ValueError("review finding cites unknown candidate")
    if review.accepted and any(f.severity=="error" for f in review.findings): raise ValueError("accepted review contains error finding")
    return review
def finalize_candidate_set_payload(payload:Mapping[str,Any])->CandidateSet:
    draft=json.loads(json.dumps(dict(payload))); draft["candidate_set_id"]="candidate_set_"+"0"*64
    if not isinstance(draft.get("candidates"),list): raise ValueError("candidates must be an array")
    for c in draft["candidates"]:
        if not isinstance(c,dict): raise ValueError("candidates must be objects")
        c["candidate_id"]="candidate_"+"0"*64
    provisional=CandidateSet.model_validate(draft)
    for raw,c in zip(draft["candidates"],provisional.candidates,strict=True): raw["candidate_id"]=c.expected_candidate_id()
    provisional=CandidateSet.model_validate(draft); draft["candidate_set_id"]=provisional.expected_candidate_set_id()
    result=CandidateSet.model_validate(draft); result.verify_identity(); return result
def finalize_candidate_review_payload(payload:Mapping[str,Any])->CandidateReview:
    draft=dict(payload); draft["review_id"]="candidate_review_"+"0"*64; provisional=CandidateReview.model_validate(draft); draft["review_id"]=provisional.expected_review_id(); return CandidateReview.model_validate(draft)
def build_empty_candidate_set(*,selected_workflow,evidence_snapshot_id,baseline_surface_manifest_id,next_action,reason):
    return finalize_candidate_set_payload({"schema":"botpipe.workflow_optimization.candidate_set/v2","selected_workflow":selected_workflow,"evidence_snapshot_id":evidence_snapshot_id,"baseline_surface_manifest_id":baseline_surface_manifest_id,"candidates":[],"next_action":next_action,"no_candidate_reason":reason})
def render_recommendation_report(*,evidence_snapshot,candidate_set,review):
    lines=["# Workflow optimization recommendation","",f"- Selected workflow: `{candidate_set.selected_workflow}`",f"- Evidence snapshot: `{candidate_set.evidence_snapshot_id}`",f"- Baseline surface: `{candidate_set.baseline_surface_manifest_id}`",f"- Recommendation basis: `{_field(evidence_snapshot,'recommendation_basis')}`","- Improvement: `not_evaluated`",f"- Next action: `{candidate_set.next_action}`","","## Candidates",""]
    lines += [f"- `{c.candidate_id}` ({c.kind}): {c.title}; hypothesis: {c.expected_effect}" for c in candidate_set.candidates] or [f"- No candidates. {candidate_set.no_candidate_reason}"]
    lines += ["","Candidate effects remain hypotheses until comparable evaluation."]
    return "\n".join(lines)+"\n"
def publish_recommendation(*,output_dir:Path,evidence_snapshot_path:Path,baseline_surface_manifest_path:Path,evidence_snapshot,candidate_set:CandidateSet,review:CandidateReview|None,max_output_bytes:int,candidate_set_source_path:Path|None=None)->PublicationReceipt:
    output_dir.mkdir(parents=True,exist_ok=True)
    write_incomplete_receipt(output_dir=output_dir,selected_workflow=candidate_set.selected_workflow,evidence_snapshot_id=candidate_set.evidence_snapshot_id,stop_reason="publication_in_progress")
    if review: validate_candidate_review(review,candidate_set=candidate_set)
    if candidate_set.candidates and (review is None or not review.accepted): raise ValueError("non-empty CandidateSet requires accepted independent review")
    cp=output_dir/"workflow_optimization_candidates.json"; rp=output_dir/"workflow_optimization_report.md"; hp=output_dir/"workflow_refinement_evidence.json"
    cb=(json.dumps(candidate_set.model_dump(mode="json",by_alias=True),indent=2,sort_keys=True)+"\n").encode() if candidate_set_source_path is None else candidate_set_source_path.read_bytes()
    if CandidateSet.model_validate_json(cb,strict=True)!=candidate_set: raise ValueError("CandidateSet changed after validation")
    rb=render_recommendation_report(evidence_snapshot=evidence_snapshot,candidate_set=candidate_set,review=review).encode()
    handoff=RefinementHandoff(target_workflow_id=candidate_set.selected_workflow,evidence_snapshot_id=candidate_set.evidence_snapshot_id,evidence_snapshot_path=str(evidence_snapshot_path.resolve()),baseline_surface_manifest_id=candidate_set.baseline_surface_manifest_id,baseline_surface_manifest_path=str(baseline_surface_manifest_path.resolve()),candidate_set_id=candidate_set.candidate_set_id,candidate_set_path=str(cp.resolve()),candidates=[HandoffCandidate(candidate_id=c.candidate_id,kind=c.kind,title=c.title) for c in candidate_set.candidates])
    hb=(json.dumps(handoff.model_dump(mode="json",by_alias=True),indent=2,sort_keys=True)+"\n").encode()
    if len(cb)+len(rb)+len(hb)>max_output_bytes: raise ValueError("recommendation output exceeds max_output_bytes")
    if candidate_set_source_path is None or candidate_set_source_path.resolve()!=cp.resolve(): atomic_write_bytes(cp,cb)
    atomic_write_bytes(rp,rb); atomic_write_bytes(hp,hb)
    receipt=PublicationReceipt(status="accepted",selected_workflow=candidate_set.selected_workflow,evidence_snapshot_id=candidate_set.evidence_snapshot_id,evidence_snapshot_path=str(evidence_snapshot_path.resolve()),baseline_surface_manifest_id=candidate_set.baseline_surface_manifest_id,baseline_surface_manifest_path=str(baseline_surface_manifest_path.resolve()),candidate_set_id=candidate_set.candidate_set_id,candidate_set_path=str(cp.resolve()),review_id=None if review is None else review.review_id,reviewed_candidate_ids=[] if review is None else review.reviewed_candidate_ids,next_action=candidate_set.next_action,refinement_handoff_path=str(hp.resolve()),report_path=str(rp.resolve()),stop_reason=None)
    atomic_write_record(output_dir/"optimization_publication_receipt.json",receipt); return receipt
def write_incomplete_receipt(*,output_dir:Path,selected_workflow:str,stop_reason:str,evidence_snapshot_id:str|None=None):
    receipt=PublicationReceipt(status="incomplete",selected_workflow=selected_workflow,evidence_snapshot_id=evidence_snapshot_id,evidence_snapshot_path=None,baseline_surface_manifest_id=None,baseline_surface_manifest_path=None,candidate_set_id=None,candidate_set_path=None,review_id=None,reviewed_candidate_ids=[],next_action=None,refinement_handoff_path=None,report_path=None,stop_reason=stop_reason); atomic_write_record(output_dir/"optimization_publication_receipt.json",receipt); return receipt

@dataclass(frozen=True,slots=True)
class OptimizationCandidateSelection:
    receipt:PublicationReceipt; candidate_set:CandidateSet; candidate:Candidate; evidence_snapshot_path:Path; baseline_surface_manifest_path:Path; refinement_handoff_path:Path
def _json(path,limit,label):
    value=json.loads(_read_bounded(path,limit,label));
    if not isinstance(value,dict): raise ValueError(f"{label} must be object")
    return value
def load_optimization_candidate(*,optimization_receipt_path:Path,candidate_id:str,expected_selected_workflow:str,allowed_kinds:Iterable[CandidateKind],max_output_bytes:int=10*1024*1024,max_evidence_bytes:int=50*1024*1024)->OptimizationCandidateSelection:
    receipt=PublicationReceipt.model_validate(_json(optimization_receipt_path,max_output_bytes,"receipt"),strict=True)
    if receipt.status!="accepted" or receipt.selected_workflow!=expected_selected_workflow or candidate_id not in receipt.reviewed_candidate_ids: raise ValueError("optimization receipt/candidate is not accepted for selected workflow")
    if not all((receipt.candidate_set_path,receipt.evidence_snapshot_path,receipt.baseline_surface_manifest_path,receipt.refinement_handoff_path)): raise ValueError("accepted receipt missing paths")
    cs=read_candidate_set(Path(receipt.candidate_set_path),max_output_bytes=max_output_bytes); cs.verify_identity()
    if (cs.candidate_set_id,cs.evidence_snapshot_id,cs.baseline_surface_manifest_id)!=(receipt.candidate_set_id,receipt.evidence_snapshot_id,receipt.baseline_surface_manifest_id): raise ValueError("receipt anchors mismatch")
    matches=[c for c in cs.candidates if c.candidate_id==candidate_id]
    if len(matches)!=1 or matches[0].kind not in set(allowed_kinds): raise ValueError("candidate missing, duplicate, or wrong kind")
    from .evidence import EvidenceSnapshot
    ev=EvidenceSnapshot.model_validate(_json(Path(receipt.evidence_snapshot_path),max_evidence_bytes,"evidence"))
    if ev.snapshot_id!=receipt.evidence_snapshot_id or not ev.verify_identity(): raise ValueError("evidence anchor mismatch")
    baseline=_json(Path(receipt.baseline_surface_manifest_path),max_evidence_bytes,"baseline")
    if baseline.get("surface_id")!=receipt.baseline_surface_manifest_id: raise ValueError("baseline anchor mismatch")
    handoff=RefinementHandoff.model_validate(_json(Path(receipt.refinement_handoff_path),max_output_bytes,"handoff"),strict=True)
    if handoff.candidate_set_id!=cs.candidate_set_id or not any(x.candidate_id==candidate_id and x.kind==matches[0].kind for x in handoff.candidates): raise ValueError("handoff mismatch")
    return OptimizationCandidateSelection(receipt,cs,matches[0],Path(receipt.evidence_snapshot_path),Path(receipt.baseline_surface_manifest_path),Path(receipt.refinement_handoff_path))

__all__=["OptimizationCandidateSelection","build_empty_candidate_set","finalize_candidate_review_payload","finalize_candidate_set_payload","load_optimization_candidate","publish_recommendation","read_candidate_review","read_candidate_set","render_recommendation_report","validate_candidate_review","validate_candidate_set","write_incomplete_receipt"]
