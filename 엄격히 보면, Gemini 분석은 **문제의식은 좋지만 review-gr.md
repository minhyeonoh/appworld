엄격히 보면, Gemini 분석은 **문제의식은 좋지만 review-grade 문장으로는 과장**이 많아. 내 판정은 이래:
**(1) “Placeholder Trap”은 부분적으로만 타당**,
**(2) “Lossy Context Squeezing”은 THREAD에는 꽤 맞지만 CodeDelegator에는 대체로 틀림**,
**(3) “Rigid Error Recovery”는 4편 공통 주장으로는 성립하지 않음**이야. 특히 AppWorld는 단순 장기계획 벤치마크가 아니라 **rich code + complex control flow + state-based evaluation + collateral damage 검사**를 요구하고, 후속 AppWorld 연구들도 **API docs consultation, exact identifiers/API format preservation, variable states/guardrails 보존**이 중요하다고 보고한다는 점을 깔고 봐야 해. ([arXiv][1])

**1) “Placeholder Trap” — 부분 타당, 그러나 현재 표현은 과장**
ReCode는 실제로 **root placeholder function**에서 시작해 이를 재귀적으로 더 작은 placeholder나 primitive action으로 확장한다. REPL-Plan도 undefined function을 통해 child REPL을 spawn하는 **top-down recursive decomposition**을 쓴다. 여기까지는 사실이야. 하지만 두 방법을 똑같이 “먼저 환각된 추상함수부터 만들고, 나중에 API 현실과 충돌해 바닥에서 영원히 에러를 뿜는다”로 묶는 건 과하다. ReCode는 오히려 **shared variable namespace**를 유지하고, prompt에서 **주어진 변수 밖의 세부사항을 invent/guess하지 말라**고 명시한다. REPL-Plan도 단순 placeholder-first라기보다 **line-by-line REPL correction**이 핵심이고, ALFWorld뿐 아니라 WebShop과 real-world web tasks에서도 평가된다. 다만 REPL-Plan은 **zero-shot으로 새로운 subtask REPL을 추론해야 할 때** 잘못 추론하면 **failure loop**가 생긴다고 스스로 보고했으니, “OOD subtask abstraction이 실패를 부를 수 있다”는 정도까지는 근거가 있어. 그래서 reviewer 관점에서는: **“API-rich 환경에서 top-down subtask abstraction이 schema mismatch를 일으킬 위험이 있다”는 주장은 가능하지만, “ReCode/REPL-Plan은 환각된 placeholder 때문에 AppWorld에서 필연적으로 바닥에서 갇힌다”는 주장은 입증되지 않았다**고 볼 거야. ([arXiv][2])

**2) “Lossy Context Squeezing” — THREAD에는 꽤 맞고, CodeDelegator에는 대체로 틀림**
THREAD 쪽 비판은 상당히 reviewer-safe해. THREAD는 child가 parent에 **필요한 tokens만** 돌려주고, 저자들도 **explicit error handling이 없고**, **self-correction에 필요한 context가 lost될 수 있다**고 인정한다. 그래서 “격리를 위해 전달 채널을 줄이다 보니 exact state나 repair-relevant evidence가 빠질 위험이 있다”는 비판은 타당해. 다만 child output이 **“주로 자연어 요약”**이라는 표현은 부정확하다. 논문은 **tokens**라고 하지, summary라고 하진 않는다. exact string, ID, 값도 token으로 전달은 가능하니까. 반면 CodeDelegator는 이 지점에서 정반대 설계다. EPSS는 **typed input bindings, typed return schema, artifact references**를 쓰고, **large objects를 natural language로 요약해 넘기지 않도록** 설계되어 있다. 위로 올라가는 건 status, artifacts, summary, diagnostics이고, **discard되는 건 raw traces와 failed attempts**다. 그러니 CodeDelegator에 대해 “복잡한 JSON이나 transaction_id가 자연어 요약으로 압축돼 exact value가 끊긴다”는 평은 논문 설계와 맞지 않아. reviewer라면 이 문장을 바로 지적할 거야. CodeDelegator에 대해 성립하는 더 정확한 비판은 **“exact values가 아니라 fine-grained debugging evidence가 discard된다”** 쪽이야. ([arXiv][3])

