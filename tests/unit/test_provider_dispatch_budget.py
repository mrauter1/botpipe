from __future__ import annotations
import asyncio
from datetime import datetime,timedelta,timezone
import pytest
from botpipe.core.providers.budget import ProviderDispatchBudget,ProviderBudgetExhausted,ProviderBudgetResumeError,activate_provider_dispatch_budget
from botpipe.core.providers.models import TokenUsage
from botpipe.core.providers.rendered import RenderedLLMProvider
from botpipe.core.providers.turns import ProviderTurnResult,RenderedProviderTurn
class Transport:
    provider_name='fake'; supports_cancellation=True
    def __init__(self): self.calls=0
    def effective_dispatch_identity(self,turn): return {'provider':'fake','model':'m','effort':'high'}
    async def run_turn(self,turn):
        self.calls+=1
        if turn.prompt_text=='fail': raise RuntimeError('failed')
        return ProviderTurnResult('ok',None,usage=TokenUsage(total_tokens=7,source='fake') if turn.prompt_text=='known' else None)
def turn(text,kind='producer',attempt=1,sink=None):
    return RenderedProviderTurn('step',kind,text,None,'raw_text',step_execution_id='step:items:x:2',runtime_event_sink=sink,attempt=attempt)
def test_retry_repair_failure_and_unknown_usage_are_each_dispatches():
    t=Transport(); p=RenderedLLMProvider(t); events=[]; snapshots=[]; budget=ProviderDispatchBudget(3,checkpoint=lambda x:snapshots.append(dict(x)))
    async def run():
        with activate_provider_dispatch_budget(budget):
            with pytest.raises(RuntimeError): await p._dispatch_turn(turn('fail',sink=lambda n,x:events.append((n,dict(x)))))
            await p._dispatch_turn(turn('known','outcome_repair',sink=lambda n,x:events.append((n,dict(x)))))
            await p._dispatch_turn(turn('unknown','verifier',2,lambda n,x:events.append((n,dict(x)))))
            with pytest.raises(ProviderBudgetExhausted): await p._dispatch_turn(turn('known'))
    asyncio.run(run()); finished=[x for n,x in events if n=='provider_dispatch_finished']
    assert t.calls==3 and [x['used_turns'] for x in snapshots]==[1,2,3]
    assert [x['outcome'] for x in finished]==['failed','succeeded','succeeded']
    assert finished[1]['phase']=='repair' and finished[1]['token_usage']['total_tokens']==7
    assert finished[2]['attempt']==2 and finished[2]['token_usage']['total_tokens'] is None
    assert (finished[2]['scope'],finished[2]['item_id'],finished[2]['provider'])==('items','x','fake')
def test_resume_preserves_turns_and_rejects_rollback():
    now=datetime(2026,9,20,tzinfo=timezone.utc); b=ProviderDispatchBudget(3,deadline_utc=now+timedelta(minutes=5),wall_clock=lambda:now,monotonic_clock=lambda:1)
    b.reserve(); b.reserve(); state=b.snapshot(); resumed=ProviderDispatchBudget(3,state=state,wall_clock=lambda:now+timedelta(seconds=1),monotonic_clock=lambda:2)
    assert resumed.reserve().sequence==3
    with pytest.raises(ProviderBudgetExhausted): resumed.reserve()
    with pytest.raises(ProviderBudgetResumeError): ProviderDispatchBudget(3,state=state,wall_clock=lambda:now-timedelta(seconds=1))
def test_budget_rejects_transport_without_cancellation_contract():
    class NoCancel(Transport): supports_cancellation=False
    p=RenderedLLMProvider(NoCancel()); budget=ProviderDispatchBudget(1)
    async def run():
        with activate_provider_dispatch_budget(budget):
            with pytest.raises(Exception,match='cancellable'): await p._dispatch_turn(turn('known'))
    asyncio.run(run()); assert budget.used_turns==0

def test_timeout_cancels_cooperative_transport_and_finishes_dispatch():
    class Hanging(Transport):
        cancelled=False
        async def run_turn(self,turn):
            try: await asyncio.sleep(60)
            except asyncio.CancelledError: self.cancelled=True; raise
    t=Hanging(); p=RenderedLLMProvider(t); events=[]; budget=ProviderDispatchBudget(1,timeout_seconds=.01)
    async def run():
        with activate_provider_dispatch_budget(budget):
            with pytest.raises(Exception,match='provider dispatch exceeded'):
                await p._dispatch_turn(turn('hang',sink=lambda n,x:events.append((n,dict(x)))))
    asyncio.run(run()); finished=[x for n,x in events if n=='provider_dispatch_finished']
    assert t.cancelled and finished[0]['outcome']=='failed' and finished[0]['token_usage']['total_tokens'] is None