**3) “Rigid Error Recovery” — 4편 공통 주장으로는 성립하지 않음**
이건 Gemini 분석에서 가장 약한 부분이야. THREAD는 맞다. 저자들이 직접 **explicit mechanisms for error handling이 없다**고 쓰고, robust recovery는 future work라고 인정한다. ReCode도 **명시적 backtracking/replan controller**를 제시하지는 않아서, “explicit strategic recovery가 약하다”는 비판은 가능하다. 하지만 REPL-Plan과 CodeDelegator까지 같은 바구니에 넣으면 안 돼. REPL-Plan은 REPL 상호작용을 통해 **line-by-line correction**, child REPL 재호출, code re-execution, caching/call counters 같은 복구 장치를 둔다. 또 저자들은 ALFWorld에서 REPL-Plan과 THREAD가 **environment issues에 맞춰 plan을 바꿀 수 있다**고 적는다. 완벽한 high-level backtracking을 정식화했다고 보긴 어렵지만, “자식 노드가 끙끙대다 max_retries에서 시스템이 죽는다”는 식의 단정은 논문에 없다. CodeDelegator는 더 분명해서, Delegator가 **Proceed / Retry / Replan**을 고르고, recoverable failure와 structural failure를 구분한다. “상위 전략 자체를 유연하게 틀어버릴 수 없다”는 말은 CodeDelegator에는 사실과 다르다. reviewer라면 이 대목을 가장 먼저 반박할 거야. 더 정확한 평은: **THREAD와 ReCode는 explicit strategic recovery가 약하고, REPL-Plan은 interactive correction은 강하지만 상위-level repair 체계는 덜 명시적이며, CodeDelegator만은 명시적 Retry/Replan을 갖는다**가 맞아. ([arXiv][3])

내가 reviewer처럼 한 줄로 정리하면 이거야.
**Gemini의 메타 직관은 맞아**: AppWorld는 ALFWorld 계열 recursive isolation 논문들이 직접 겨냥한 환경보다 **API grounding, exact state carryover, side-effect-safe repair**를 더 강하게 요구한다. 그런데 **세부 진술은 정밀도가 부족해**. 특히 `CodeDelegator = lossy summary handoff`, `4편 공통으로 strategy revision 불가`는 그대로 쓰면 반박당할 가능성이 높다. 반대로 reviewer-safe한 비판은 다음 세 가지야:
**(a)** top-down recursive abstraction은 API-rich/OOD subtask에서 schema mismatch 위험이 있다. 직접 근거는 REPL-Plan의 zero-shot subtask failure loop이고, ReCode에 대해서는 구조적 우려 수준이다.
**(b)** aggressive isolation은 repair-relevant state/evidence를 잃을 수 있다. 이건 THREAD에는 강하게 맞고, CodeDelegator에는 “artifact loss”가 아니라 “trace loss”로 표현해야 맞다.
**(c)** explicit high-level recovery는 방법별로 다르다: THREAD/ReCode는 약하고, REPL-Plan은 mixed, CodeDelegator는 명시적 Replan이 있다. ([arXiv][1])

네 문장을 논문에 쓸 수준으로 더 안전하게 바꾸면 이렇게 가는 게 좋아 보여:
**“Prior recursive isolation methods reduce context interference, but AppWorld-style interactive coding exposes a stricter requirement: the agent must preserve exact executable state and API-grounded commitments while localizing only the uncertainty or failure. Existing methods only partially meet this requirement—some under-specify cross-subtask state transfer, some discard repair-relevant traces, and some leave higher-level recovery under-specified.”** ([arXiv][1])

원하면 다음 답변에서 내가 이걸 **논문 introduction용 비판 문단**으로 바로 다듬어줄게.

[1]: https://arxiv.org/abs/2407.18901 "[2407.18901] AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents"
[2]: https://arxiv.org/html/2510.23564v1 "ReCode: Unify Plan and Action for Universal Granularity Control"
[3]: https://arxiv.org/html/2405.17402v2 "THREAD: Thinking Deeper with Recursive Spawning"
